from fastapi import UploadFile, File, APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from services import llm_service, whisper, rag_service
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
    """Legacy endpoint - simple text concatenation"""
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


@router.post("/rag/index")
async def index_folder(folder_path: str, collection_name: str = "default"):
    """
    Index a folder for RAG retrieval.
    Creates embeddings and stores them in ChromaDB.
    """
    try:
        result = rag_service.create_index_from_folder(
            folder_path, collection_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rag/load")
async def load_collection(collection_name: str):
    """
    Load an existing RAG collection.
    """
    try:
        result = rag_service.load_existing_index(collection_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/rag/query")
async def rag_query(question: str, top_k: int = 5):
    """
    Query the RAG system directly.
    Returns answer with sources.
    """
    try:
        result = rag_service.query_rag(question, top_k)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rag/collections")
async def list_rag_collections():
    """
    List all available RAG collections.
    """
    return rag_service.list_collections()


@router.get("/rag/status")
async def rag_status():
    """
    Get current RAG collection status.
    """
    return rag_service.get_current_collection_info()


@router.get("/chat")
async def chat(prompt: str, use_rag: bool = False, top_k: int = 3):
    """
    Chat with LLM, optionally using RAG context.
    """
    sources = []

    if use_rag:
        if rag_service.current_index is None:
            raise HTTPException(
                status_code=400,
                detail="No RAG index loaded. Please load or create a collection first."
            )

        try:
            rag_context, sources = rag_service.get_context_for_llm(
                prompt, top_k)
            llm_service.extra_context = rag_context
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"RAG error: {str(e)}")

    # Stream response with sources metadata first
    async def stream_with_metadata():
        import json
        # Send sources as first event
        if sources:
            yield f"data: {json.dumps({'type': 'sources', 'data': sources})}\n\n"

        # Then stream LLM response
        async for chunk in llm_service.ollama_streamer(prompt):
            yield chunk

    return StreamingResponse(
        stream_with_metadata(),
        media_type="text/event-stream"
    )
