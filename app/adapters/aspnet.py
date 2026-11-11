"""ASP.NET WebForms "postbacks": the page posts its own form back to change page.

Tech Mahindra, Jio and Reliance page this way. A rejected postback (stale __VIEWSTATE)
answers 302 to /error.aspx, so anything but a 200 is a ParseError, never "no jobs".
"""

import re

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from app.adapters.base import ParseError
from app.http.client import PoliteClient

_TARGET = re.compile(r"__doPostBack\(\s*'([^']*)'")
_SHOWN = re.compile(r"Showing\s+(\d+)\s+of\s+(\d+)\s+Pages")
_FIELD_TYPES = {"", "hidden", "text"}


def form_fields(tree: HTMLParser) -> dict[str, str]:
    """The values a browser would post: hidden and text inputs, and each select's choice."""
    fields: dict[str, str] = {}
    for node in tree.css("input[name]"):
        if (node.attributes.get("type") or "").lower() in _FIELD_TYPES:
            fields[node.attributes["name"]] = node.attributes.get("value") or ""
    for select in tree.css("select[name]"):
        option = select.css_first("option[selected]") or select.css_first("option")
        value = option.attributes.get("value") if option is not None else None
        fields[select.attributes["name"]] = value if value is not None else ""
    return fields


def postback_target(href: str) -> str:
    """The control name in "javascript:__doPostBack('X','')"."""
    m = _TARGET.search(href or "")
    if m is None:
        raise ParseError(f"not a postback link: {href!r}")
    return m[1]


async def postback(
    client: PoliteClient,
    url: str,
    tree: HTMLParser,
    target: str,
    extra: dict[str, str] | None = None,
) -> HTMLParser:
    data = form_fields(tree) | {"__EVENTTARGET": target, "__EVENTARGUMENT": ""} | (extra or {})
    resp = await client.post_form(url, data, follow_redirects=False)
    if resp.status_code != 200:
        location = resp.headers.get("Location", "")
        raise ParseError(f"postback {target} answered {resp.status_code} {location}".strip())
    return HTMLParser(resp.text)


async def get_page(client: PoliteClient, url: str) -> HTMLParser:
    """GET a WebForms page. These sites redirect errors to /error.aspx, so a 3xx is a
    ParseError and the redirect is never followed."""
    resp = await client.get(url, follow_redirects=False)
    if 300 <= resp.status_code < 400:
        location = resp.headers.get("Location", "")
        raise ParseError(f"{url} redirected to {location!r}")
    resp.raise_for_status()
    return HTMLParser(resp.text)


def pages_shown(tree: HTMLParser) -> tuple[int, int] | None:
    """Jio and Reliance print "Showing 2 of 4 Pages" under the list."""
    body = tree.body
    m = _SHOWN.search(body.text() if body is not None else "")
    return (int(m[1]), int(m[2])) if m else None
