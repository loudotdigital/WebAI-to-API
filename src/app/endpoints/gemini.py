# src/app/endpoints/gemini.py
from fastapi import APIRouter, HTTPException, Depends  # <--- MAKE SURE THIS LINE IS CORRECT
from app.logger import logger
from schemas.request import GeminiRequest
from app.services.gemini_client import get_gemini_client
from app.services.session_manager import get_gemini_chat_manager
from app.security import verify_api_key

from pathlib import Path
from typing import Union, List, Optional

# Add the dependency here to protect all routes in this file
router = APIRouter(dependencies=[Depends(verify_api_key)])

@router.post("/gemini")
async def gemini_generate(request: GeminiRequest):
    gemini_client = get_gemini_client()
    if not gemini_client:
        raise HTTPException(status_code=503, detail="Gemini client is not initialized.")
    try:
        files: Optional[List[Union[str, Path]]] = [Path(f) for f in request.files] if request.files else None
        response = await gemini_client.generate_content(request.message, request.model.value, files=files)
        return {"response": response.text}
    except Exception as e:
        logger.error(f"Error in /gemini endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error generating content: {str(e)}")

@router.post("/gemini-chat")
async def gemini_chat(request: GeminiRequest):
    gemini_client = get_gemini_client()
    session_manager = get_gemini_chat_manager()
    if not gemini_client or not session_manager:
        raise HTTPException(status_code=503, detail="Gemini client is not initialized.")
    try:
        response = await session_manager.get_response(request.model, request.message, request.files)
        return {"response": response.text}
    except Exception as e:
        logger.error(f"Error in /gemini-chat endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error in chat: {str(e)}")