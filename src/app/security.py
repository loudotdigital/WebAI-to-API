# src/app/security.py
import os
from fastapi import Depends, HTTPException, status, Request # <-- Import Request
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

API_KEY = os.getenv("API_KEY")

def verify_api_key(request: Request, token: str = Depends(oauth2_scheme)): # <-- Add request: Request
    # Allow OPTIONS preflight requests to pass without a key
    if request.method == "OPTIONS":
        return

    if not API_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API Key not configured on the server."
        )
    if token != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key",
        )