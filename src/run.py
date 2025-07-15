# src/run.py (Simplified Web Controller Version)
import argparse
import asyncio
import multiprocessing
import time
import sys
import os
import signal
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import uvicorn

# --- DYNAMICALLY IMPORT AI SERVER MODULES (to keep things clean) ---

def is_g4f_available():
    try:
        from g4f.api import run_api
        return True
    except ImportError:
        return False

def is_webai_available():
    try:
        from app.services.gemini_client import init_gemini_client
        return asyncio.run(init_gemini_client())
    except Exception:
        return False

# --- SERVER RUNNER FUNCTIONS (These run in separate processes) ---

def run_g4f_server_process(host, port, stop_event):
    """Starts the G4F server and waits for a stop signal."""
    from g4f.api import run_api
    import threading

    signal.signal(signal.SIGINT, signal.SIG_IGN) # Ignore Ctrl+C in child process
    
    def shutdown_monitor():
        stop_event.wait()
        os._exit(0) # Force exit when event is set

    threading.Thread(target=shutdown_monitor, daemon=True).start()
    print(f"[AI Server] Starting g4f server on http://{host}:{port}")
    run_api(host=host, port=port)

def run_webai_server_process(host, port, stop_event):
    """Starts the WebAI FastAPI server and waits for a stop signal."""
    from app.main import app as webai_app
    import threading

    signal.signal(signal.SIGINT, signal.SIG_IGN) # Ignore Ctrl+C in child process
    
    config = uvicorn.Config(webai_app, host=host, port=port, log_config=None)
    server = uvicorn.Server(config)

    def shutdown_monitor():
        stop_event.wait()
        server.should_exit = True

    threading.Thread(target=shutdown_monitor, daemon=True).start()
    print(f"[AI Server] Starting WebAI server on http://{host}:{port}")
    server.run()

# --- MAIN CONTROLLER ---

if __name__ == "__main__":
    multiprocessing.freeze_support()

    # --- Configuration ---
    AI_HOST = "0.0.0.0"
    AI_PORT = 6969
    CONTROLLER_HOST = "0.0.0.0"
    CONTROLLER_PORT = 7000

    # Use a multiprocessing Manager to share state between the controller and the main loop
    manager = multiprocessing.Manager()
    shared_state = manager.dict({
        "current_mode": None,
        "webai_available": False,
        "g4f_available": False,
    })

    # --- The Controller Web App (replaces the CLI) ---
    controller_app = FastAPI()

    @controller_app.get("/", response_class=HTMLResponse)
    async def get_controller_ui():
        try:
            with open("src/controller.html", "r") as f:
                return HTMLResponse(content=f.read())
        except FileNotFoundError:
            return HTMLResponse(content="<h1>Error: src/controller.html not found.</h1>", status_code=500)

    @controller_app.get("/status")
    async def get_status():
        return dict(shared_state)

    @controller_app.post("/switch/{mode}")
    async def switch_mode(mode: str):
        if mode in ["webai", "g4f"]:
            # This is a signal to the main loop below
            shared_state["requested_mode"] = mode
            return {"status": "request received", "mode": mode}
        return {"status": "error", "message": "Invalid mode"}

    # --- Main Application Logic ---
    print("--- Initializing Controller ---")
    shared_state["webai_available"] = is_webai_available()
    shared_state["g4f_available"] = is_g4f_available()

    initial_mode = "webai" if shared_state["webai_available"] else "g4f" if shared_state["g4f_available"] else None
    shared_state["requested_mode"] = initial_mode
    
    # Start the controller UI in the main process
    # This makes it easy to manage and keeps things simple
    controller_thread = threading.Thread(
        target=uvicorn.run,
        args=(controller_app,),
        kwargs={"host": CONTROLLER_HOST, "port": CONTROLLER_PORT, "log_level": "warning"},
        daemon=True
    )
    controller_thread.start()
    print(f"🚀 Controller UI running at http://{CONTROLLER_HOST}:{CONTROLLER_PORT}/")

    if not initial_mode:
        print("❌ No AI servers are available to run. Please check your configuration. The controller UI will still run.")
        while True: time.sleep(1) # Keep controller alive

    ai_process = None
    stop_event = None

    try:
        while True:
            requested = shared_state.get("requested_mode")

            if requested and requested != shared_state["current_mode"]:
                if ai_process and ai_process.is_alive():
                    print(f"[Controller] Stopping '{shared_state['current_mode']}' server...")
                    stop_event.set()
                    ai_process.join(timeout=5)
                    if ai_process.is_alive():
                        ai_process.terminate()

                print(f"[Controller] Starting '{requested}' server...")
                shared_state["current_mode"] = requested
                shared_state["requested_mode"] = None  # Clear the request
                stop_event = multiprocessing.Event()

                target_func = run_webai_server_process if requested == "webai" else run_g4f_server_process
                ai_process = multiprocessing.Process(
                    target=target_func, args=(AI_HOST, AI_PORT, stop_event)
                )
                ai_process.start()

            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Controller] Shutdown signal received...")
    finally:
        if ai_process and ai_process.is_alive():
            stop_event.set()
            ai_process.terminate()
        print("[Controller] Shutdown complete.")