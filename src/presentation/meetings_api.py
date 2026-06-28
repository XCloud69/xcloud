from fastapi import APIRouter
from services import meeting_service

router = APIRouter()


@router.get("/get-token")
def get_token():
    """Generates a VideoSDK token."""
    token = meeting_service.generate_token()
    return {"token": token}


@router.post("/create-meeting")
def create_meeting():
    """Creates a meeting room on VideoSDK."""
    return meeting_service.create_meeting()


@router.post("/validate-meeting/{roomId}")
def validate_meeting(roomId: str):
    """Validates if a meeting room exists."""
    return meeting_service.validate_meeting(roomId)


@router.post("/start-recording/{roomId}")
def start_recording(roomId: str):
    """Starts cloud recording for a specific room."""
    return meeting_service.start_recording(roomId)


@router.post("/stop-recording/{roomId}")
def stop_recording(roomId: str):
    """Stops cloud recording for a specific room."""
    return meeting_service.stop_recording(roomId)
