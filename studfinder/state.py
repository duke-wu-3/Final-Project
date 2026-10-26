"""One user's parts list, agent trace, and token usage (kept in memory)."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import date

from . import catalog, prices
from .config import (
    LOGS,
    MAX_LOTS,
    MAX_QTY_PER_LOT,
    MAX_TOTAL_PIECES,
    cost_usd,
)


@dataclass
class Item:
    id: int
    part_num: str
    name: str
    color_id: int
    color: str
    rgb: str
    bl_color_id: int | None
    qty: int
    section: str
    note: str
    sets: int
    last_year: int
    rarity: str
    img: str
    suggestion: dict | None = None


@dataclass
class Session:
    id: str
    description: str = ""
    items: dict[int, Item] = field(default_factory=dict)
    next_id: int = 1
    summary: str = ""
    checker_notes: list[str] = field(default_factory=list)
    chat: list[dict] = field(default_factory=list)
    trace: list[dict] = field(default_factory=list)
    blocked: list[dict] = field(default_factory=list)
    run_usage: dict = field(default_factory=dict)
    session_usage: dict = field(default_factory=dict)
    running: str = ""
    error: str = ""
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    # --- list edits (all validated against the catalog) ------------------------
    def total_pieces(self) -> int:
        return sum(i.qty for i in self.items.values())

    def find_item(self, part_num: str, color_id: int) -> Item | None:
        for it in self.items.values():
            if it.part_num == part_num and it.color_id == color_id:
                return it
        return None

    def add(self, part_num: str, color_name: str, qty: int, section: str = "", note: str = "") -> dict:
        part = catalog.get_part(part_num)
        if not part:
            self.block("made-up part", f"{part_num} is not in the LEGO catalog")
            return {"error": f"Part {part_num} does not exist. Search again and use a part_num from the results."}
        color = catalog.resolve_color(color_name)
        if not color:
            return {"error": f"Unknown color '{color_name}'. Pick one of: "
                             + ", ".join(c["color"] for c in catalog.part_colors(part_num, 8))}
        pc = catalog.part_color(part_num, color["id"])
        if not pc:
            self.block("impossible color", f"{part['name']} has never been made in {color['name']}")
            return {"error": f"{part['name']} has never been made in {color['name']}. It exists in: "
                             + ", ".join(c["color"] for c in catalog.part_colors(part_num, 8))}
        qty = int(qty)
        if qty < 1:
            return {"error": "Quantity must be at least 1."}
        existing = self.find_item(part_num, color["id"])
        new_qty = (existing.qty if existing else 0) + qty
        if new_qty > MAX_QTY_PER_LOT:
            self.block("quantity cap", f"{new_qty} x {part['name']} is over the {MAX_QTY_PER_LOT} limit")
            return {"error": f"Quantity cap is {MAX_QTY_PER_LOT} per part. Use a realistic amount."}
        if self.total_pieces() + qty > MAX_TOTAL_PIECES:
            self.block("piece cap", f"list would pass {MAX_TOTAL_PIECES} pieces")
            return {"error": f"The list is capped at {MAX_TOTAL_PIECES} pieces."}
        if existing:
            existing.qty = new_qty
            return {"ok": True, "id": existing.id, "qty": new_qty, "rarity": existing.rarity}
        if len(self.items) >= MAX_LOTS:
            self.block("lot cap", f"list would pass {MAX_LOTS} different parts")
            return {"error": f"The list is capped at {MAX_LOTS} different parts."}
        it = Item(
            id=self.next_id, part_num=part_num, name=part["name"], color_id=color["id"], color=color["name"],
            rgb=color["rgb"], bl_color_id=color["bl_id"], qty=qty, section=(section or "Other")[:40],
            note=note[:120], sets=pc["sets"], last_year=pc["last_year"], rarity=pc["rarity"], img=pc["img"],
        )
        self.items[it.id] = it
        self.next_id += 1
        return {"ok": True, "id": it.id, "rarity": it.rarity, "sets": it.sets}

    def set_qty(self, item_id: int, qty: int) -> dict:
        it = self.items.get(int(item_id))
        if not it:
            return {"error": f"No item #{item_id}."}
        qty = int(qty)
        if qty <= 0:
            del self.items[it.id]
            return {"ok": True, "removed": it.id}
        if qty > MAX_QTY_PER_LOT:
            self.block("quantity cap", f"{qty} x {it.name} is over the {MAX_QTY_PER_LOT} limit")
            return {"error": f"Quantity cap is {MAX_QTY_PER_LOT} per part."}
        if self.total_pieces() - it.qty + qty > MAX_TOTAL_PIECES:
            self.block("piece cap", f"list would pass {MAX_TOTAL_PIECES} pieces")
            return {"error": f"The list is capped at {MAX_TOTAL_PIECES} pieces."}
        it.qty = qty
        return {"ok": True, "id": it.id, "qty": qty}

    def remove(self, item_id: int) -> dict:
        it = self.items.pop(int(item_id), None)
        return {"ok": True, "removed": item_id} if it else {"error": f"No item #{item_id}."}

    def replace(self, item_id: int, part_num: str, color_name: str) -> dict:
        it = self.items.get(int(item_id))
        if not it:
            return {"error": f"No item #{item_id}."}
        old = (it.qty, it.section, it.note)
        del self.items[it.id]
        res = self.add(part_num, color_name, old[0], old[1], old[2])
        if "error" in res:
            self.items[it.id] = it  # put the original back
        return res

    def recolor(self, item_id: int, color_name: str) -> dict:
        it = self.items.get(int(item_id))
        if not it:
            return {"error": f"No item #{item_id}."}
        color = catalog.resolve_color(color_name)
        if not color:
            return {"error": f"Unknown color '{color_name}'."}
        pc = catalog.part_color(it.part_num, color["id"])
        if not pc:
            self.block("impossible color", f"{it.name} has never been made in {color['name']}")
            return {"error": f"{it.name} is not made in {color['name']}. It exists in: "
                             + ", ".join(c["color"] for c in catalog.part_colors(it.part_num, 8))}
        twin = self.find_item(it.part_num, color["id"])
        if twin and twin.id != it.id:  # already have it in that color: merge
            twin.qty = min(twin.qty + it.qty, MAX_QTY_PER_LOT)
            del self.items[it.id]
            return {"ok": True, "merged_into": twin.id}
        it.color_id, it.color, it.rgb, it.bl_color_id = color["id"], color["name"], color["rgb"], color["bl_id"]
        it.sets, it.last_year, it.rarity, it.img = pc["sets"], pc["last_year"], pc["rarity"], pc["img"]
        it.suggestion = None
        return {"ok": True, "id": it.id, "rarity": it.rarity}

    def block(self, kind: str, detail: str) -> None:
        self.blocked.append({"kind": kind, "detail": detail, "t": time.strftime("%H:%M:%S")})

    def compact_list(self) -> str:
        if not self.items:
            return "(empty)"
        def cost(i: Item) -> str:
            p = prices.price(i.part_num, i.color_id)
            return f" | about ${p:.2f} each" if p is not None else ""

        return "\n".join(
            f"#{i.id} {i.part_num} {i.name} | {i.color} | x{i.qty} | {i.section} | {i.rarity} ({i.sets} sets){cost(i)}"
            for i in self.items.values()
        )

    # --- usage -----------------------------------------------------------------
    def record_usage(self, agent: str, u: dict, cache_hit: bool = False) -> None:
        u = {**u, "cost": 0.0 if cache_hit else cost_usd(u), "cache_hits": int(cache_hit)}
        for bucket in (self.run_usage, self.session_usage):
            for k, v in u.items():
                bucket[k] = bucket.get(k, 0) + v
            bucket["calls"] = bucket.get("calls", 0) + 1
            per = bucket.setdefault("by_agent", {})
            a = per.setdefault(agent, {"input": 0, "cached": 0, "output": 0, "cost": 0.0, "calls": 0})
            for k in ("input", "cached", "output", "cost"):
                a[k] += u.get(k, 0)
            a["calls"] += 1
        LOGS.mkdir(exist_ok=True)
        with open(LOGS / "usage.jsonl", "a") as f:
            f.write(json.dumps({"ts": time.time(), "day": date.today().isoformat(), "session": self.id,
                                "agent": agent, **u}) + "\n")

    def session_tokens(self) -> int:
        return self.session_usage.get("input", 0) + self.session_usage.get("output", 0)

    def to_json(self) -> dict:
        items = []
        est_total, priced = 0.0, 0
        for i in self.items.values():
            d = asdict(i)
            d["price_each"] = prices.price(i.part_num, i.color_id)
            d["price_few_sales"] = prices.few_sales(i.part_num, i.color_id)
            if d["price_each"] is not None:
                est_total += d["price_each"] * i.qty
                priced += 1
            if i.suggestion:
                c = catalog.resolve_color(i.suggestion["color"])
                d["suggestion"] = {**i.suggestion, "price_each": prices.price(i.suggestion["part_num"], c["id"]) if c else None}
            items.append(d)
        return {
            "estimate": {"total": round(est_total, 2), "priced": priced, "parts": len(items),
                         "date": prices.snapshot_date()},
            "description": self.description,
            "items": items,
            "total_pieces": self.total_pieces(),
            "summary": self.summary,
            "checker_notes": self.checker_notes,
            "chat": self.chat,
            "trace": self.trace[-80:],
            "blocked": self.blocked[-20:],
            "run_usage": self.run_usage,
            "session_usage": self.session_usage,
            "running": self.running,
            "error": self.error,
        }


def tokens_used_today() -> int:
    path = LOGS / "usage.jsonl"
    if not path.exists():
        return 0
    today = date.today().isoformat()
    total = 0
    with open(path) as f:
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("day") == today:
                total += r.get("input", 0) + r.get("output", 0)
    return total
