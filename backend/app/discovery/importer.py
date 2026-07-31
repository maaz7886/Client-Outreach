"""College discovery via open datasets.

AICTE and NIRF both publish downloadable institution lists (CSV/Excel). This
importer takes any CSV with at least name/city/state columns (flexible header
matching), normalizes, dedups against the DB, and inserts College rows with
the file recorded as discovery_source."""

import csv
import io
import re

from sqlalchemy.orm import Session

from app.models import College, CollegeType

HEADER_ALIASES = {
    "name": {"name", "college name", "institute name", "institution name", "college"},
    "city": {"city", "district", "town"},
    "state": {"state", "state name"},
    "website": {"website", "url", "web site", "website url"},
    "naac_grade": {"naac", "naac grade"},
    "nirf_rank": {"nirf", "nirf rank", "rank"},
    "affiliation": {"affiliation", "university", "affiliated to"},
    "college_type": {"type", "institution type", "college type"},
}

_TYPE_MAP = {
    "government": CollegeType.GOVERNMENT,
    "govt": CollegeType.GOVERNMENT,
    "private": CollegeType.PRIVATE,
    "autonomous": CollegeType.AUTONOMOUS,
    "deemed": CollegeType.DEEMED,
}


def normalize_name(name: str) -> str:
    """Stable dedup key: lowercase, punctuation stripped, whitespace collapsed."""
    cleaned = re.sub(r"[^\w\s]", " ", name.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _map_headers(fieldnames: list[str]) -> dict[str, str]:
    mapping = {}
    for raw in fieldnames:
        key = raw.strip().lower()
        for canonical, aliases in HEADER_ALIASES.items():
            if key in aliases and canonical not in mapping:
                mapping[canonical] = raw
    return mapping


def import_colleges_csv(db: Session, csv_text: str, source_label: str) -> dict:
    """Returns {"inserted": n, "skipped_duplicates": n, "skipped_invalid": n}."""
    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames:
        return {"inserted": 0, "skipped_duplicates": 0, "skipped_invalid": 0}
    headers = _map_headers(list(reader.fieldnames))
    if "name" not in headers or "state" not in headers:
        raise ValueError(
            f"CSV must contain a college-name and state column; found {reader.fieldnames}"
        )

    existing = {
        (norm, city.lower())
        for norm, city in db.query(College.normalized_name, College.city).all()
    }
    inserted = dup = invalid = 0
    for row in reader:
        name = (row.get(headers["name"]) or "").strip()
        city = (row.get(headers.get("city", ""), "") or "").strip() or "UNKNOWN"
        state = (row.get(headers["state"]) or "").strip()
        if not name or not state:
            invalid += 1
            continue
        key = (normalize_name(name), city.lower())
        if key in existing:
            dup += 1
            continue
        existing.add(key)

        raw_type = (row.get(headers.get("college_type", ""), "") or "").strip().lower()
        nirf_raw = (row.get(headers.get("nirf_rank", ""), "") or "").strip()
        db.add(
            College(
                name=name,
                normalized_name=key[0],
                city=city,
                state=state,
                website=(row.get(headers.get("website", ""), "") or "").strip() or None,
                naac_grade=(row.get(headers.get("naac_grade", ""), "") or "").strip() or None,
                nirf_rank=int(nirf_raw) if nirf_raw.isdigit() else None,
                affiliation=(row.get(headers.get("affiliation", ""), "") or "").strip() or None,
                college_type=next(
                    (t for k, t in _TYPE_MAP.items() if k in raw_type), CollegeType.UNKNOWN
                ),
                discovery_source=source_label,
            )
        )
        inserted += 1
    db.commit()
    return {"inserted": inserted, "skipped_duplicates": dup, "skipped_invalid": invalid}
