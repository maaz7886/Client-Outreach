"""Confidence rubric (spec §Verification Rules), implemented as a pure
function over the set of source types citing a contact:

  95-100  verified from official website (incl. mandatory-disclosure PDF)
  80-95   multiple trusted sources agree
  60-80   enrichment API + one other source
  <60     single weak source -> NEEDS_MANUAL_REVIEW
"""

from app.models import SourceType

OFFICIAL = {SourceType.OFFICIAL_WEBSITE, SourceType.MANDATORY_DISCLOSURE_PDF}
TRUSTED = OFFICIAL | {SourceType.GOVT_DATABASE, SourceType.PUBLIC_DOCUMENT}


def confidence_score(source_types: set[SourceType]) -> int:
    if not source_types:
        return 0
    if source_types & OFFICIAL:
        return min(100, 95 + (3 if len(source_types) > 1 else 0))
    if len(source_types & TRUSTED) >= 2:
        return 85
    if SourceType.ENRICHMENT_API in source_types and len(source_types) >= 2:
        return 70
    if len(source_types) >= 2:
        return 65
    return 50
