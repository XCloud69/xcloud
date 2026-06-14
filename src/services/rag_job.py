"""
Background RAG indexing job manager.

Runs a single indexing job at a time in a worker thread so the FastAPI event
loop is never blocked, and supports real cancellation: the worker polls a
threading.Event between document nodes and stops + rolls back when set.
"""

import threading
import time
import uuid

from services import rag_service


class _IndexJob:
    def __init__(self, folder_path: str, collection_name: str):
        self.id = uuid.uuid4().hex
        self.folder_path = folder_path
        self.collection_name = collection_name
        self.state = "running"   # running | success | cancelled | error
        self.phase = "starting"  # starting | reading | embedding
        self.done = 0
        self.total = 0
        self.error = None
        self.result = None
        self.started_at = time.time()
        self.finished_at = None
        self._cancel = threading.Event()
        self._thread = None

    # --- worker ---------------------------------------------------------
    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        def is_cancelled():
            return self._cancel.is_set()

        def on_progress(done, total):
            self.done = done
            self.total = total

        def on_phase(phase):
            self.phase = phase

        try:
            result = rag_service.create_index_from_folder_cancellable(
                self.folder_path,
                self.collection_name,
                is_cancelled=is_cancelled,
                on_progress=on_progress,
                on_phase=on_phase,
            )
            self.result = result
            self.state = "success"
        except rag_service.IndexingCancelled:
            self.state = "cancelled"
        except Exception as e:  # noqa: BLE001
            self.state = "error"
            self.error = str(e)
        finally:
            self.finished_at = time.time()

    def cancel(self):
        self._cancel.set()

    def to_dict(self):
        return {
            "job_id": self.id,
            "state": self.state,
            "phase": self.phase,
            "folder_path": self.folder_path,
            "collection_name": self.collection_name,
            "done": self.done,
            "total": self.total,
            "error": self.error,
            "result": self.result,
        }


_current_job: _IndexJob | None = None
_lock = threading.Lock()


def start_index_job(folder_path: str, collection_name: str = "default") -> dict:
    """Start a new indexing job. Rejects if one is already running."""
    global _current_job
    with _lock:
        if _current_job is not None and _current_job.state == "running":
            raise RuntimeError("An indexing job is already running.")
        job = _IndexJob(folder_path, collection_name)
        _current_job = job
    job.start()
    return job.to_dict()


def cancel_index_job() -> dict:
    """Signal the current job to cancel. Returns its status."""
    with _lock:
        job = _current_job
    if job is None:
        return {"state": "idle"}
    job.cancel()
    return job.to_dict()


def get_index_status() -> dict:
    """Return the status of the current/last job, or idle."""
    with _lock:
        job = _current_job
    if job is None:
        return {"state": "idle"}
    return job.to_dict()
