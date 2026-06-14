import os

from fastapi import APIRouter, HTTPException
from services import rag_service, rag_job

router = APIRouter()


@router.post("/index")
async def index_folder(folder_path: str, collection_name: str = "default"):
    """
    Start indexing a folder for RAG retrieval (runs in the background).

    Returns immediately with a job id. Poll GET /rag/index/status for progress
    and POST /rag/index/cancel to stop it.
    """
    if not os.path.exists(folder_path):
        raise HTTPException(
            status_code=400,
            detail=f"Folder path does not exist: {folder_path}",
        )
    try:
        return rag_job.start_index_job(folder_path, collection_name)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/index/status")
async def index_status():
    """Get the status/progress of the current (or last) indexing job."""
    return rag_job.get_index_status()


@router.post("/index/cancel")
async def index_cancel():
    """Cancel the running indexing job, if any."""
    return rag_job.cancel_index_job()


@router.post("/load")
async def load_collection(collection_name: str):
    """
    Load an existing RAG collection.
    """
    try:
        result = rag_service.load_existing_index(collection_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/collections")
async def list_rag_collections():
    """
    List all available RAG collections.
    """
    return rag_service.list_collections()


@router.get("/collections/{collection_name}/files")
async def list_collection_files(collection_name: str):
    """
    List the distinct source files indexed in a collection.
    """
    try:
        return rag_service.get_collection_files(collection_name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/collections/{collection_name}/source")
async def collection_source(collection_name: str):
    """
    Recover the source folder a collection was indexed from (best-effort,
    from stored file paths). Used by the UI's "Update" action.
    """
    try:
        return rag_service.get_collection_source_folder(collection_name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/collections/{collection_name}")
async def delete_rag_collection(collection_name: str):
    """
    Delete a RAG collection.
    """
    try:
        return rag_service.delete_collection(collection_name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def rag_status():
    """
    Get current RAG collection status.
    """
    return rag_service.get_current_collection_info()
