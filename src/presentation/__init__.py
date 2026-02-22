import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .llm_api import router as llm_router
from .rag_api import router as rag_router
from .auth_api import router as auth_router
from .task_api import router as task_router
from .reminder_api import router as reminder_router
from .notification_api import router as notification_router
from Data.database import init_db
from services.reminder_service import check_and_fire_due_reminders


async def _reminder_background_loop():
    """Periodically check for due reminders and create notifications."""
    while True:
        try:
            check_and_fire_due_reminders()
        except Exception:
            pass  # Don't crash the background loop
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create DB tables
    init_db()
    # Start background reminder checker
    task = asyncio.create_task(_reminder_background_loop())
    yield
    # Shutdown: cancel background task
    task.cancel()


app = FastAPI(title="Xcloud", version="0.3.0", lifespan=lifespan)

# CORS - allow all origins for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(llm_router, prefix="/llm", tags=["LLM & Chat"])
app.include_router(rag_router, prefix="/rag", tags=["RAG"])
app.include_router(task_router, prefix="/tasks", tags=["Tasks"])
app.include_router(reminder_router, prefix="/reminders", tags=["Reminders"])
app.include_router(notification_router, prefix="/notifications", tags=["Notifications"])
