"""Draft quality gate. A draft failing any BLOCKING check cannot be approved.
Checks are dumb and deterministic on purpose — the LLM writes, this verifies."""

import re

UNSUBSCRIBE_TOKEN = "%UNSUBSCRIBE_URL%"

# leaked template placeholders: [College Name], {{name}}, <NAME>
_PLACEHOLDER_RES = [
    re.compile(r"\[[A-Za-z][^\]]{2,40}\]"),
    re.compile(r"\{\{[^}]+\}\}"),
    re.compile(r"<[A-Z][A-Z _]{2,30}>"),
]

_SPAM_PHRASES = [
    "100% free", "act now", "limited time", "risk-free", "click here",
    "winner", "congratulations", "no obligation", "urgent", "once in a lifetime",
    "money back", "double your",
]

BODY_MIN, BODY_MAX = 400, 2200
SUBJECT_MAX = 78


def lint_draft(subject_options: list[str], body_text: str, college_name: str) -> dict:
    """Returns {"ok": bool, "errors": [...], "warnings": [...]}."""
    errors: list[str] = []
    warnings: list[str] = []

    if not subject_options or len(subject_options) < 5:
        errors.append("fewer than 5 subject options")
    for subject in subject_options or []:
        if len(subject) > SUBJECT_MAX:
            errors.append(f"subject too long ({len(subject)} chars): {subject[:40]}…")
        if subject.isupper():
            errors.append(f"all-caps subject: {subject[:40]}")

    body_lower = (body_text or "").lower()
    if not body_text or len(body_text) < BODY_MIN:
        errors.append(f"body too short (<{BODY_MIN} chars)")
    if body_text and len(body_text) > BODY_MAX:
        errors.append(f"body too long (>{BODY_MAX} chars)")

    for regex in _PLACEHOLDER_RES:
        leaked = regex.findall(body_text or "")
        if leaked:
            errors.append(f"template placeholder leaked: {leaked[:3]}")

    if UNSUBSCRIBE_TOKEN not in (body_text or ""):
        errors.append("missing unsubscribe token")

    if college_name and college_name.split()[0].lower() not in body_lower:
        errors.append("body never mentions the college")

    for phrase in _SPAM_PHRASES:
        if phrase in body_lower:
            warnings.append(f"spam-trigger phrase: {phrase!r}")
    if (body_text or "").count("!") > 3:
        warnings.append("too many exclamation marks")

    return {"ok": not errors, "errors": errors, "warnings": warnings}
