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
    token = payload.get("data", {}).get("token", "")
    return f"""<!doctype html>
<html>
  <head><meta charset="utf-8"><title>Signing in…</title></head>
  <body style="font-family: system-ui, sans-serif; background:#0a0a0a; color:#fafafa; display:grid; place-items:center; height:100vh; margin:0;">
    <p style="margin-bottom:2rem;">Signed in!</p>
    <div style="background:#1a1a2e; padding:1rem 2rem; border-radius:8px; max-width:90vw; overflow-wrap:break-word;">
      <p style="font-size:0.8rem; opacity:0.6; margin-bottom:0.5rem;">Your token:</p>
      <code style="font-size:0.75rem; color:#7ec8e3;">{token}</code>
    </div>
    <script>
      (function () {{
        var payload = {data};
        try {{
          if (window.opener) {{
            window.opener.postMessage({{ source: "xcloud-google-auth", payload: payload }}, "*");
          }}
        }} catch (e) {{}}
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


@router.get("/google/callback")
async def google_callback_get(
    code: str = Query(...),
    state: str = Query(...),
    fmt: str | None = Query(None, alias="format"),
    db: Session = Depends(get_db),
):
    """Handle OAuth redirect from Google (GET).

    Returns a small HTML page that relays the auth result to the window that
    opened the OAuth popup, then closes itself.

    Add ?format=json to get a plain JSON response instead (for CLI use).
    """
    try:
        result = google_auth_service.signup_or_login(db, code, state)
        if fmt == "json":
            return result
        return HTMLResponse(_popup_response_html({"ok": True, "data": result}))
    except HTTPException as e:
        if fmt == "json":
            raise
        return HTMLResponse(
            _popup_response_html({"ok": False, "error": e.detail}),
            status_code=e.status_code,
        )
    except Exception as e:  # noqa: BLE001
        if fmt == "json":
            raise HTTPException(status_code=500, detail=str(e))
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
