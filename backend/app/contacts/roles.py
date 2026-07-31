"""Free-text designation → canonical decision-maker role. Rules only — cheap,
deterministic, and auditable. Anything unmatched stays OTHER (still stored,
just deprioritized)."""

import re

from app.models import CanonicalRole

# ordered: first match wins, most specific first
_RULES: list[tuple[str, CanonicalRole]] = [
    (r"training\s*(and|&)\s*placement|t\s*&\s*p\s*officer|\btpo\b", CanonicalRole.TPO),
    (r"placement\s*(director|head|dean)|(director|head|dean)\s*(of\s*)?placement",
     CanonicalRole.PLACEMENT_DIRECTOR),
    (r"placement\s*officer|placement\s*co", CanonicalRole.TPO),
    (r"training\s*officer", CanonicalRole.TRAINING_OFFICER),
    (r"vice\s*[- ]?principal", CanonicalRole.VICE_PRINCIPAL),
    (r"principal", CanonicalRole.PRINCIPAL),
    (r"(hod|head)\b.*(computer|cse|it\b|artificial|ai\b|data\s*science|aiml|ai&ds)",
     CanonicalRole.AI_CS_DEPT_HEAD),
    (r"(computer|cse|artificial|ai\b|aiml).*(hod|head\s*of\s*department)",
     CanonicalRole.AI_CS_DEPT_HEAD),
    (r"\bhod\b|head\s*of\s*(the\s*)?department", CanonicalRole.HOD),
    (r"\bdean\b", CanonicalRole.DEAN),
    (r"innovation\s*(cell|council|centre|center)", CanonicalRole.INNOVATION_CELL_HEAD),
    (r"(e[- ]?cell|entrepreneurship)", CanonicalRole.ECELL_HEAD),
    (r"incubat", CanonicalRole.INCUBATION_HEAD),
    (r"\bdirector\b", CanonicalRole.DIRECTOR),
]

# roles we actively pursue, in outreach priority order
PRIORITY_ROLES = [
    CanonicalRole.TPO,
    CanonicalRole.PLACEMENT_DIRECTOR,
    CanonicalRole.TRAINING_OFFICER,
    CanonicalRole.AI_CS_DEPT_HEAD,
    CanonicalRole.INNOVATION_CELL_HEAD,
    CanonicalRole.ECELL_HEAD,
    CanonicalRole.INCUBATION_HEAD,
    CanonicalRole.HOD,
    CanonicalRole.DEAN,
    CanonicalRole.DIRECTOR,
    CanonicalRole.PRINCIPAL,
    CanonicalRole.VICE_PRINCIPAL,
]


def canonical_role(designation: str | None) -> CanonicalRole:
    if not designation:
        return CanonicalRole.OTHER
    text = designation.lower()
    for pattern, role in _RULES:
        if re.search(pattern, text):
            return role
    return CanonicalRole.OTHER
