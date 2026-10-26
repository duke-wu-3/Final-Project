"""Turn a parts list into BrickLink's Wanted List upload format (XML)."""

from __future__ import annotations

from xml.sax.saxutils import escape

from .state import Session


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
            f"    <ITEMID>{escape(it.part_num)}</ITEMID>",
            f"    <COLOR>{it.bl_color_id}</COLOR>",
            f"    <MINQTY>{it.qty}</MINQTY>",
            f"    <REMARKS>{escape(it.section)}</REMARKS>",
            "  </ITEM>",
        ]
    lines.append("</INVENTORY>")
    return "\n".join(lines), skipped
