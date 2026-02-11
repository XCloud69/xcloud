from fastapi import APIRouter, HTTPException
from services import rag_service

router = APIRouter()


@router.post("/index")
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


@router.get("/status")
async def rag_status():
    """
    Get current RAG collection status.
    """
    return rag_service.get_current_collection_info()
