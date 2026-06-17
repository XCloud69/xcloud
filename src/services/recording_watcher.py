import os
import asyncio
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from services.dir_config import (
    get_recording_dir,
    get_transcriptions_dir,
    get_summarization_dir,
)
from services.whisper.transcript import transcribe_audio
from services.llm_service import summarize_text
from Data.database import SessionLocal
from Data.models import User, Chat
from services.chat_service import create_chat, add_message


class RecordingHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        time.sleep(2)
        asyncio.run(self._process(event.src_path))

    async def _process(self, filepath):
        basename = os.path.splitext(os.path.basename(filepath))[0]

        transcript_path = os.path.join(get_transcriptions_dir(), f"{basename}.txt")
        if os.path.exists(transcript_path):
            return

        print(f"[recording-watcher] Transcribing {basename}...")
        with open(filepath, "rb") as f:
            audio_bytes = f.read()
        transcript = await transcribe_audio(audio_bytes)

        os.makedirs(get_transcriptions_dir(), exist_ok=True)
        with open(transcript_path, "w") as f:
            f.write(transcript)
        print(f"[recording-watcher] Transcription saved: {transcript_path}")

        print(f"[recording-watcher] Summarizing {basename}...")
        summary = await summarize_text(transcript)

        os.makedirs(get_summarization_dir(), exist_ok=True)
        summary_path = os.path.join(get_summarization_dir(), f"{basename}_summary.txt")
        with open(summary_path, "w") as f:
            f.write(summary)
        print(f"[recording-watcher] Summary saved: {summary_path}")

        try:
            self._inject_into_chat(basename, summary)
        except Exception as e:
            print(f"[recording-watcher] Chat injection failed: {e}")

    def _inject_into_chat(self, title: str, summary: str):
        db = SessionLocal()
        try:
            user = db.query(User).first()
            if not user:
                print("[recording-watcher] No user found, skipping chat")
                return
            meeting_chat = db.query(Chat).filter(
                Chat.user_id == user.id, Chat.title == "Meeting Summaries"
            ).first()
            if meeting_chat:
                chat_id = meeting_chat.id
            else:
                chat_data = create_chat(db, user.id, title="Meeting Summaries")
                chat_id = chat_data["id"]
            add_message(db, chat_id, role="system",
                        content=f"## {title}\n\n{summary}")
            print(f"[recording-watcher] Summary added to chat '{title}'")
        finally:
            db.close()


def start_recording_watcher() -> Observer:
    recordings_dir = get_recording_dir()
    os.makedirs(recordings_dir, exist_ok=True)
    event_handler = RecordingHandler()
    observer = Observer()
    observer.schedule(event_handler, recordings_dir, recursive=False)
    observer.start()
    print(f"[recording-watcher] Watching: {recordings_dir}")
    return observer
