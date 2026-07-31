"""Reply handling: classify an inbound reply and update the CRM.

v1 intake is the API endpoint (paste/forward a reply); IMAP/webhook polling
can feed the same `process_reply` later."""

import enum
import re

from sqlalchemy.orm import Session

from app.llm.base import LLMError, LLMProvider
from app.models import (
    Contact,
    ContactStatus,
    EmailEvent,
    EmailEventType,
    EmailMessage,
)
from app.sender.service import _cancel_followups, record_unsubscribe


class ReplySentiment(str, enum.Enum):
    POSITIVE = "POSITIVE"
    NEUTRAL = "NEUTRAL"
    NEGATIVE = "NEGATIVE"
    AUTO_REPLY = "AUTO_REPLY"
    UNSUBSCRIBE = "UNSUBSCRIBE"


SYSTEM_PROMPT = """Classify a reply to a B2B outreach email proposing a free AI \
guest lecture at a college. Answer with exactly one word:
POSITIVE - interested, asks for details/call/dates, forwards to a colleague to arrange
NEUTRAL - acknowledges without commitment, asks to write later
NEGATIVE - declines, not interested
AUTO_REPLY - out-of-office / automatic acknowledgement
UNSUBSCRIBE - asks to stop emailing or remove from list"""

_UNSUB_RE = re.compile(r"\b(unsubscribe|stop\s+email|remove\s+me|do\s+not\s+(contact|email))\b", re.I)


def classify_reply(text: str, llm: LLMProvider) -> ReplySentiment:
    if _UNSUB_RE.search(text or ""):
        return ReplySentiment.UNSUBSCRIBE  # never let the LLM miss an opt-out
    try:
        raw = llm.complete(SYSTEM_PROMPT, text[:4000], max_tokens=5).strip().upper()
    except LLMError:
        return ReplySentiment.NEUTRAL  # safe default: human reviews, no auto-action
    for sentiment in ReplySentiment:
        if sentiment.value in raw:
            return sentiment
    return ReplySentiment.NEUTRAL


_STATUS_FOR = {
    ReplySentiment.POSITIVE: ContactStatus.REPLIED_POSITIVE,
    ReplySentiment.NEGATIVE: ContactStatus.REPLIED_NEGATIVE,
    ReplySentiment.NEUTRAL: ContactStatus.REPLIED_POSITIVE,  # a human reply = warm; operator can downgrade
}


def process_reply(db: Session, contact: Contact, text: str, llm: LLMProvider) -> ReplySentiment:
    sentiment = classify_reply(text, llm)

    message = (
        db.query(EmailMessage)
        .filter_by(contact_id=contact.id)
        .order_by(EmailMessage.sent_at.desc())
        .first()
    )
    if message:
        db.add(EmailEvent(message_id=message.id, event_type=EmailEventType.REPLY,
                          meta={"sentiment": sentiment.value, "excerpt": text[:500]}))

    if sentiment is ReplySentiment.UNSUBSCRIBE:
        record_unsubscribe(db, contact.id)
    elif sentiment is ReplySentiment.AUTO_REPLY:
        db.commit()  # event recorded; sequence continues
    else:
        contact.status = _STATUS_FOR[sentiment]
        _cancel_followups(db, contact.id, f"replied ({sentiment.value.lower()})")
        db.commit()
    return sentiment
