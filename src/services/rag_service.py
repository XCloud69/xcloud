from llama_index.core import VectorStoreIndex, StorageContext
from llama_index.core import SimpleDirectoryReader
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore
from chromadb import PersistentClient
from os import path

# Initialize embedding model (using your local Ollama)
embed_model = OllamaEmbedding(
    model_name="nomic-embed-text:latest",
    base_url="http://localhost:11434",
)

# Initialize ChromaDB client
chroma_client = PersistentClient(path="./.chroma_db")

current_index = None
current_collection_name = None


def create_index_from_folder(folder_path: str,
                             collection_name: str = "default"):
    """
    Create a vector index from documents in a folder.
    Supports: .txt, .md, .pdf, .docx, etc.
    """
    global current_index, current_collection_name

    if not path.exists(folder_path):
        raise ValueError(f"Folder path does not exist: {folder_path}")

    # Load documents from folder
    documents = SimpleDirectoryReader(
        input_dir=folder_path,
        recursive=True,
        required_exts=[".txt", ".md", ".pdf"]  # Add more as needed
    ).load_data()

    if not documents:
        raise ValueError(f"No supported documents found in {folder_path}")

    try:
        chroma_client.delete_collection(name=collection_name)
    except:
        pass

    chroma_collection = chroma_client.create_collection(name=collection_name)

    # Create vector store
    vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    # Create index with custom embedding model
    current_index = VectorStoreIndex.from_documents(
        documents,
        storage_context=storage_context,
        embed_model=embed_model,
        show_progress=True,
    )

    current_collection_name = collection_name

    return {
        "status": "success",
        "documents_indexed": len(documents),
        "collection": collection_name
    }


def load_existing_index(collection_name: str = "default"):
    """
    Load an existing index from ChromaDB.
    """
    global current_index, current_collection_name

    try:
        chroma_collection = chroma_client.get_collection(name=collection_name)
        vector_store = ChromaVectorStore(chroma_collection=chroma_collection)

        current_index = VectorStoreIndex.from_vector_store(
            vector_store=vector_store,
            embed_model=embed_model,
        )

        current_collection_name = collection_name
        return {"status": "success", "collection": collection_name}
    except Exception as e:
        raise ValueError(f"Failed to load collection '{
                         collection_name}': {str(e)}")


def get_context_for_llm(question: str, top_k: int = 3):
    """
    Get relevant context to inject into LLM prompt.
    Returns tuple: (context_text, sources_list)
    """
    if current_index is None:
        return "", []

    retriever = current_index.as_retriever(similarity_top_k=top_k)
    nodes = retriever.retrieve(question)

    # Combine all relevant text
    context_parts = []
    sources = []

    for i, node in enumerate(nodes, 1):
        context_parts.append(f"[Source {i}]\n{node.node.text}\n")
        sources.append({
            "id": i,
            "text": node.node.text[:200] + "...",
            "score": node.score,
            "metadata": node.node.metadata  # Contains file path, etc.
        })

    return "\n".join(context_parts), sources


def list_collections():
    """
    List all available collections in ChromaDB.
    """
    collections = chroma_client.list_collections()
    return [{"name": col.name, "count": col.count()} for col in collections]


def get_current_collection_info():
    """
    Get info about the currently loaded collection.
    """
    if current_index is None:
        return {"status": "No collection loaded"}

    return {
        "collection_name": current_collection_name,
        "status": "loaded"
    }
