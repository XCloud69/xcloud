import os

XDCLOUD_HOME = os.path.join(os.path.expanduser("~"), "Xcloud")

SUBDIRS = [
    "notes",
    "recordings",
    "transcriptions",
    "summarization",
    "exports",
]

def ensure_xcloud_dirs() -> None:
    os.makedirs(XDCLOUD_HOME, exist_ok=True)
    for sub in SUBDIRS:
        os.makedirs(os.path.join(XDCLOUD_HOME, sub), exist_ok=True)

def get_recording_dir() -> str:
    return os.path.join(XDCLOUD_HOME, "recordings")

def get_notes_dir() -> str:
    return os.path.join(XDCLOUD_HOME, "notes")

def get_transcriptions_dir() -> str:
    return os.path.join(XDCLOUD_HOME, "transcriptions")

def get_summarization_dir() -> str:
    return os.path.join(XDCLOUD_HOME, "summarization")
