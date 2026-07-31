"""HTML → clean text, and homepage → candidate research links."""

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

# link keywords that identify pages worth reading, in priority order
PAGE_KEYWORDS = [
    ("placement", 1),
    ("training", 1),
    ("mandatory-disclosure", 1),
    ("disclosure", 1),
    ("about", 2),
    ("department", 2),
    ("computer", 2),
    ("innovation", 2),
    ("incubation", 2),
    ("e-cell", 2),
    ("entrepreneur", 2),
    ("achievement", 3),
    ("news", 3),
    ("event", 3),
    ("nirf", 3),
    ("naac", 3),
]

MAX_TEXT_CHARS = 20_000


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()[:MAX_TEXT_CHARS]


def candidate_links(homepage_html: str, base_url: str, limit: int = 8) -> list[str]:
    """Rank same-site links from the homepage by research value."""
    soup = BeautifulSoup(homepage_html, "html.parser")
    base_domain = urlparse(base_url).netloc
    scored: dict[str, int] = {}
    for a in soup.find_all("a", href=True):
        url = urljoin(base_url, a["href"].split("#")[0])
        parsed = urlparse(url)
        if parsed.netloc != base_domain or parsed.scheme not in ("http", "https"):
            continue
        haystack = (parsed.path + " " + a.get_text(" ", strip=True)).lower()
        for keyword, priority in PAGE_KEYWORDS:
            if keyword in haystack:
                score = 10 - priority
                if scored.get(url, 0) < score:
                    scored[url] = score
                break
    ranked = sorted(scored, key=lambda u: -scored[u])
    return ranked[:limit]
