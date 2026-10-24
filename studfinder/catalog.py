"""Read-only lookups against data/catalog.db (built from Rebrickable's free downloads).

Every part number and color the agents use goes through here, so a model
cannot put a part on the list that does not exist in the real catalog.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "data" / "catalog.db"

# How many official sets a part-in-a-color has appeared in.
COMMON_MIN = 40
UNCOMMON_MIN = 8

# BrickLink-style or hobby words -> the words Rebrickable uses in part names.
QUERY_SYNONYMS = {
    "slope curved": "brick curved",
    "curved slope": "brick curved",
    "cheese slope": "slope 30 1 x 1 x 2/3",
    "cheese": "slope 30 1 x 1 x 2/3",
    "jumper": "plate special 1 x 2 with 1 stud",
    "snot": "bracket",
    "grill": "grille",
    "masonry": "masonry brick profile",
    "log": "brick log",
}
COLOR_SYNONYMS = {
    "gray": "Light Bluish Gray",
    "grey": "Light Bluish Gray",
    "light gray": "Light Bluish Gray",
    "light grey": "Light Bluish Gray",
    "dark gray": "Dark Bluish Gray",
    "dark grey": "Dark Bluish Gray",
    "brown": "Reddish Brown",
    "beige": "Tan",
    "dark beige": "Dark Tan",
    "clear": "Trans-Clear",
    "transparent": "Trans-Clear",
    "glass": "Trans-Clear",
    "navy": "Dark Blue",
    "olive": "Olive Green",
    "gold": "Pearl Gold",
    "silver": "Flat Silver",
    "teal": "Dark Turquoise",
    "maroon": "Dark Red",
    "cream": "Light Yellow",
}

_local = threading.local()


def _db() -> sqlite3.Connection:
    con = getattr(_local, "con", None)
    if con is None:
        con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        _local.con = con
    return con


def rarity(n_sets: int) -> str:
    if n_sets >= COMMON_MIN:
        return "common"
    if n_sets >= UNCOMMON_MIN:
        return "uncommon"
    return "rare"


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _fts_tokens(query: str) -> list[str]:
    q = query.lower().replace("×", "x")
    for k, v in QUERY_SYNONYMS.items():
        q = re.sub(rf"\b{re.escape(k)}\b", v, q)
    q = re.sub(r"(\d)\s*x\s*(?=\d)", r"\1 x ", q)  # 1x2 -> 1 x 2
    return [t for t in re.findall(r"[a-z0-9/]+", q) if t not in {"lego", "piece", "pieces", "part", "parts"}]


def search_parts(query: str, limit: int = 8) -> list[dict]:
    toks = _fts_tokens(query)
    if not toks:
        return []
    want_print = any(t.startswith("print") for t in toks)
    sql = """
        SELECT p.part_num, p.name, c.name AS category, p.n_sets, p.printed
        FROM parts_fts f JOIN parts p ON p.part_num = f.part_num JOIN categories c ON c.id = p.cat_id
        WHERE parts_fts MATCH ? {printed}
        ORDER BY (bm25(parts_fts) - 2.0 * log(p.n_sets + 1)) LIMIT ?
    """.format(printed="" if want_print else "AND p.printed = 0")
    quoted = ['"%s"' % t.replace('"', "") for t in toks]
    rows = _db().execute(sql, (" ".join(quoted), limit)).fetchall()
    if len(rows) < 3:  # loosen to "any word" when the exact phrase finds little
        seen = {r["part_num"] for r in rows}
        more = _db().execute(sql, (" OR ".join(quoted), limit * 2)).fetchall()
        rows += [r for r in more if r["part_num"] not in seen][: limit - len(rows)]
    out = []
    for r in rows:
        top = _db().execute(
            """SELECT c.name FROM part_colors pc JOIN colors c ON c.id = pc.color_id
               WHERE pc.part_num = ? ORDER BY pc.n_sets DESC LIMIT 4""",
            (r["part_num"],),
        ).fetchall()
        out.append(
            {
                "part_num": r["part_num"],
                "name": r["name"],
                "category": r["category"],
                "sets": r["n_sets"],
                "top_colors": [t[0] for t in top],
            }
        )
    return out


def get_part(part_num: str) -> dict | None:
    r = _db().execute(
        """SELECT p.part_num, p.name, c.name AS category, p.n_sets FROM parts p
           JOIN categories c ON c.id = p.cat_id WHERE p.part_num = ?""",
        (part_num.strip(),),
    ).fetchone()
    return dict(r) if r else None


def part_colors(part_num: str, limit: int = 10) -> list[dict]:
    rows = _db().execute(
        """SELECT c.id, c.name, pc.n_sets, pc.last_year FROM part_colors pc
           JOIN colors c ON c.id = pc.color_id WHERE pc.part_num = ?
           ORDER BY pc.n_sets DESC LIMIT ?""",
        (part_num.strip(), limit),
    ).fetchall()
    return [
        {"color": r["name"], "sets": r["n_sets"], "last_year": r["last_year"], "rarity": rarity(r["n_sets"])}
        for r in rows
    ]


def resolve_color(name: str) -> dict | None:
    name = (name or "").strip()
    name = COLOR_SYNONYMS.get(name.lower(), name)
    rows = _db().execute("SELECT id, name, rgb, is_trans, bl_id FROM colors").fetchall()
    target = _norm(name)
    for r in rows:
        if _norm(r["name"]) == target:
            return dict(r)
    return None


def color_by_id(color_id: int) -> dict | None:
    r = _db().execute("SELECT id, name, rgb, is_trans, bl_id FROM colors WHERE id = ?", (color_id,)).fetchone()
    return dict(r) if r else None


def part_color(part_num: str, color_id: int) -> dict | None:
    r = _db().execute(
        "SELECT n_sets, last_year, img_url FROM part_colors WHERE part_num = ? AND color_id = ?",
        (part_num, color_id),
    ).fetchone()
    if not r:
        return None
    img = r["img_url"] or _any_image(part_num)
    return {"sets": r["n_sets"], "last_year": r["last_year"], "img": img, "rarity": rarity(r["n_sets"])}


def _any_image(part_num: str) -> str:
    r = _db().execute(
        "SELECT img_url FROM part_colors WHERE part_num = ? AND img_url != '' ORDER BY n_sets DESC LIMIT 1",
        (part_num,),
    ).fetchone()
    return r[0] if r else ""


def _rgb_dist(a: str, b: str) -> float:
    pa = [int(a[i : i + 2], 16) for i in (0, 2, 4)]
    pb = [int(b[i : i + 2], 16) for i in (0, 2, 4)]
    return sum((x - y) ** 2 for x, y in zip(pa, pb)) ** 0.5


def substitutes(part_num: str, color_id: int, limit: int = 6) -> list[dict]:
    """Easier-to-find options for a part-in-a-color, best first.

    1. the same part in the nearest common color,
    2. a related mold or alternate of the part in the same color,
    3. a similar-sized part from the same category in the same color.
    """
    base = get_part(part_num)
    color = color_by_id(color_id)
    if not base or not color:
        return []
    out: list[dict] = []

    rows = _db().execute(
        """SELECT c.id, c.name, c.rgb, pc.n_sets FROM part_colors pc JOIN colors c ON c.id = pc.color_id
           WHERE pc.part_num = ? AND pc.color_id != ? AND pc.n_sets >= ? AND c.bl_id IS NOT NULL""",
        (part_num, color_id, COMMON_MIN),
    ).fetchall()
    for r in sorted(rows, key=lambda r: _rgb_dist(r["rgb"], color["rgb"]))[:2]:
        out.append({"kind": "same part, nearby color", "part_num": part_num, "name": base["name"],
                    "color": r["name"], "sets": r["n_sets"]})

    rel = _db().execute(
        """SELECT DISTINCT CASE WHEN child = ? THEN parent ELSE child END AS other FROM relationships
           WHERE (child = ? OR parent = ?) AND rel_type IN ('M', 'A')""",
        (part_num, part_num, part_num),
    ).fetchall()
    for r in rel:
        pc = part_color(r["other"], color_id)
        p = get_part(r["other"])
        if pc and p and pc["sets"] > (part_color(part_num, color_id) or {"sets": 0})["sets"]:
            out.append({"kind": "related mold, same color", "part_num": r["other"], "name": p["name"],
                        "color": color["name"], "sets": pc["sets"]})

    dims = re.search(r"\d+ x \d+(?: x \d+(?:/\d+)?)?", base["name"])
    if dims:
        rows = _db().execute(
            """SELECT p.part_num, p.name, pc.n_sets FROM parts p JOIN part_colors pc ON pc.part_num = p.part_num
               WHERE p.cat_id = (SELECT cat_id FROM parts WHERE part_num = ?) AND p.part_num != ?
                 AND pc.color_id = ? AND p.printed = 0 AND p.name LIKE ? AND pc.n_sets >= ?
               ORDER BY pc.n_sets DESC LIMIT 3""",
            (part_num, part_num, color_id, f"%{dims.group(0)}%", UNCOMMON_MIN),
        ).fetchall()
        for r in rows:
            out.append({"kind": "similar part, same color", "part_num": r["part_num"], "name": r["name"],
                        "color": color["name"], "sets": r["n_sets"]})
    return out[:limit]
