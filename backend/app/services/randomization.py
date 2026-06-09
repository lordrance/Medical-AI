from __future__ import annotations

import random
from typing import Iterable


def assign_condition(rng: random.Random | None = None) -> str:
    """V3 random plain/guardrail assignment.

    Deprecated in V4 (single-condition study). Kept for archival / replay
    of V3 sessions and for tests that still exercise the V3 contract.
    The V4 session creator wires `condition="single"` directly and does
    not call this function.
    """
    r = rng or random
    return "plain" if r.random() < 0.5 else "guardrail"


def pick_order_template_id(
    template_ids: Iterable[int], rng: random.Random | None = None
) -> int:
    ids = list(template_ids)
    if not ids:
        raise ValueError("No order templates available")
    r = rng or random
    return r.choice(ids)
