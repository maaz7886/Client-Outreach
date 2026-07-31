"""Signed per-contact unsubscribe links. HMAC over the contact id with the
app secret — no DB lookup needed to verify, no way to forge someone else's."""

import hashlib
import hmac

from app.core.config import get_settings


def _sign(contact_id: int) -> str:
    secret = get_settings().jwt_secret.encode()
    return hmac.new(secret, f"unsub:{contact_id}".encode(), hashlib.sha256).hexdigest()[:24]


def unsubscribe_token(contact_id: int) -> str:
    return f"{contact_id}.{_sign(contact_id)}"


def unsubscribe_url(contact_id: int) -> str:
    return f"{get_settings().public_base_url.rstrip('/')}/u/{unsubscribe_token(contact_id)}"


def verify_unsubscribe_token(token: str) -> int | None:
    """Returns the contact id, or None for a tampered/malformed token."""
    try:
        raw_id, signature = token.split(".", 1)
        contact_id = int(raw_id)
    except ValueError:
        return None
    if hmac.compare_digest(signature, _sign(contact_id)):
        return contact_id
    return None
