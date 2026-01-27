from fastapi import UploadFile, File, APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from services import llm_service, whisper
import os

router = APIRouter()


@router.post("/set_context")
async def set_context(file: UploadFile = File(...)):
    content = await file.read()
    mime_type = file.content_type
    if mime_type.startswith("text/"):
        text_context = content.decode("utf-8")
    elif mime_type.startswith("audio/"):
        try:
            text_context = await whisper.transcript.transcribe_audio(content)
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Transcription failed: {str(e)}")
    else:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    llm_service.extra_context = text_context
    return {"status": "Context loaded"}


@router.post("/set_context_folder")
async def set_folder_context(path: str):
    if os.path.exists(path):
        llm_service.extra_context = llm_service.read_context_from_folder(path)
        return {"status": f"Context loaded from {path}"}
    return {"error": "path does not exist"}, 400


@router.get("/models")
async def list_models():
    return llm_service.get_available_models()


@router.post("/models")
async def set_model(name: str):
    llm_service.current_model = name
    return {"message": f"Active model set to {llm_service.current_model}"}


@router.get("/chat")
async def chat(prompt: str):
    return StreamingResponse(
        llm_service.ollama_streamer(prompt),
        media_type="text/event-stream"
    )
