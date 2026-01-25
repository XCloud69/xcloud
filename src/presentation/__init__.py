from fastapi import FastAPI
from .llm_api import router as llm_router


app = FastAPI()


app.include_router(llm_router, prefix="/llm")
