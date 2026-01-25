from fastapi import UploadFile, File, APIRouter
from fastapi.responses import StreamingResponse
from services import llm_service
import os

router = APIRouter()


@router.post("/set_context")
async def set_context(file: UploadFile = File(...)):
    content = await file.read()
    llm_service.extra_context = content.decode("utf-8")
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
async def chat_route(prompt: str):
    return StreamingResponse(
        llm_service.ollama_streamer(prompt),
        media_type="text/event-stream"
    )
