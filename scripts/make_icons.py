"""Home-screen icons for the dashboard, drawn from the same artwork as web/public/favicon.svg.

python scripts/make_icons.py [path-to-chrome]

Writes web/public/icons/*.png by rendering SVG with headless Chrome (no image library is a
dependency of this project). Run it again only if the logo changes; the PNGs are committed.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "public" / "icons"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
BLUE = "#2F5BEA"  # --accent in web/src/index.css, the favicon's tile

# The bag from favicon.svg, on a 32-unit canvas. Its box is x 7–25, y 7–24.
GLYPH = (
    '<g fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" '
    'stroke-linejoin="round"><rect x="7" y="11" width="18" height="13" rx="2"/>'
    '<path d="M12 11V9a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></g>'
)


def svg(tile: str, glyph_scale: float = 1.0) -> str:
    g = GLYPH
    if glyph_scale != 1.0:  # shrink around the glyph's centre (16, 15.5)
        g = f'<g transform="translate(16 16) scale({glyph_scale}) translate(-16 -15.5)">{GLYPH}</g>'
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">{tile}{g}</svg>'


ROUNDED = f'<rect width="32" height="32" rx="8" fill="{BLUE}"/>'  # same tile as the favicon
SQUARE = f'<rect width="32" height="32" fill="{BLUE}"/>'  # the OS cuts its own shape

ICONS = {
    # "any": the favicon as it is, with transparent corners.
    "icon-192.png": (192, svg(ROUNDED)),
    "icon-512.png": (512, svg(ROUNDED)),
    # "maskable": a full square; Android may crop it to a circle, so the bag stays inside
    # the middle 80% (its corners reach about 30% of the width from the centre).
    "icon-maskable-512.png": (512, svg(SQUARE, glyph_scale=0.8)),
    # iOS rounds the corners itself and shows transparency as black, so a full square.
    "apple-touch-icon.png": (180, svg(SQUARE)),
}


def render(chrome: str, size: int, markup: str, dest: Path, tmp: Path) -> None:
    page = tmp / f"{dest.stem}.html"
    page.write_text(
        "<!doctype html><style>html,body{margin:0;background:transparent}"
        f"svg{{display:block;width:{size}px;height:{size}px}}</style>{markup}"
    )
    subprocess.run(
        [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--force-device-scale-factor=1",
            "--default-background-color=00000000",
            f"--window-size={size},{size}",
            f"--screenshot={dest}",
            page.as_uri(),
        ],
        check=True,
        capture_output=True,
    )


def main() -> None:
    chrome = sys.argv[1] if len(sys.argv) > 1 else CHROME
    if not Path(chrome).exists() and not shutil.which(chrome):
        sys.exit(f"Chrome not found at {chrome}; pass its path as the first argument")
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as t:
        for name, (size, markup) in ICONS.items():
            render(chrome, size, markup, OUT / name, Path(t))
            print(f"{name}: {size}×{size}")


if __name__ == "__main__":
    main()
