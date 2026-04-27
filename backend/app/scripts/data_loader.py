from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def read_json(filename: str) -> Any:
    path = DATA_DIR / filename
    return json.loads(path.read_text(encoding="utf-8"))


def load_cases() -> list[dict]:
    return read_json("cases.json")


def load_order_templates() -> dict:
    return read_json("order_templates.json")


def load_pre_survey() -> dict:
    return read_json("pre_survey.json")


def load_post_survey() -> dict:
    return read_json("post_survey.json")


def load_case_quick_survey() -> dict:
    return read_json("case_quick_survey.json")
