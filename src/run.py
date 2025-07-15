# src/run.py (Corrected version using middleware for g4f)
import argparse
import asyncio
import multiprocessing
import time
import sys
import threading
import os
import signal
from typing import Dict, Tuple

# This block is only processed by type checkers like Pylance
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from multiprocessing.synchronize import Event as MultiprocessingEvent

# Import tomli to read pyproject.toml
try:
    import tomli
except ImportError:
    try:
        import tomllib as tomli
    except ImportError:
        tomli = None

# --- App and Service Imports ---
from app.config import load_config
from app.main import app as webai_app
from app.services.gemini_client import init_gemini_client

# Conditionally import g4f runner function
try:
    from g4f.api import create_app
    G4F_AVAILABLE = True
except ImportError:
    G4F_AVAILABLE = False

# --- FastAPI and Security imports for the controller and auth ---
from fastapi import FastAPI, Request, HTTPException, status, Depends
from fastapi.responses import HTMLResponse
import uvicorn


# Helper class for terminal colors
class Colors:
    """A class to hold ANSI color codes for terminal output."""
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    RED = "\033[91m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


# --- Helper function to get app info ---
def get_app_info() -> Tuple[str, str]:
    """Reads application name and version from pyproject.toml."""
    if not tomli:
        return "WebAI to API", "N/A (tomli not installed)"
    try:
        with open("pyproject.toml", "rb") as f:
            toml_data = tomli.load(f)
        poetry_data = toml_data.get("tool", {}).get("poetry", {})
        name = poetry_data.get("name", "WebAI-to-API").replace("-", " ").title()
        version = poetry_data.get("version", "N/A")
        return name, version
    except (FileNotFoundError, KeyError):
        return "WebAI-to-API", "N/A"


# --- UNIFIED Server Runner Functions ---
def start_webai_server(
    host: str, port: int, reload: bool, stop_event: "MultiprocessingEvent"
):
    """Starts the WebAI Uvicorn server. Auth is handled in app.main."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    config = uvicorn.Config(webai_app, host=host, port=port, reload=reload, log_config=None)
    server = uvicorn.Server(config)

    def shutdown_monitor():
        stop_event.wait()
        server.should_exit = True

    monitor_thread = threading.Thread(target=shutdown_monitor, daemon=True)
    monitor_thread.start()

    print_server_info(host, port, "webai")
    server.run()
    print(f"\n[WebAI Server] Process exited gracefully.")


def start_g4f_server(host: str, port: int, stop_event: "MultiprocessingEvent"):
    """Starts the G4F server and wraps it with Bearer Token auth middleware."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # --- CORRECTED: Bearer Token Authentication Logic using Middleware ---
    API_KEY = os.getenv("API_KEY", "default-key-please-change")
    BEARER_TOKEN = f"Bearer {API_KEY}"

    # Get the original g4f application
    g4f_app = create_app()

    @g4f_app.middleware("http")
    async def verify_g4f_bearer_token(request: Request, call_next):
        # Allow access to documentation and the root health check without a key
        if request.url.path in ["/docs", "/redoc", "/openapi.json", "/"]:
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        if auth_header != BEARER_TOKEN:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing Bearer Token",
            )
        
        # If the token is valid, proceed with the request
        response = await call_next(request)
        return response
    # --- END of corrected logic ---

    def shutdown_monitor():
        stop_event.wait()
        print(f"\n[G4F Server] Stop signal received. Exiting.")
        os._exit(0)

    monitor_thread = threading.Thread(target=shutdown_monitor, daemon=True)
    monitor_thread.start()

    print_server_info(host, port, "g4f")
    uvicorn.run(g4f_app, host=host, port=port, log_level="info")


# --- Helper Function for Printing Info ---
def print_server_info(host: str, port: int, mode: str):
    """Displays complete, formatted information about the running server."""
    protocol = "http"
    base_url = f"{protocol}://{host}:{port}"
    app_name, app_version = get_app_info()
    app_info_line = f"{app_name} v{app_version}".center(80)
    print("\n" + "=" * 80)
    print(f"{Colors.BOLD}{Colors.YELLOW}{app_info_line}{Colors.RESET}")
    if mode == "webai":
        print("🚀 WebAI-to-API Server is RUNNING (Primary Mode) 🚀".center(80))
    elif mode == "g4f":
        print("🚀 gpt4free Server is RUNNING 🚀".center(80))
    print("=" * 80)
    print(f"INFO: API Server available at: {base_url} (Protected with Bearer Token)")
    print("=" * 80)


