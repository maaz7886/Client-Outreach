"""Free-tier email verification: RFC-ish syntax + MX lookup. Deliberately no
SMTP-handshake probing — it is unreliable and gets sending IPs flagged.
Deeper verification happens naturally via bounce handling after first send."""

import re
from functools import lru_cache

import dns.resolver

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def valid_syntax(email: str) -> bool:
    return bool(EMAIL_RE.match(email or ""))


@lru_cache(maxsize=4096)
def domain_has_mx(domain: str, timeout: float = 5.0) -> bool | None:
    """True/False, or None when DNS itself failed (unknown, not invalid)."""
    try:
        resolver = dns.resolver.Resolver()
        resolver.lifetime = timeout
        answers = resolver.resolve(domain, "MX")
        return len(answers) > 0
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return False
    except Exception:
        return None


def check_email(email: str, mx_lookup=domain_has_mx) -> bool | None:
    """None = could not determine (kept, flagged); False = definitely bad."""
    if not valid_syntax(email):
        return False
    return mx_lookup(email.rsplit("@", 1)[1].lower())
