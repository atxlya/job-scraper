"""Recognise a careers URL as a platform we have an adapter for (plan D2)."""

import re
from typing import NamedTuple
from urllib.parse import parse_qs, urlparse


class Detected(NamedTuple):
    adapter: str
    config: dict
    key_hint: str


_WORKDAY_HOST = re.compile(r"^(?P<tenant>[a-z0-9-]+)\.wd\d+\.myworkdayjobs\.com$")
_LANG = re.compile(r"^[a-z]{2}(-[A-Z]{2})?$")
_ORACLE_PATH = re.compile(r"^/hcmUI/CandidateExperience/[^/]+/sites/(?P<site>[^/?#]+)")


def _registrable(host: str) -> str:
    return ".".join(host.split(".")[-2:])


def detect(url: str) -> Detected | None:
    u = urlparse(url.strip())
    host = (u.hostname or "").lower()
    if u.scheme not in ("http", "https") or not host:
        return None
    parts = [p for p in u.path.split("/") if p]

    if m := _WORKDAY_HOST.match(host):
        if parts and _LANG.match(parts[0]):
            parts = parts[1:]
        if not parts:
            return None
        tenant = m["tenant"]
        return Detected("workday", {"host": host, "tenant": tenant, "site": parts[0]}, tenant)

    if m := _ORACLE_PATH.match(u.path):
        return Detected("oracle_hcm", {"host": host, "site": m["site"]}, host.split(".")[0])

    if host.endswith(".eightfold.ai"):
        sub = host.split(".")[0]
        return Detected("eightfold", {"host": host, "domain": f"{sub}.com"}, sub)
    looks_eightfold = parts[:1] == ["careers"] and (
        "pid" in parse_qs(u.query) or "job" in parts[1:2]
    )
    if looks_eightfold:
        domain = _registrable(host)
        return Detected("eightfold", {"host": host, "domain": domain}, domain.split(".")[0])
    return None
