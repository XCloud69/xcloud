import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from Data.database import get_db
from services import google_auth_service

router = APIRouter()


def _popup_response_html(payload: dict) -> str:
    """Render an HTML page that posts the auth result back to the opener
    window (the app that launched the OAuth popup) and then closes itself."""
    data = json.dumps(payload)
    return f"""<!doctype html>
<html>
  <head><meta charset="utf-8"><title>Signing in…</title></head>
  <body style="font-family: system-ui, sans-serif; background:#0a0a0a; color:#fafafa; display:grid; place-items:center; height:100vh; margin:0;">
    <p>Completing sign-in…</p>
    <script>
      (function () {{
        var payload = {data};
        try {{
          if (window.opener) {{
            window.opener.postMessage({{ source: "xcloud-google-auth", payload: payload }}, "*");
          }}
        }} catch (e) {{}}
        window.close();
      }})();
    </script>
  </body>
</html>"""


class GoogleAuthUrlResponse(BaseModel):
    auth_url: str
    state: str


class GoogleCallbackBody(BaseModel):
    code: str
    state: str


@router.get("/google/url", response_model=GoogleAuthUrlResponse)
async def google_auth_url():
    """Get the Google OAuth URL for sign-in."""
    try:
        return google_auth_service.get_google_auth_url()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/google/callback", response_class=HTMLResponse)
async def google_callback_get(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
):
    """Handle OAuth redirect from Google (GET).

    Returns a small HTML page that relays the auth result to the window that
    opened the OAuth popup, then closes itself.
    """
    try:
        result = google_auth_service.signup_or_login(db, code, state)
        return HTMLResponse(_popup_response_html({"ok": True, "data": result}))
    except HTTPException as e:
        return HTMLResponse(
            _popup_response_html({"ok": False, "error": e.detail}),
            status_code=e.status_code,
        )
    except Exception as e:  # noqa: BLE001
        return HTMLResponse(
            _popup_response_html({"ok": False, "error": str(e)}),
            status_code=500,
        )


@router.post("/google/callback")
async def google_callback_post(
    body: GoogleCallbackBody, db: Session = Depends(get_db)
):
    """Exchange an authorization code for a JWT token (POST)."""
    return google_auth_service.signup_or_login(db, body.code, body.state)
