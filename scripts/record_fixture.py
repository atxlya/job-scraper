"""Record a live response as a test fixture.

Usage:
  uv run python scripts/record_fixture.py ADAPTER NAME METHOD URL [--json BODY] [--max-items 25]
      [--header 'Accept: application/json' ...] [--no-follow] [--keep REGEX]
      [--form K=V ...] [--step SPEC ...] [--drop-keys a,b,c]

--form K=V: with POST, send a form body (application/x-www-form-urlencoded) instead of JSON.
--step SPEC: ASP.NET postback on the previous answer (repeatable; the last answer is saved).
  SPEC is TARGET|K=V|K=V... where TARGET is a control name, label=TEXT (the postback link
  with that text) or select$=SUFFIX:VALUE (the select whose name ends with SUFFIX, set to VALUE).
--drop-keys a,b,c: remove these keys at any depth of a JSON answer (e.g. employee contacts).

--no-follow: don't follow redirects; print the status and Location instead of saving.
XML responses are saved as NAME.xml; a sitemap <urlset> or an RSS <rss> is cut to the
items whose <loc>/<link> match --keep (default: all), then to the first --max-items.

Goes through PoliteClient, so robots.txt and pacing apply. JSON lists longer
than --max-items are cut down to keep fixtures small; nothing else is edited.
"""

import argparse
import asyncio
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from selectolax.lexbor import LexborHTMLParser as HTMLParser  # noqa: E402

from app.adapters import aspnet  # noqa: E402
from app.http.client import PoliteClient  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def trim(value, max_items: int):
    if isinstance(value, list):
        return [trim(v, max_items) for v in value[:max_items]]
    if isinstance(value, dict):
        return {k: trim(v, max_items) for k, v in value.items()}
    return value


def drop_keys(value, keys: set[str]):
    if isinstance(value, list):
        return [drop_keys(v, keys) for v in value]
    if isinstance(value, dict):
        return {k: drop_keys(v, keys) for k, v in value.items() if k not in keys}
    return value


async def run_step(client: PoliteClient, url: str, html: str, spec: str):
    """One postback on the page `html`; returns the answer's HTML."""
    target, *pairs = spec.split("|")
    extra = dict(p.split("=", 1) for p in pairs)
    tree = HTMLParser(html)
    if target.startswith("label="):
        text = target[len("label=") :]
        links = tree.css('a[href^="javascript:__doPostBack"]')
        link = next((a for a in links if a.text(strip=True) == text), None)
        if link is None:
            raise SystemExit(f"no postback link labelled {text!r}")
        target = aspnet.postback_target(link.attributes["href"])
    elif target.startswith("select$="):
        suffix, value = target[len("select$=") :].split(":", 1)
        select = next(
            (s for s in tree.css("select[name]") if s.attributes["name"].endswith(suffix)), None
        )
        if select is None:
            raise SystemExit(f"no select ending {suffix!r}")
        target = select.attributes["name"]
        extra[target] = value
    data = aspnet.form_fields(tree) | {"__EVENTTARGET": target, "__EVENTARGUMENT": ""} | extra
    resp = await client.post_form(url, data, follow_redirects=False)
    if resp.status_code != 200:
        raise SystemExit(f"postback {target} answered {resp.status_code}")
    return resp.text  # the raw answer, not a re-serialised tree


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def trim_xml(content: bytes, max_items: int, keep: str) -> bytes:
    """Cut a sitemap or RSS feed to the wanted items; any other XML is saved as is."""
    root = ET.fromstring(content)
    name = local(root.tag)
    if name == "urlset":
        parent, item, key = root, "url", "loc"
    elif name == "rss":
        channel = next((c for c in root if local(c.tag) == "channel"), None)
        if channel is None:
            return content
        parent, item, key = channel, "item", "link"
    else:
        return content
    pattern = re.compile(keep)
    kept = 0
    for child in list(parent):
        if local(child.tag) != item:
            continue
        text = next((c.text or "" for c in child if local(c.tag) == key), "")
        if kept >= max_items or not pattern.search(text.strip()):
            parent.remove(child)
        else:
            kept += 1
    # Only the root's own declarations: a nested xmlns="..." (e.g. an XHTML link inside a
    # sitemap <url>) must not take over the default prefix.
    root_tag = re.search(rb"<(?![?!])[^>]*>", content)
    for prefix, uri in re.findall(rb'xmlns(?::(\w+))?="([^"]+)"', root_tag[0] if root_tag else b""):
        ET.register_namespace(prefix.decode(), uri.decode())
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("adapter")
    ap.add_argument("name")
    ap.add_argument("method", choices=["GET", "POST"])
    ap.add_argument("url")
    ap.add_argument("--json", dest="body")
    ap.add_argument("--max-items", type=int, default=25)
    ap.add_argument("--header", action="append", default=[], help="K: V, repeatable")
    ap.add_argument("--no-follow", action="store_true", help="show status and Location only")
    ap.add_argument("--keep", default="", help="XML: keep only items whose loc/link matches")
    ap.add_argument("--form", action="append", default=[], help="POST form field K=V")
    ap.add_argument("--step", action="append", default=[], help="ASP.NET postback, see above")
    ap.add_argument("--drop-keys", default="", help="JSON: keys to remove, comma-separated")
    a = ap.parse_args()

    headers = dict(h.split(":", 1) for h in a.header)
    headers = {k.strip(): v.strip() for k, v in headers.items()}
    client = PoliteClient(min_interval_s=2.5)
    body = None
    try:
        if a.method == "POST" and a.form:
            form = dict(f.split("=", 1) for f in a.form)
            resp = await client.post_form(
                a.url, form, headers=headers or None, follow_redirects=not a.no_follow
            )
        elif a.method == "POST":
            resp = await client.post_json(
                a.url,
                json.loads(a.body or "{}"),
                headers={"Accept": "application/json", **headers},
                follow_redirects=not a.no_follow,
            )
        else:
            resp = await client.get(
                a.url, headers=headers or None, follow_redirects=not a.no_follow
            )
        if a.step:
            body = resp.text
            for spec in a.step:
                body = await run_step(client, a.url, body, spec)
    finally:
        await client.aclose()

    if a.no_follow:
        print(f"{resp.status_code} Location: {resp.headers.get('location', '')}")
        return

    folder = OUT / a.adapter
    folder.mkdir(parents=True, exist_ok=True)
    if body is not None:
        path = folder / f"{a.name}.html"
        path.write_text(body, encoding="utf-8")
        print(f"postback x{len(a.step)} -> {path} ({path.stat().st_size} bytes)")
        return
    ctype = resp.headers.get("content-type", "")
    if "json" in ctype:
        path = folder / f"{a.name}.json"
        data = drop_keys(resp.json(), {k for k in a.drop_keys.split(",") if k})
        path.write_text(json.dumps(trim(data, a.max_items), indent=1, ensure_ascii=False))
    elif "xml" in ctype:
        path = folder / f"{a.name}.xml"
        path.write_bytes(trim_xml(resp.content, a.max_items, a.keep))
    else:
        path = folder / f"{a.name}.html"
        path.write_bytes(resp.content)
    print(f"{resp.status_code} {ctype} -> {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    asyncio.run(main())
