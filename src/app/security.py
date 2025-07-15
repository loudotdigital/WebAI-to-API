# src/app/security.py
import os
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

# This object looks for the "Authorization: Bearer <token>" header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Load the secret key from the environment
API_KEY = os.getenv("API_KEY")

def verify_api_key(token: str = Depends(oauth2_scheme)):
    if not API_KEY:
        # This is a server configuration error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API Key not configured on the server."
        )
    if token != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key",
        )