"""Build data/catalog.db from the free Rebrickable CSV downloads.

Run once (the built catalog.db is committed, so normal users never need this):
    python scripts/build_catalog.py

Inputs:  data/raw/*.csv.gz   from https://rebrickable.com/downloads/
         data/bricklink_colors.csv   (Rebrickable color id -> BrickLink color id)
Output:  data/catalog.db     (SQLite with a full-text index on part names)
"""

from __future__ import annotations

import csv
import gzip
import sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DB = ROOT / "data" / "catalog.db"

# Not useful for System-brick MOCs (and they crowd out real matches in search).
SKIP_CATEGORIES = {
    "Stickers", "Modulex", "Duplo, Quatro and Primo", "Belville, Scala and Fabuland",
    "Clikits", "Znap", "HO Scale", "Non-Buildable Figures (Duplo, Fabuland, etc)",
    "Non-System Parts", "Pen & Watch", "Large Buildable Figures",
}


def rows(name: str):
    with gzip.open(RAW / f"{name}.csv.gz", "rt", encoding="utf-8") as f:
        yield from csv.DictReader(f)


def main() -> None:
    categories = {int(r["id"]): r["name"] for r in rows("part_categories")}
    skip_cats = {cid for cid, n in categories.items() if n in SKIP_CATEGORIES}

    bl_colors = {}
    with open(ROOT / "data" / "bricklink_colors.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            bl_colors[int(r["rb_color_id"])] = int(r["bl_color_id"])

    set_year = {r["set_num"]: int(r["year"]) for r in rows("sets")}
    inv_set = {}
    for r in rows("inventories"):
        if not r["set_num"].startswith("fig-"):
            inv_set[int(r["id"])] = r["set_num"]

    # (part, color) -> set_nums, total quantity, newest year, an image
    pc_sets: dict[tuple, set] = defaultdict(set)
    pc_qty: dict[tuple, int] = defaultdict(int)
    pc_year: dict[tuple, int] = {}
    pc_img: dict[tuple, str] = {}
    for r in rows("inventory_parts"):
        set_num = inv_set.get(int(r["inventory_id"]))
        if not set_num or r["is_spare"] == "True":
            continue
        key = (r["part_num"], int(r["color_id"]))
        pc_sets[key].add(set_num)
        pc_qty[key] += int(r["quantity"])
        y = set_year.get(set_num, 0)
        pc_year[key] = max(pc_year.get(key, 0), y)
        if r["img_url"] and key not in pc_img:
            pc_img[key] = r["img_url"]

    part_sets: dict[str, set] = defaultdict(set)
    for (part, _), s in pc_sets.items():
        part_sets[part] |= s

    DB.unlink(missing_ok=True)
    con = sqlite3.connect(DB)
    con.executescript(
        """
        CREATE TABLE colors (id INTEGER PRIMARY KEY, name TEXT, rgb TEXT, is_trans INTEGER, bl_id INTEGER);
        CREATE TABLE categories (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE parts (part_num TEXT PRIMARY KEY, name TEXT, cat_id INTEGER, n_sets INTEGER, printed INTEGER);
        CREATE TABLE part_colors (part_num TEXT, color_id INTEGER, n_sets INTEGER, qty INTEGER,
                                  last_year INTEGER, img_url TEXT, PRIMARY KEY (part_num, color_id));
        CREATE TABLE relationships (rel_type TEXT, child TEXT, parent TEXT);
        CREATE VIRTUAL TABLE parts_fts USING fts5(part_num UNINDEXED, name, category, tokenize='porter');
        """
    )
    con.executemany(
        "INSERT INTO colors VALUES (?,?,?,?,?)",
        [
            (int(r["id"]), r["name"], r["rgb"], r["is_trans"] == "True", bl_colors.get(int(r["id"])))
            for r in rows("colors")
        ],
    )
    con.executemany("INSERT INTO categories VALUES (?,?)", categories.items())

    kept = set()
    part_rows = []
    for r in rows("parts"):
        cat = int(r["part_cat_id"])
        pn = r["part_num"]
        if cat in skip_cats or pn not in part_sets:
            continue
        printed = "pr" in pn or "pat" in pn or "Print" in r["name"] or "Pattern" in r["name"]
        kept.add(pn)
        part_rows.append((pn, r["name"], cat, len(part_sets[pn]), printed))
    con.executemany("INSERT INTO parts VALUES (?,?,?,?,?)", part_rows)
    con.executemany(
        "INSERT INTO parts_fts VALUES (?,?,?)",
        [(pn, name, categories[cat]) for pn, name, cat, _, _ in part_rows],
    )
    con.executemany(
        "INSERT INTO part_colors VALUES (?,?,?,?,?,?)",
        [
            (p, c, len(s), pc_qty[(p, c)], pc_year[(p, c)], pc_img.get((p, c), ""))
            for (p, c), s in pc_sets.items()
            if p in kept
        ],
    )
    con.executemany(
        "INSERT INTO relationships VALUES (?,?,?)",
        [
            (r["rel_type"], r["child_part_num"], r["parent_part_num"])
            for r in rows("part_relationships")
            if r["child_part_num"] in kept and r["parent_part_num"] in kept
        ],
    )
    con.execute("CREATE INDEX idx_pc_part ON part_colors(part_num)")
    con.execute("CREATE INDEX idx_rel_child ON relationships(child)")
    con.execute("CREATE INDEX idx_rel_parent ON relationships(parent)")
    con.commit()
    con.execute("VACUUM")
    n_pc = con.execute("SELECT COUNT(*) FROM part_colors").fetchone()[0]
    con.close()
    print(f"parts={len(part_rows)} part_colors={n_pc} -> {DB} ({DB.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
