"""Turn a parts list into BrickLink's Wanted List upload format (XML)."""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from xml.sax.saxutils import escape

from .state import Session

BL_IDS = Path(__file__).resolve().parents[1] / "data" / "bricklink_part_ids.csv"


@lru_cache(maxsize=1)
def bricklink_ids() -> dict[str, str]:
    """Rebrickable part number -> BrickLink item number, checked against BrickLink's catalog
    (scripts/map_bricklink_ids.py). Most are the same; a few differ, e.g. 3069b -> 3069, 6141 -> 4073."""
    if not BL_IDS.exists():
        return {}
    with open(BL_IDS, encoding="utf-8") as f:
        return {r["rb_part_num"]: r["bl_item_id"] for r in csv.DictReader(f)}


def bricklink_xml(s: Session) -> tuple[str, list[str]]:
    """Returns (xml, skipped). Items whose color has no BrickLink id are skipped."""
    lines = ["<INVENTORY>"]
    skipped = []
    for it in s.items.values():
        if it.bl_color_id is None:
            skipped.append(f"{it.part_num} {it.name} in {it.color}")
            continue
        lines += [
            "  <ITEM>",
            "    <ITEMTYPE>P</ITEMTYPE>",
            f"    <ITEMID>{escape(bricklink_ids().get(it.part_num, it.part_num))}</ITEMID>",
            f"    <COLOR>{it.bl_color_id}</COLOR>",
            f"    <MINQTY>{it.qty}</MINQTY>",
            f"    <REMARKS>{escape(it.section)}</REMARKS>",
            "  </ITEM>",
        ]
    lines.append("</INVENTORY>")
    return "\n".join(lines), skipped
