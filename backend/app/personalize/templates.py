"""Template helpers — append context to the user prompt without changing SYSTEM_PROMPT."""

from app.models.email_template import EmailTemplate


def build_template_prompt_block(template: EmailTemplate | None) -> str:
    """Return text appended to the fact-sheet user prompt, or empty string."""
    if template is None:
        return ""
    parts: list[str] = []
    if template.name and template.name.strip():
        parts.append(
            f"TEMPLATE NAME: {template.name.strip()}"
        )
    if template.description and template.description.strip():
        parts.append(
            f"TEMPLATE OBJECTIVE: {template.description.strip()}"
        )
    if template.additional_context and template.additional_context.strip():
        parts.append(
            "EMAIL TEMPLATE CONTENT / INSTRUCTIONS:\n"
            "You MUST base the email message, offer, key points, structure, and details on this template:\n"
            + template.additional_context.strip()
        )
    if template.formatting_notes and template.formatting_notes.strip():
        parts.append(
            "FORMATTING & TONE GUIDANCE:\n" + template.formatting_notes.strip()
        )
    if not parts:
        return ""
    return "\n\n=== SELECTED EMAIL TEMPLATE ===\n" + "\n\n".join(parts) + "\n================================\n"


def preview_template_prompt(
    template: EmailTemplate,
    fact_sheet: str | None = None,
) -> str:
    """Render how the template augments a draft-generation prompt."""
    block = build_template_prompt_block(template)
    if fact_sheet:
        return f"FACT SHEET:\n{fact_sheet}{block}"
    sample = (
        "RECIPIENT: Dr. Example\n"
        "COLLEGE: Sample College\n"
        "CITY/STATE: Pune, Maharashtra\n"
        "...(contact-specific facts would appear here)..."
    )
    return f"FACT SHEET:\n{sample}{block}"