# --- Main Execution Block ---
if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    multiprocessing.freeze_support()

    manager = multiprocessing.Manager()
    shared_state = manager.dict({
        "requested_mode": None,
        "current_mode": None,
        "webai_available": False,
        "g4f_available": False,
    })

    parser = argparse.ArgumentParser(description="Run a managed server with a web controller.")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host IP address for AI servers")
    parser.add_argument("--port", type=int, default=6969, help="Port for AI servers")
    parser.add_argument("--controller-port", type=int, default=7000, help="Port for the web controller")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reloading for WebAI mode")
    args = parser.parse_args()

    # --- Controller FastAPI App ---
    controller_app = FastAPI()

    @controller_app.get("/controller", response_class=HTMLResponse)
    async def get_controller_page():
        try:
            with open("src/controller.html", "r") as f:
                return HTMLResponse(content=f.read())
        except FileNotFoundError:
            return HTMLResponse(content="<h1>Error: controller.html not found.</h1>", status_code=500)

    @controller_app.get("/controller/status")
    async def get_status():
        return dict(shared_state)

    @controller_app.post("/controller/switch/{mode}")
    async def switch_mode(mode: str):
        if mode in ["webai", "g4f"]:
            print(f"[Controller] Web request received to switch to '{mode}' mode.")
            shared_state["requested_mode"] = mode
            return {"status": "switching", "mode": mode}
        return {"status": "error", "message": "Invalid mode"}

    def run_controller(host: str, port: int):
        print("--- Starting Controller UI Server ---")
        uvicorn.run(controller_app, host=host, port=port, log_level="warning")

    controller_process = multiprocessing.Process(
        target=run_controller, args=(args.host, args.controller_port)
    )
    controller_process.daemon = True
    controller_process.start()
    time.sleep(2)
    print("\n" + "=" * 80)
    print(f"🚀 {Colors.BOLD}{Colors.MAGENTA}CONTROLLER UI is running at http://{args.host}:{args.controller_port}/controller{Colors.RESET}")
    print("=" * 80 + "\n")

    print("INFO:     Checking availability of server modes...")
    shared_state["webai_available"] = asyncio.run(init_gemini_client())
    shared_state["g4f_available"] = G4F_AVAILABLE

    if shared_state["webai_available"]:
        print(f"INFO:     ✅ {Colors.CYAN}WebAI-to-API mode is available.{Colors.RESET}")
    else:
        print(f"WARN:     ⚠️ {Colors.YELLOW}WebAI-to-API mode is not available.{Colors.RESET}")
    if shared_state["g4f_available"]:
        print(f"INFO:     ✅ {Colors.CYAN}gpt4free mode is available.{Colors.RESET}")
    else:
        print(f"WARN:     ⚠️ {Colors.YELLOW}gpt4free mode is not available.{Colors.RESET}")

    initial_mode = "webai" if shared_state["webai_available"] else "g4f" if shared_state["g4f_available"] else None
    if not initial_mode:
        print("\nERROR:    No server modes are available to run. Exiting.")
        controller_process.terminate()
        sys.exit(1)

    current_process = None
    stop_event = None

    try:
        while True:
            requested = shared_state["requested_mode"]
            if not current_process or (requested and requested != shared_state["current_mode"]):
                if current_process and current_process.is_alive():
                    print(f"\n[Controller] Gracefully stopping server ('{shared_state['current_mode']}')...")
                    if stop_event:
                        stop_event.set()
                    current_process.join(timeout=10)
                    if current_process.is_alive():
                        print("[Controller] Process did not stop in time, terminating.")
                        current_process.terminate()

                current_mode = requested or initial_mode
                shared_state["current_mode"] = current_mode
                shared_state["requested_mode"] = None

                print(f"\n[Controller] Starting server in '{current_mode}' mode on port {args.port}...")
                stop_event = multiprocessing.Event()

                if current_mode == "webai":
                    process_args = (args.host, args.port, args.reload, stop_event)
                    target_func = start_webai_server
                else: # g4f
                    process_args = (args.host, args.port, stop_event)
                    target_func = start_g4f_server

                current_process = multiprocessing.Process(target=target_func, args=process_args)
                current_process.start()
            
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n[Controller] Ctrl+C detected. Initiating final shutdown...")

    finally:
        if stop_event and not stop_event.is_set():
            stop_event.set()
        if current_process and current_process.is_alive():
            print("[Controller] Waiting for final AI server process to shut down...")
            current_process.join(timeout=5)
            if current_process.is_alive():
                current_process.terminate()
        if controller_process and controller_process.is_alive():
            print("[Controller] Shutting down controller UI process...")
            controller_process.terminate()
        print("[Controller] Shutdown complete. Forcing exit.")
        os._exit(0)