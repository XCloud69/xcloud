from fastapi import FastAPI
from .llm_api import router as llm_router
from .rag_api import router as rag_router


app = FastAPI()


app.include_router(llm_router, prefix="/llm")
app.include_router(rag_router, prefix="/rag")
