"""Keys, model, prices, and the safety limits that every agent run obeys."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"

# The .env is looked for in two places: this repo first, then one folder up
# (where the teaching staff's shared .env lives). Earlier values win.
load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / ".env")

MODEL = "gpt-6-luna"  # the only model allowed on the course key
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"
REASONING_EFFORT = os.getenv("STUDFINDER_REASONING", "low")

# USD per 1M tokens (OpenAI standard tier, fetched 2026-10-06 for Lecture 11).
PRICES = {"input": 0.10, "cached_input": 0.01, "cache_write": 0.125, "output": 0.50}

# --- Guardrails -------------------------------------------------------------
MAX_OUTPUT_TOKENS = 1500          # per model response
MAX_STEPS = {"finder": 14, "checker": 6, "refiner": 8}  # model calls per agent run
SESSION_TOKEN_BUDGET = 250_000    # one browser session, all runs combined
DAILY_TOKEN_BUDGET = 3_000_000    # whole app per day (read from logs/usage.jsonl)
MAX_DESCRIPTION_CHARS = 1500
MAX_CHAT_CHARS = 500
MAX_LOTS = 60                     # distinct part+color rows on one list
MAX_QTY_PER_LOT = 300
MAX_TOTAL_PIECES = 3000

_client: OpenAI | None = None


def client() -> OpenAI:
    global _client
    if _client is None:
        portkey = os.getenv("PORTKEY_API_KEY", "").strip()
        openai_key = os.getenv("OPENAI_API_KEY", "").strip()
        if portkey:
            _client = OpenAI(api_key=portkey, base_url=PORTKEY_BASE_URL,
                             default_headers={"x-portkey-api-key": portkey})
        elif openai_key:
            _client = OpenAI(api_key=openai_key)
        else:
            raise RuntimeError(
                "No API key found. Put PORTKEY_API_KEY in a .env file in this folder "
                "or the folder above it (see .env.example)."
            )
    return _client


def cost_usd(u: dict) -> float:
    cached = u.get("cached", 0)
    write = u.get("cache_write", 0)
    fresh = max(u.get("input", 0) - cached - write, 0)
    return (
        fresh * PRICES["input"]
        + cached * PRICES["cached_input"]
        + write * PRICES["cache_write"]
        + u.get("output", 0) * PRICES["output"]
    ) / 1_000_000
