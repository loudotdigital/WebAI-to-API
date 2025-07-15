import os
from fastapi import FastAPI, Request, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware

from app.services.gemini_client import get_gemini_client
from app.services.session_manager import init_session_managers
from app.logger import logger

from app.endpoints import gemini, chat

API_KEY = os.getenv("API_KEY", "default-key-please-change")
BEARER_TOKEN = f"Bearer {API_KEY}"

async def verify_bearer_token(request: Request):
    if request.method == "OPTIONS":
        return
    if request.url.path in ["/docs", "/redoc", "/openapi.json"]:
        return
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header is missing",
        )
    if auth_header != BEARER_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Bearer Token",
        )

@asynccontextmanager
async def lifespan(app: FastAPI):
    if get_gemini_client():
        init_session_managers()
        logger.info("Session managers initialized for WebAI-to-API.")
    yield
    logger.info("Application shutdown complete.")

app = FastAPI(lifespan=lifespan, dependencies=[Depends(verify_bearer_token)])
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(gemini.router)
app.include_router(chat.router)