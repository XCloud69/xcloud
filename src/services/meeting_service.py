import os
import datetime
import jwt
import requests
from fastapi import HTTPException
from .dir_config import get_recording_dir

VIDEOSDK_API_KEY = os.environ.get("VIDEOSDK_API_KEY", "")
VIDEOSDK_SECRET_KEY = os.environ.get("VIDEOSDK_SECRET_KEY", "")
RECORDING_DIR = get_recording_dir()

def generate_token() -> str:
    if not VIDEOSDK_API_KEY or not VIDEOSDK_SECRET_KEY:
        raise HTTPException(
            status_code=500,
            detail="VIDEOSDK_API_KEY or VIDEOSDK_SECRET_KEY environment variables are not set."
        )
    
    expiration = datetime.datetime.utcnow() + datetime.timedelta(hours=24)
    payload = {
        "apikey": VIDEOSDK_API_KEY,
        "permissions": ["allow_join", "allow_mod", "ask_join"],
        "version": 2,
        "roles": ["CRAWLER", "RTC"],
        "exp": expiration
    }
    
    token = jwt.encode(payload, VIDEOSDK_SECRET_KEY, algorithm="HS256")
    return token

def create_meeting() -> dict:
    token = generate_token()
    url = "https://api.videosdk.live/v2/rooms"
    headers = {
        "Authorization": token,
        "Content-Type": "application/json"
    }
    response = requests.post(url, headers=headers)
    if response.status_code == 200:
        return {"roomId": response.json().get("roomId"), "token": token}
    else:
        raise HTTPException(status_code=response.status_code, detail=response.text)

def validate_meeting(roomId: str) -> dict:
    token = generate_token()
    url = f"https://api.videosdk.live/v2/rooms/validate/{roomId}"
    headers = {
        "Authorization": token,
        "Content-Type": "application/json"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return {"roomId": response.json().get("roomId"), "token": token}
    else:
        raise HTTPException(status_code=response.status_code, detail=response.text)

def start_recording(roomId: str) -> dict:
    token = generate_token()
    url = "https://api.videosdk.live/v2/recordings/start"
    headers = {
        "Authorization": token,
        "Content-Type": "application/json"
    }
    payload = {
        "roomId": roomId
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        return response.json()
    else:
        raise HTTPException(status_code=response.status_code, detail=response.text)

def stop_recording(roomId: str) -> dict:
    token = generate_token()
    url = "https://api.videosdk.live/v2/recordings/end"
    headers = {
        "Authorization": token,
        "Content-Type": "application/json"
    }
    payload = {
        "roomId": roomId
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        return response.json()
    else:
        raise HTTPException(status_code=response.status_code, detail=response.text)
