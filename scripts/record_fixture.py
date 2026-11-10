"""Record a live response as a test fixture.

Usage:
  uv run python scripts/record_fixture.py ADAPTER NAME METHOD URL [--json BODY] [--max-items 25]

Goes through PoliteClient, so robots.txt and pacing apply. JSON lists longer
than --max-items are cut down to keep fixtures small; nothing else is edited.
"""

import argparse
import asyncio
import json
from pathlib import Path

from app.http.client import PoliteClient

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def trim(value, max_items: int):
    if isinstance(value, list):
        return [trim(v, max_items) for v in value[:max_items]]
    if isinstance(value, dict):
        return {k: trim(v, max_items) for k, v in value.items()}
    return value


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("adapter")
    ap.add_argument("name")
    ap.add_argument("method", choices=["GET", "POST"])
    ap.add_argument("url")
    ap.add_argument("--json", dest="body")
    ap.add_argument("--max-items", type=int, default=25)
    a = ap.parse_args()

    client = PoliteClient(min_interval_s=2.5)
    try:
        if a.method == "POST":
            resp = await client.post_json(
                a.url, json.loads(a.body or "{}"), headers={"Accept": "application/json"}
            )
        else:
            resp = await client.get(a.url)
    finally:
        await client.aclose()

    folder = OUT / a.adapter
    folder.mkdir(parents=True, exist_ok=True)
    ctype = resp.headers.get("content-type", "")
    if "json" in ctype:
        path = folder / f"{a.name}.json"
        path.write_text(json.dumps(trim(resp.json(), a.max_items), indent=1, ensure_ascii=False))
    else:
        path = folder / f"{a.name}.html"
        path.write_bytes(resp.content)
    print(f"{resp.status_code} {ctype} -> {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    asyncio.run(main())
