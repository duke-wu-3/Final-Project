"""Snapshot BrickLink price-guide averages for common part+color combinations.

    python scripts/fetch_bricklink_prices.py [how_many]    # default 300 most common combos + every combo used in tests

Price = quantity-weighted average price of NEW parts sold on BrickLink in the last 6 months
(falls back to current new listings, then used). Only reads the small summary at the top of each
price-guide page, one request per second. Needs data/bricklink_part_ids.csv (map_bricklink_ids.py).
Writes data/bricklink_prices.csv, which the app reads; the app never calls BrickLink itself.
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "bricklink_prices.csv"
UA = "Mozilla/5.0 (StudFinder class project; one-time price snapshot)"
BASES = ["6-month sales, new", "6-month sales, used", "for sale now, new", "for sale now, used"]


def fetch(url: str, max_bytes: int | None = None) -> str:
    """curl (system certificates); stops reading after max_bytes so we only take the summary."""
    p = subprocess.Popen(["curl", "-s", "-m", "25", "-A", UA, url], stdout=subprocess.PIPE)
    try:
        data = p.stdout.read(max_bytes) if max_bytes else p.stdout.read()
    finally:
        p.kill()
        p.wait()
        time.sleep(1.0)
    return data.decode("utf-8", "replace")


def id_item(bl_item: str) -> str | None:
    m = re.search(r"idItem[^0-9]{1,6}([0-9]+)", fetch(f"https://www.bricklink.com/v2/catalog/catalogitem.page?P={bl_item}"))
    return m.group(1) if m else None


def summary(item_id: str, bl_color: int) -> dict:
    html = fetch(f"https://www.bricklink.com/v2/catalog/catalogitem_pgtab.page?idItem={item_id}&idColor={bl_color}"
                 "&st=1&gm=0&gc=0&ei=0&prec=4&showflag=0&showbulk=0&currency=1", max_bytes=12000)
    start = html.find("background-color: #C0C0C0")
    seg = html[start: html.find("pcipgOddColumn", start)] if start >= 0 else ""
    cols = re.findall(r"pcipgSummaryTable.*?</TABLE>|\(unavailable\)", seg, re.S)
    out = {}
    for basis, col in zip(BASES, cols):
        q = re.search(r"Qty Avg Price:</TD><TD><b>US \$([\d.,]+)", col)
        n = re.search(r"(?:Times Sold|Total Lots):</TD><TD><b>([\d,]+)", col)
        if q and n:
            out[basis] = (float(q.group(1).replace(",", "")), int(n.group(1).replace(",", "")))
    # order of preference: what new parts actually sold for, then asking prices
    for basis in ("6-month sales, new", "for sale now, new", "6-month sales, used", "for sale now, used"):
        if basis in out and out[basis][0] > 0:
            return {"price": out[basis][0], "basis": basis, "count": out[basis][1]}
    return {}


def combos_used_in_tests(con: sqlite3.Connection) -> set[tuple[str, int]]:
    colors = {name: cid for cid, name in con.execute("SELECT id, name FROM colors")}
    found = set()
    for path in [ROOT / "docs" / "eval" / "results.json", ROOT / "docs" / "eval" / "sample_trace.json"]:
        for part, color in re.findall(r"\d+ x ([0-9a-z]+) .*?\(([^()]+)\)(?: \[|\")", path.read_text()):
            if color in colors:
                found.add((part, colors[color]))
    for f in (ROOT / "logs" / "friend_tests").glob("*.json"):
        s = json.loads(f.read_text()).get("studfinder_session") or {}
        found |= {(i["part_num"], i["color_id"]) for i in s.get("items", [])}
    return found


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    con = sqlite3.connect(ROOT / "data" / "catalog.db")
    with open(ROOT / "data" / "bricklink_part_ids.csv", encoding="utf-8") as f:
        bl_ids = {r["rb_part_num"]: r["bl_item_id"] for r in csv.DictReader(f)}
    bl_color = {cid: bl for cid, bl in con.execute("SELECT id, bl_id FROM colors WHERE bl_id IS NOT NULL")}
    combos = [(p, c) for p, c in con.execute(
        "SELECT pc.part_num, pc.color_id FROM part_colors pc JOIN parts p ON p.part_num = pc.part_num "
        "WHERE p.printed = 0 ORDER BY pc.n_sets DESC LIMIT ?", (n * 2,)) if p in bl_ids and c in bl_color][:n]
    combos += [c for c in sorted(combos_used_in_tests(con)) if c not in combos and c[0] in bl_ids and c[1] in bl_color]

    rows, fails = [], []
    if OUT.exists():  # extend an earlier snapshot instead of starting over
        with open(OUT, encoding="utf-8") as f:
            old = list(csv.reader(f))[1:]
        rows = [tuple(r) for r in old]
        have = {(r[0], int(r[1])) for r in old}
        combos = [c for c in combos if c not in have]
        print(f"{len(rows)} combos already priced; fetching {len(combos)} more", flush=True)
    item_ids: dict[str, str | None] = {}
    today = time.strftime("%Y-%m-%d")
    for i, (part, color) in enumerate(combos, 1):
        bl = bl_ids[part]
        if bl not in item_ids:
            item_ids[bl] = id_item(bl)
        s = summary(item_ids[bl], bl_color[color]) if item_ids[bl] else {}
        if s:
            rows.append((part, color, bl, bl_color[color], f"{s['price']:.4f}", s["basis"], s["count"], today))
        else:
            fails.append(f"{part}/{color}")
        if i % 25 == 0:
            print(f"priced {len(rows)} of {i}/{len(combos)}", flush=True)
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rb_part_num", "rb_color_id", "bl_item_id", "bl_color_id", "price_usd", "basis", "count", "fetched"])
        w.writerows(rows)
    print(f"\n{len(rows)} combos priced in total; no price for {len(fails)} of the {len(combos)} new: {fails[:15]}")


if __name__ == "__main__":
    main()
