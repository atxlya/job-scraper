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


_LEVER_HOSTS = {"jobs.lever.co"}  # EU boards use api.eu.lever.co, not supported yet
_GREENHOUSE_HOSTS = {
    "boards.greenhouse.io",
    "job-boards.greenhouse.io",
    "job-boards.eu.greenhouse.io",
}


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

    if host in _LEVER_HOSTS and parts:
        return Detected("lever", {"site": parts[0]}, parts[0])
    if host == "api.lever.co" and parts[:2] == ["v0", "postings"] and len(parts) > 2:
        return Detected("lever", {"site": parts[2]}, parts[2])

    if host in _GREENHOUSE_HOSTS and parts:
        board = parse_qs(u.query).get("for", [""])[0] if parts[0] == "embed" else parts[0]
        return Detected("greenhouse", {"board": board}, board) if board else None
    if host == "boards-api.greenhouse.io" and parts[:2] == ["v1", "boards"] and len(parts) > 2:
        return Detected("greenhouse", {"board": parts[2]}, parts[2])

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
