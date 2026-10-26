"""Check the most-used parts against BrickLink's catalog and record BrickLink's item number
where it differs from Rebrickable's (e.g. Rebrickable 3069b -> BrickLink 3069, 6141 -> 4073).

    python scripts/map_bricklink_ids.py [how_many]     # default: 350 most common parts, ~1 request/second

Writes data/bricklink_part_ids.csv, which studfinder/export.py uses for the Wanted List.
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
import sys
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "bricklink_part_ids.csv"
KNOWN = {"6141": ["4073"], "6143": ["3941"], "3794b": ["15573", "3794"], "4032b": ["4032"]}


def bl_title(item: str) -> str:
    """BrickLink's name for an item number, or "" if BrickLink doesn't know that number.
    Uses curl (system certificates); BrickLink redirects unknown numbers to a not-found page."""
    url = f"https://www.bricklink.com/v2/catalog/catalogitem.page?P={item}"
    try:
        r = subprocess.run(["curl", "-s", "-m", "20", "-A", "Mozilla/5.0 (StudFinder class project; one-time ID check)",
                            "-w", "\\n%{http_code}", url], capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return ""
    finally:
        time.sleep(1.0)
    body, _, code = r.stdout.rpartition("\n")
    if code.strip() != "200":
        return ""
    m = re.search(r"<title>([^<]*) : Part ([^ <]+) \| BrickLink</title>", body)
    return m.group(1).strip() if m and m.group(2) == item else ""


def candidates(part: str, con: sqlite3.Connection) -> list[str]:
    out = list(KNOWN.get(part, []))
    stripped = re.sub(r"[a-z]+\d*$", "", part)  # 3069b -> 3069
    if stripped and stripped != part:
        out.append(stripped)
    for (other,) in con.execute(
        "SELECT CASE WHEN child = ? THEN parent ELSE child END FROM relationships "
        "WHERE (child = ? OR parent = ?) AND rel_type IN ('M', 'A')", (part, part, part)):
        out.append(other)
    seen = []
    return [c for c in out if not (c in seen or seen.append(c))]


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 350
    con = sqlite3.connect(ROOT / "data" / "catalog.db")
    parts = [r[0] for r in con.execute("SELECT part_num FROM parts WHERE printed = 0 ORDER BY n_sets DESC LIMIT ?", (n,))]
    # plus every part the agents actually picked in our test runs
    used = set(re.findall(r'"(?:\d+ x )?([0-9]+[a-z]*\d*)\s', (ROOT / "docs" / "eval" / "results.json").read_text()))
    used |= set(re.findall(r'"part_num":\s*"([^"]+)"', (ROOT / "docs" / "eval" / "sample_trace.json").read_text()))
    parts += [p for p in sorted(used) if p not in parts and con.execute("SELECT 1 FROM parts WHERE part_num=?", (p,)).fetchone()]

    rows, changed, missing = [], 0, []
    for i, p in enumerate(parts, 1):
        title = bl_title(p)
        if title:
            rows.append((p, p, title))
        else:
            for c in candidates(p, con):
                t = bl_title(c)
                if t:
                    rows.append((p, c, t))
                    changed += 1
                    print(f"  {p} -> {c} ({t})", flush=True)
                    break
            else:
                missing.append(p)
        if i % 50 == 0:
            print(f"checked {i}/{len(parts)}", flush=True)
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rb_part_num", "bl_item_id", "bl_name"])
        w.writerows(rows)
    print(f"\nchecked {len(parts)} parts: {len(rows) - changed} same id, {changed} renamed, "
          f"{len(missing)} not found: {missing[:20]}")
    (ROOT / "docs" / "eval" / "bricklink_id_check.json").write_text(json.dumps(
        {"date": time.strftime("%Y-%m-%d"), "checked": len(parts), "same": len(rows) - changed,
         "renamed": changed, "not_found": missing}, indent=2))


if __name__ == "__main__":
    main()
