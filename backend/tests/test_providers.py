"""Adapter hardening: LLM HTTP providers (success, API error, malformed
response) and the SMTP sender (success, recipient refused, connection error)
— all offline via MockTransport and a stubbed smtplib."""

import smtplib

import httpx
import pytest

from app.llm.base import LLMError
from app.llm.providers import GeminiProvider, GroqProvider, get_provider
from app.sender.providers import OutgoingEmail, SMTPSender


# ---------- LLM providers ----------

def _groq(response: httpx.Response) -> GroqProvider:
    return GroqProvider("key", transport=httpx.MockTransport(lambda req: response))


def test_groq_success_and_payload_shape():
    ok = httpx.Response(200, json={"choices": [{"message": {"content": "hello"}}]})
    assert _groq(ok).complete("s", "u") == "hello"


def test_groq_api_error_raises_llmerror():
    with pytest.raises(LLMError, match="429"):
        _groq(httpx.Response(429, text="rate limited")).complete("s", "u")


def test_groq_malformed_response_raises_llmerror():
    with pytest.raises(LLMError, match="shape"):
        _groq(httpx.Response(200, json={"unexpected": True})).complete("s", "u")


def test_gemini_success_and_error():
    ok = httpx.Response(200, json={
        "candidates": [{"content": {"parts": [{"text": "hi"}]}}]})
    provider = GeminiProvider("key", transport=httpx.MockTransport(lambda r: ok))
    assert provider.complete("s", "u") == "hi"

    bad = GeminiProvider("key", transport=httpx.MockTransport(
        lambda r: httpx.Response(500, text="boom")))
    with pytest.raises(LLMError, match="500"):
        bad.complete("s", "u")


def test_missing_key_and_unknown_provider_rejected():
    with pytest.raises(LLMError, match="key missing"):
        GroqProvider("")
    with pytest.raises(LLMError, match="Unknown LLM provider"):
        get_provider("chatgpt", "key")


# ---------- SMTP sender ----------

class StubSMTP:
    """Stands in for smtplib.SMTP as a context manager."""

    instances: list = []
    fail_with: Exception | None = None

    def __init__(self, host, port, timeout=30):
        self.host, self.port = host, port
        self.calls = []
        StubSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        self.calls.append("starttls")

    def login(self, username, password):
        self.calls.append(("login", username))

    def send_message(self, msg):
        if StubSMTP.fail_with:
            raise StubSMTP.fail_with
        self.calls.append(("send", msg["To"]))


@pytest.fixture()
def smtp(monkeypatch):
    StubSMTP.instances = []
    StubSMTP.fail_with = None
    monkeypatch.setattr(smtplib, "SMTP", StubSMTP)
    return StubSMTP


EMAIL = OutgoingEmail(to="tpo@abc.ac.in", subject="Hi", body_text="Body",
                      from_name="Maaz", from_email="maaz@outreach.example")


def make_sender():
    return SMTPSender(host="smtp.test", port=587, username="user", password="pw")


def test_smtp_send_success(smtp):
    result = make_sender().send(EMAIL)
    assert result.ok
    calls = smtp.instances[0].calls
    assert calls[0] == "starttls"            # TLS before credentials, always
    assert ("login", "user") in calls
    assert ("send", "tpo@abc.ac.in") in calls


def test_smtp_recipient_refused_is_clean_failure(smtp):
    smtp.fail_with = smtplib.SMTPRecipientsRefused({"tpo@abc.ac.in": (550, b"no user")})
    result = make_sender().send(EMAIL)
    assert not result.ok and "refused" in result.error


def test_smtp_connection_error_is_clean_failure(smtp):
    smtp.fail_with = OSError("connection reset")
    result = make_sender().send(EMAIL)
    assert not result.ok and "connection reset" in result.error


def test_smtp_requires_host():
    with pytest.raises(ValueError, match="SMTP_HOST"):
        SMTPSender(host="")
