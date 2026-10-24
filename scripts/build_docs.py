"""Build the self-contained report.html and slides.html (every image embedded).

    python scripts/build_docs.py

Reads docs/report_src.html and docs/slides_src.html, inlines each <img src="..."> from docs/
as a data URI, and writes report.html and slides.html to the repo root.
"""

from __future__ import annotations

import base64
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".svg": "image/svg+xml"}


def inline(html: str) -> str:
    def repl(m: re.Match) -> str:
        path = DOCS / m.group(2)
        if not path.exists():
            raise FileNotFoundError(path)
        data = base64.b64encode(path.read_bytes()).decode()
        return f'{m.group(1)}"data:{TYPES[path.suffix.lower()]};base64,{data}"'

    return re.sub(r'(<img[^>]*?\bsrc=)"(?!data:|https?:)([^"]+)"', repl, html)


def main() -> None:
    for name in ("report", "slides"):
        out = ROOT / f"{name}.html"
        out.write_text(inline((DOCS / f"{name}_src.html").read_text(encoding="utf-8")), encoding="utf-8")
        pending = (DOCS / f"{name}_src.html").read_text().count('class="pending"')
        print(f"{out.name}: {out.stat().st_size / 1e6:.1f} MB, {pending} pending slots")


if __name__ == "__main__":
    main()
