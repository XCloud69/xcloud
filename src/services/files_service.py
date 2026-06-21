"""
File browser service — list directories and read files like an HTTP directory index.
"""

import os
import stat
import mimetypes
from datetime import datetime, timezone

from services.dir_config import get_recording_dir


def _file_entry(filepath: str, name: str) -> dict:
    """Build metadata dict for a single file or directory."""
    try:
        st = os.stat(filepath)
    except OSError:
        return {"name": name, "error": "Cannot stat"}

    is_dir = stat.S_ISDIR(st.st_mode)
    modified = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)

    entry = {
        "name": name + ("/" if is_dir else ""),
        "is_directory": is_dir,
        "size": st.st_size if not is_dir else None,
        "modified": modified.isoformat(),
        "permissions": stat.filemode(st.st_mode),
    }

    if not is_dir:
        mime, _ = mimetypes.guess_type(name)
        entry["mime_type"] = mime

    return entry


def browse(path: str) -> dict:
    """
    List the contents of a directory.
    Returns metadata about the directory and its entries,
    sorted with directories first, then files, both alphabetically.
    """
    abs_path = os.path.abspath(path)

    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"Path does not exist: {path}")

    if not os.path.isdir(abs_path):
        raise NotADirectoryError(f"Not a directory: {path}")

    entries = []
    try:
        names = os.listdir(abs_path)
    except PermissionError:
        raise PermissionError(f"Permission denied: {path}")

    for name in names:
        full = os.path.join(abs_path, name)
        entries.append(_file_entry(full, name))

    dirs = sorted(
        [e for e in entries if e.get("is_directory")],
        key=lambda e: e["name"].lower(),
    )
    files = sorted(
        [e for e in entries if not e.get("is_directory")],
        key=lambda e: e["name"].lower(),
    )

    return {
        "path": abs_path,
        "parent": os.path.dirname(abs_path),
        "entries": dirs + files,
        "total_dirs": len(dirs),
        "total_files": len(files),
    }


def read_file(path: str, max_size: int = 10 * 1024 * 1024) -> dict:
    """
    Read a file and return its content with metadata.
    Text files return the content as a string.
    Binary files return base64-encoded content.
    max_size limits to 10MB by default.
    """
    import base64

    abs_path = os.path.abspath(path)

    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"File does not exist: {path}")

    if os.path.isdir(abs_path):
        raise IsADirectoryError(f"Path is a directory, use browse instead: {path}")

    st = os.stat(abs_path)
    if st.st_size > max_size:
        raise ValueError(f"File too large ({st.st_size} bytes). Max: {max_size} bytes.")

    mime, _ = mimetypes.guess_type(abs_path)
    is_text = (mime or "").startswith("text/") or mime in (
        "application/json",
        "application/xml",
        "application/javascript",
        "application/x-yaml",
        "application/toml",
    )
    if mime is None:
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                f.read(512)
            is_text = True
        except (UnicodeDecodeError, ValueError):
            is_text = False

    modified = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)

    result = {
        "path": abs_path,
        "name": os.path.basename(abs_path),
        "size": st.st_size,
        "mime_type": mime,
        "modified": modified.isoformat(),
        "is_text": is_text,
    }

    if is_text:
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            result["content"] = f.read()
    else:
        with open(abs_path, "rb") as f:
            result["content"] = base64.b64encode(f.read()).decode("ascii")
        result["encoding"] = "base64"

    return result


def _safe_filename(filename: str) -> str:
    """Strip any path components and keep a clean basename."""
    name = os.path.basename(filename.replace("\\", "/")).strip()
    return name or "recording.webm"


def _unique_path(directory: str, filename: str) -> str:
    """Return a path inside directory that does not collide with an existing file."""
    base, ext = os.path.splitext(filename)
    candidate = os.path.join(directory, filename)
    counter = 1
    while os.path.exists(candidate):
        candidate = os.path.join(directory, f"{base} ({counter}){ext}")
        counter += 1
    return candidate


def save_recording(data: bytes, filename: str) -> dict:
    """
    Persist an uploaded meeting recording into ~/Xcloud/recordings.
    Returns metadata about the saved file.
    """
    directory = get_recording_dir()
    os.makedirs(directory, exist_ok=True)

    safe = _safe_filename(filename)
    target = _unique_path(directory, safe)

    with open(target, "wb") as f:
        f.write(data)

    st = os.stat(target)
    return {
        "path": os.path.abspath(target),
        "name": os.path.basename(target),
        "size": st.st_size,
    }
