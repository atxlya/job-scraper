"""Record a live response as a test fixture.

Usage:
  uv run python scripts/record_fixture.py ADAPTER NAME METHOD URL [--json BODY] [--max-items 25]
      [--header 'Accept: application/json' ...] [--no-follow] [--keep REGEX]

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

from app.http.client import PoliteClient  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def trim(value, max_items: int):
    if isinstance(value, list):
        return [trim(v, max_items) for v in value[:max_items]]
    if isinstance(value, dict):
        return {k: trim(v, max_items) for k, v in value.items()}
    return value


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
    for prefix, uri in re.findall(rb'xmlns(?::(\w+))?="([^"]+)"', content):
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
    a = ap.parse_args()

    headers = dict(h.split(":", 1) for h in a.header)
    headers = {k.strip(): v.strip() for k, v in headers.items()}
    client = PoliteClient(min_interval_s=2.5)
    try:
        if a.method == "POST":
            resp = await client.post_json(
                a.url, json.loads(a.body or "{}"), headers={"Accept": "application/json", **headers}
            )
        else:
            resp = await client.get(
                a.url, headers=headers or None, follow_redirects=not a.no_follow
            )
    finally:
        await client.aclose()

    if a.no_follow:
        print(f"{resp.status_code} Location: {resp.headers.get('location', '')}")
        return

    folder = OUT / a.adapter
    folder.mkdir(parents=True, exist_ok=True)
    ctype = resp.headers.get("content-type", "")
    if "json" in ctype:
        path = folder / f"{a.name}.json"
        path.write_text(json.dumps(trim(resp.json(), a.max_items), indent=1, ensure_ascii=False))
    elif "xml" in ctype:
        path = folder / f"{a.name}.xml"
        path.write_bytes(trim_xml(resp.content, a.max_items, a.keep))
    else:
        path = folder / f"{a.name}.html"
        path.write_bytes(resp.content)
    print(f"{resp.status_code} {ctype} -> {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    asyncio.run(main())
