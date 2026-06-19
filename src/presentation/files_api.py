"""File browser API — browse directories, view files, and save recordings."""

import os
import time
from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File
from fastapi.responses import FileResponse

from Data.models import User
from services import auth_service, files_service
from services.dir_config import get_recording_dir

router = APIRouter()


@router.get("/browse")
async def browse_directory(
    path: str = Query("~", description="Directory path to browse"),
    show_hidden: bool = Query(False, description="Show hidden files (dotfiles)"),
    user: User = Depends(auth_service.get_current_user),
):
    """
    List files and folders in a directory, like a browser directory index.
    Returns file names, sizes, types, modification dates, and permissions.
    """
    expanded = os.path.expanduser(path)
    try:
        result = files_service.browse(expanded)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except NotADirectoryError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    if not show_hidden:
        result["entries"] = [
            e for e in result["entries"]
            if not e["name"].lstrip("/").startswith(".")
        ]
        result["total_dirs"] = sum(
            1 for e in result["entries"] if e.get("is_directory")
        )
        result["total_files"] = sum(
            1 for e in result["entries"] if not e.get("is_directory")
        )

    return result


@router.get("/view")
async def view_file(
    path: str = Query(..., description="File path to view"),
    user: User = Depends(auth_service.get_current_user),
):
    """
    Read a file's content with metadata.
    Text files return content as a string, binary files as base64.
    """
    expanded = os.path.expanduser(path)
    try:
        return files_service.read_file(expanded)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except IsADirectoryError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=413, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("/download")
async def download_file(
    path: str = Query(..., description="File path to download"),
    user: User = Depends(auth_service.get_current_user),
):
    """Download a file directly."""
    expanded = os.path.expanduser(path)
    abs_path = os.path.abspath(expanded)

    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    if os.path.isdir(abs_path):
        raise HTTPException(status_code=400, detail="Cannot download a directory")

    return FileResponse(
        abs_path,
        filename=os.path.basename(abs_path),
        media_type="application/octet-stream",
    )


@router.post("/save-recording")
async def save_recording(
    file: UploadFile = File(...),
    user: User = Depends(auth_service.get_current_user),
):
    """Save a meeting recording to ~/Xcloud/recordings/."""
    recordings_dir = get_recording_dir()
    os.makedirs(recordings_dir, exist_ok=True)

    filename = file.filename or f"recording-{int(time.time())}.webm"
    dest = os.path.join(recordings_dir, filename)

    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)

    return {
        "path": dest,
        "name": filename,
        "size": len(content),
    }
