from fastapi import UploadFile, File, APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from services import llm_service, whisper, rag_service, search_service
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
    llm_service.session.extra_context = text_context
    return {"status": "Context loaded"}


@router.post("/set_context_folder")
async def set_folder_context(path: str):
    """Legacy endpoint - simple text concatenation"""
    if os.path.exists(path):
        llm_service.session.extra_context = llm_service.read_context_from_folder(
            path)
        return {"status": f"Context loaded from {path}"}
    raise HTTPException(status_code=400, detail="Path does not exist")


@router.get("/models")
async def list_models():
    return llm_service.get_available_models()


@router.post("/models")
async def set_model(name: str):
    llm_service.session.model = name
    return {"message": f"Active model set to {llm_service.session.model}"}


@router.post("/clear")
async def clear_conversation():
    """Reset the conversation history."""
    llm_service.session.clear_history()
    return {"status": "Conversation history cleared"}


@router.get("/chat")
async def chat(prompt: str, use_rag: bool = False,
               use_web_search: bool = False, top_k: int = 3,
               search_results: int = 5,):
    """
    Chat with LLM, optionally using RAG context and/or web search.

    - use_rag: enrich prompt with local document context from ChromaDB
    - use_web_search: search the web and inject results as context
    """
    sources = []
    context_parts = []

    # 1. RAG context
    if use_rag:
        if rag_service.current_index is None:
            raise HTTPException(
                status_code=400,
                detail="""No RAG index loaded.
                Please load or create a collection first."""
            )
        try:
            rag_context, rag_sources = rag_service.get_context_for_llm(
                prompt, top_k)
            context_parts.append(f"=== Document Context ===\n{rag_context}")
            sources.extend([{**s, "type": "rag"} for s in rag_sources])
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"RAG error: {str(e)}")

    # 2. Web search context
    if use_web_search:
        try:
            search_context = search_service.format_search_results_as_context(
                prompt, max_results=search_results
            )
            context_parts.append(
                f"=== Web Search Results ===\n{search_context}")

            # Add web sources to the sources list
            web_results = search_service.web_search(
                prompt, max_results=search_results)
            for i, result in enumerate(web_results, 1):
                if "error" not in result:
                    sources.append({
                        "id": f"web-{i}",
                        "type": "web",
                        "title": result.get("title", ""),
                        "url": result.get("href", ""),
                        "text": result.get("body", "")[:200] + "...",
                    })
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Web search error: {str(e)}")

    # Combine all context
    llm_service.extra_context = "\n\n".join(context_parts)

    # Stream response with sources metadata first
    async def stream_with_metadata():
        import json
        # Send sources as first event
        if sources:
            yield f"data: {json.dumps({'type': 'sources',
                                       'data': sources})}\n\n"

        # Then stream LLM response
        async for chunk in llm_service.session.stream(prompt):
            yield chunk

    return StreamingResponse(
        stream_with_metadata(),
        media_type="text/event-stream"
    )
