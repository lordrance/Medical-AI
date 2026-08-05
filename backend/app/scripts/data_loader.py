"""读取 backend/data/ 下的题库 JSON 文件。

★ 所有研究素材（题目、问卷题、顺序模板）都以 JSON 文件的形式放在
backend/data/ 里，而不是写死在代码里。好处是改题目不用改代码，
而且这些文件在 git 里有完整的修改历史，改过什么一目了然。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# 从本文件位置往上数两级到 backend/，再进 data/。
# 用相对定位而不是写死绝对路径，这样本机、Docker 容器里都能跑。
#   __file__ = backend/app/scripts/data_loader.py
#   parents[0]=scripts  parents[1]=app  parents[2]=backend
DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def read_json(filename: str) -> Any:
    """读一个 JSON 文件。★ 必须指定 utf-8，否则 Windows 上读中文会乱码。"""
    path = DATA_DIR / filename
    return json.loads(path.read_text(encoding="utf-8"))


def load_cases() -> list[dict]:
    """★ 8 道正式题 + 1 道练习题的全部内容。改题目就是改这个文件。"""
    return read_json("cases.json")


def load_order_templates() -> dict:
    """4 套题目顺序。"""
    return read_json("order_templates.json")


def load_pre_survey() -> dict:
    """前测问卷题目（存档用；前端实际用的是 preSurveyConfig.ts）。"""
    return read_json("pre_survey.json")


def load_post_survey() -> dict:
    """后测问卷题目（存档用；前端实际用的是 postSurveyConfig.ts）。"""
    return read_json("post_survey.json")


def load_case_quick_survey() -> dict:
    """每道题后面那两道小量表的题目。"""
    return read_json("case_quick_survey.json")
