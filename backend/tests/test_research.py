"""Phase 3 tests: polite fetcher behavior (robots, rate limit, retries),
CSV importer, and the research engine's grounding guarantees — all offline
via httpx.MockTransport and a fake LLM."""

import json

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.discovery.importer import import_colleges_csv, normalize_name
from app.models import Base, College, ResearchStatus
from app.research.engine import RESEARCH_FIELDS, research_college
from app.research.extractor import candidate_links, html_to_text
from app.research.fetcher import FetchBlocked, FetchFailed, PoliteFetcher


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def make_fetcher(routes: dict[str, httpx.Response | Exception], sleeps: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        result = routes.get(str(request.url))
        if isinstance(result, Exception):
            raise result
        if result is None:
            return httpx.Response(404)
        return result

    return PoliteFetcher(
        delay_seconds=1.5,
        transport=httpx.MockTransport(handler),
        sleep=(sleeps.append if sleeps is not None else lambda s: None),
    )


# ---------- fetcher ----------

def test_robots_disallow_blocks_fetch():
    fetcher = make_fetcher(
        {
            "https://college.example/robots.txt": httpx.Response(
                200, text="User-agent: *\nDisallow: /private/"
            ),
            "https://college.example/private/list.html": httpx.Response(200, text="secret"),
        }
    )
    with pytest.raises(FetchBlocked):
        fetcher.get("https://college.example/private/list.html")


def test_rate_limit_sleeps_between_same_domain_requests():
    sleeps = []
    fetcher = make_fetcher(
        {
            "https://college.example/robots.txt": httpx.Response(404),
            "https://college.example/a": httpx.Response(200, text="a"),
            "https://college.example/b": httpx.Response(200, text="b"),
        },
        sleeps=sleeps,
    )
    fetcher.get("https://college.example/a")
    fetcher.get("https://college.example/b")
    assert sleeps and sleeps[-1] > 0  # second hit waited for the politeness delay


def test_retry_then_give_up_on_5xx():
    fetcher = make_fetcher(
        {
            "https://college.example/robots.txt": httpx.Response(404),
            "https://college.example/down": httpx.Response(503),
        }
    )
    with pytest.raises(FetchFailed):
        fetcher.get("https://college.example/down")


# ---------- extractor ----------

def test_html_to_text_strips_scripts():
    text = html_to_text("<html><script>evil()</script><p>Placement  Cell</p></html>")
    assert "evil" not in text and "Placement Cell" in text


def test_candidate_links_prefers_placement_and_stays_on_site():
    html = """
    <a href="/placement">Placements</a>
    <a href="/news">News</a>
    <a href="https://other.example/spam">Elsewhere</a>
    """
    links = candidate_links(html, "https://college.example/")
    assert links[0] == "https://college.example/placement"
    assert all("other.example" not in u for u in links)


# ---------- importer ----------

CSV = """Institute Name,District,State Name,Website,Type
ABC College of Engineering,Pune,Maharashtra,https://abc.example,Private
ABC College of Engineering,Pune,Maharashtra,https://abc.example,Private
XYZ Institute,Nagpur,Maharashtra,,Government
,Nowhere,Maharashtra,,
"""


def test_import_colleges_csv(db):
    result = import_colleges_csv(db, CSV, source_label="test.csv")
    assert result == {"inserted": 2, "skipped_duplicates": 1, "skipped_invalid": 1}
    abc = db.query(College).filter_by(city="Pune").one()
    assert abc.normalized_name == normalize_name("ABC College of Engineering")
    assert abc.discovery_source == "test.csv"


# ---------- research engine ----------

class FakeLLM:
    name = "fake"

    def __init__(self, payload: dict):
        self._payload = payload

    def complete(self, system, user, *, max_tokens=2048):
        return "```json\n" + json.dumps(self._payload) + "\n```"


def _college_with_site(db) -> College:
    college = College(
        name="ABC College",
        normalized_name="abc college",
        city="Pune",
        state="Maharashtra",
        website="https://college.example/",
    )
    db.add(college)
    db.commit()
    return college


SITE = {
    "https://college.example/robots.txt": httpx.Response(404),
    "https://college.example/": httpx.Response(
        200,
        text='<a href="/placement">Placement Cell</a><p>ABC College, est 1985</p>',
        headers={"content-type": "text/html"},
    ),
    "https://college.example/placement": httpx.Response(
        200,
        text="<p>Placement cell conducts AI workshops with industry.</p>",
        headers={"content-type": "text/html"},
    ),
}


def test_research_college_stores_grounded_summary(db):
    college = _college_with_site(db)
    payload = {f: {"value": "NOT_FOUND", "source_url": None} for f in RESEARCH_FIELDS}
    payload["placement_activities"] = {
        "value": "Runs AI workshops with industry.",
        "source_url": "https://college.example/placement",
    }
    # hallucinated citation: URL we never fetched -> must be dropped
    payload["ai_initiatives"] = {
        "value": "Invented fact.",
        "source_url": "https://wikipedia.org/fake",
    }

    record = research_college(db, college, make_fetcher(SITE), FakeLLM(payload))

    assert record.status is ResearchStatus.DONE
    assert record.summary["placement_activities"]["value"].startswith("Runs AI")
    assert record.summary["ai_initiatives"]["value"] == "NOT_FOUND"  # guard worked
    assert "https://college.example/placement" in record.source_urls


def test_research_college_marks_unavailable_site(db):
    college = _college_with_site(db)
    routes = {"https://college.example/robots.txt": httpx.Response(404)}  # homepage 404s
    record = research_college(db, college, make_fetcher(routes), FakeLLM({}))
    assert record.status is ResearchStatus.WEBSITE_UNAVAILABLE
    assert record.retry_count == 1
