"""Baseline: ask the same model (gpt-6-luna) the friend-kit request with NO catalog tools,
the way someone would ask ChatGPT, and check its part numbers against the real catalog.

    python scripts/baseline_no_tools.py      # 5 runs, writes docs/eval/baseline.json
"""

from __future__ import annotations

import json
import re
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.evaluate import KNOWN_ANSWERS, KNOWN_REQUEST  # noqa: E402
from studfinder import catalog, config  # noqa: E402

PROMPT = ("You are a helpful LEGO expert. A builder asks:\n\n{req}\n\nList each part with its BrickLink part number "
          "and color, one per line, like: 3004 - Brick 1 x 2 - Red. (Request {nonce}.)")


def main() -> None:
    runs = []
    for i in range(1, 6):
        r = config.client().responses.create(
            model=config.MODEL, input=PROMPT.format(req=KNOWN_REQUEST, nonce=uuid.uuid4().hex[:6]),
            max_output_tokens=1500, reasoning={"effort": config.REASONING_EFFORT}, store=False,
        )
        text = r.output_text or ""
        nums = sorted(set(re.findall(r"\b\d{4,6}[a-z]?\d?\b", text.lower())))
        nums = [n for n in nums if not (len(n) == 4 and n.startswith(("19", "20")))]  # drop years
        accepted = set().union(*(parts for parts, _ in KNOWN_ANSWERS.values()))
        fake = [n for n in nums if not catalog.get_part(n) and n not in accepted]
        hits = {need: any(p in nums for p in parts) for need, (parts, _) in KNOWN_ANSWERS.items()}
        runs.append({"run": i, "right_part_numbers": sum(hits.values()), "out_of": len(hits), "hits": hits,
                     "part_numbers_given": nums, "not_in_catalog": fake, "answer": text})
        print(f"run {i}: right {sum(hits.values())}/{len(hits)} | numbers given {len(nums)} | "
              f"not in catalog: {fake or 'none'}")
    (ROOT / "docs" / "eval" / "baseline.json").write_text(json.dumps(runs, indent=2))


if __name__ == "__main__":
    main()
