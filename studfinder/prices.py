"""BrickLink price estimates from the snapshot in data/bricklink_prices.csv.

Built by scripts/fetch_bricklink_prices.py: the quantity-weighted average price new parts sold for
on BrickLink over the last 6 months. The app only reads this file; it never calls BrickLink.
"""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

PRICES = Path(__file__).resolve().parents[1] / "data" / "bricklink_prices.csv"


@lru_cache(maxsize=1)
def _table() -> dict[tuple[str, int], dict]:
    if not PRICES.exists():
        return {}
    with open(PRICES, encoding="utf-8") as f:
        return {
            (r["rb_part_num"], int(r["rb_color_id"])): {"price": float(r["price_usd"]), "basis": r["basis"],
                                                         "count": int(r["count"]), "fetched": r["fetched"]}
            for r in csv.DictReader(f)
        }


def price(part_num: str, color_id: int) -> float | None:
    p = _table().get((part_num, color_id))
    return p["price"] if p else None


def few_sales(part_num: str, color_id: int) -> bool:
    """True when the estimate rests on fewer than 10 sales or listings (less reliable)."""
    p = _table().get((part_num, color_id))
    return bool(p and p["count"] < 10)


def snapshot_date() -> str:
    return max((v["fetched"] for v in _table().values()), default="")
