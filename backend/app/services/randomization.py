from __future__ import annotations

import random
from typing import Iterable


def assign_condition(rng: random.Random | None = None) -> str:
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
