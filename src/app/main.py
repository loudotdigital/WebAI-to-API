# src/app/main.py
import os
from fastapi import FastAPI, Request, HTTPException, status
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware

from app.services.gemini_client import get_gemini_client
from app.services.session_manager import init_session_managers
from app.logger import logger

# Import endpoint routers
from app.endpoints import gemini, chat

# --- Bearer Token Authentication ---
API_KEY = os.getenv("API_KEY", "default-key-please-change")
BEARER_TOKEN = f"Bearer {API_KEY}"

@asynccontextmanager
async def lifespan(app: FastAPI):
    if get_gemini_client():
        init_session_managers()
        logger.info("Session managers initialized for WebAI-to-API.")
    yield
    logger.info("Application shutdown complete.")

app = FastAPI(lifespan=lifespan)

# --- CORRECTED: Use Middleware for Authentication ---
@app.middleware("http")
async def verify_bearer_token_middleware(request: Request, call_next):
    # First, let OPTIONS requests for CORS preflight pass through without a key
    if request.method == "OPTIONS":
        return await call_next(request)
        
    # Also allow access to documentation
    if request.url.path in ["/docs", "/redoc", "/openapi.json"]:
        return await call_next(request)

    # Now, check for the token on all other requests
    auth_header = request.headers.get("Authorization")
    if auth_header != BEARER_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Bearer Token",
        )
    
    response = await call_next(request)
    return response
# --- END of corrected logic ---

# Add CORS middleware AFTER the auth middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register the endpoint routers for WebAI-to-API
app.include_router(gemini.router)
app.include_router(chat.router)