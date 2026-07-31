"""Unauthenticated endpoints: unsubscribe landing, open pixel, click redirect.
These are the URLs embedded in outbound email."""

import base64

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import EmailEvent, EmailEventType, EmailMessage
from app.sender.links import verify_unsubscribe_token
from app.sender.service import record_unsubscribe

router = APIRouter(tags=["public"])

_PIXEL_GIF = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")


@router.get("/u/{token}", response_class=HTMLResponse)
def unsubscribe(token: str, db: Session = Depends(get_db)):
    contact_id = verify_unsubscribe_token(token)
    if contact_id is None:
        raise HTTPException(404, "Invalid link")
    record_unsubscribe(db, contact_id)
    return HTMLResponse(
        "<html><body style='font-family:sans-serif;max-width:480px;margin:80px auto'>"
        "<h3>You're unsubscribed.</h3>"
        "<p>You will not receive further emails from us. Sorry for the bother.</p>"
        "</body></html>"
    )


@router.get("/t/o/{message_id}.gif")
def open_pixel(message_id: int, db: Session = Depends(get_db)):
    message = db.get(EmailMessage, message_id)
    if message:
        db.add(EmailEvent(message_id=message.id, event_type=EmailEventType.OPEN))
        db.commit()
    return Response(content=_PIXEL_GIF, media_type="image/gif",
                    headers={"Cache-Control": "no-store"})


@router.get("/t/c/{message_id}")
def click_redirect(message_id: int, url: str, db: Session = Depends(get_db)):
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "Invalid redirect URL")
    message = db.get(EmailMessage, message_id)
    if message:
        db.add(EmailEvent(message_id=message.id, event_type=EmailEventType.CLICK,
                          meta={"url": url[:500]}))
        db.commit()
    return RedirectResponse(url, status_code=302)
