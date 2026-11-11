"""Small text helpers shared by adapters: plain text to HTML, epoch-ms dates, sections."""

import html
import re
from datetime import UTC, datetime

_BULLET = re.compile(r"^\s*[-•*]\s+")
_MS = re.compile(r"-?\d+")


def text_to_html(text: str | None) -> str | None:
    """Plain text (Apple, IBM) to simple HTML: blank lines split blocks, bullet runs
    become lists, other line runs become one paragraph with <br> between lines."""
    if not text or not text.strip():
        return None
    out: list[str] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        run: list[str] = []
        items: list[str] = []
        for line in lines:
            if _BULLET.match(line):
                if run:
                    out.append(f"<p>{'<br>'.join(run)}</p>")
                    run = []
                items.append(html.escape(_BULLET.sub("", line)))
            else:
                if items:
                    out.append("<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>")
                    items = []
                run.append(html.escape(line))
        if run:
            out.append(f"<p>{'<br>'.join(run)}</p>")
        if items:
            out.append("<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>")
    return "".join(out)


def from_ms(ms: int | str | None) -> datetime | None:
    """Epoch milliseconds (also as digits, or Microsoft's "/Date(ms)/") to UTC."""
    if ms is None or ms == "":
        return None
    if isinstance(ms, str):
        m = _MS.search(ms)
        if not m:
            return None
        ms = int(m.group())
    return datetime.fromtimestamp(ms / 1000, UTC)


def join_sections(parts: list[tuple[str | None, str | None]]) -> str | None:
    """(heading, html) pairs to one HTML string, skipping blank bodies."""
    out = []
    for heading, body in parts:
        if not body or not body.strip():
            continue
        out.append(f"<h3>{html.escape(heading)}</h3>{body}" if heading else body)
    return "\n".join(out) or None
