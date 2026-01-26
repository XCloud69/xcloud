from time import sleep
import subprocess
from os import makedirs, path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from json import load

# === CONFIGURATION ===
with open("path.json", "r") as f:
    config_data = load(f)
WATCH_DIR = config_data["WATCH_DIR"]
TRANSCRIPT_SCRIPT = config_data["TRANSCRIPT_SCRIPT"]
PYTHON_EXEC = config_data["PYTHON_EXEC"]
# =====================


class WatchHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return

        filepath = event.src_path
        print(f"\nNew file detected: {filepath}")
        sleep(2)
        try:
            print(f"Starting transcription for {path.basename(filepath)}...")
            _ = subprocess.run([PYTHON_EXEC, TRANSCRIPT_SCRIPT, filepath], check=True)
            print(f"Done: {path.basename(filepath)}\n")
        except subprocess.CalledProcessError as e:
            print(f"Transcription failed for {filepath}: {e}")


def main():
    makedirs(WATCH_DIR, exist_ok=True)
    print(f"Watching directory: {WATCH_DIR}")

    event_handler = WatchHandler()
    observer = Observer()
    _ = observer.schedule(event_handler, WATCH_DIR, recursive=False)
    observer.start()

    try:
        while True:
            sleep(1)
    except KeyboardInterrupt:
        print("\nStopping watcher...")
        observer.stop()
    observer.join()
