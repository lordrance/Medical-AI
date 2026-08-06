"""
================================================================================
文件作用：把数据转成 CSV —— 你从后台下载、用 Excel / SPSS 打开的那个格式
================================================================================

CSV 就是"逗号分隔的纯文本表格"，第一行是列名，后面每行一条数据。
所有统计软件都认它，所以是导出研究数据最通用的格式。

这个文件不碰数据库、不管 HTTP，只做纯粹的格式转换，所以很好单独测试。

--------------------------------------------------------------------------------
本文件的代码块（从上到下）：
--------------------------------------------------------------------------------
  第 1 块  to_csv()           ★ 一堆字典 → CSV 文本
  第 2 块  _format()          把各种 Python 类型转成单元格里的文字
  第 3 块  flatten_summary()  把嵌套的汇总 JSON 摊平成一张长表
================================================================================
"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any


# ── 第 1 块：字典列表 → CSV 文本 ★ ────────────────────────────────────────
def to_csv(rows: list[dict[str, Any]], columns: list[str] | None = None) -> str:
    """Convert a list of plain dicts to a CSV string.

    Header is the union of keys from all rows (or `columns` if provided).
    Date / dict / list values are serialized via JSON-ish helpers.

    中文：把一堆字典转成 CSV 文本。
    不指定列名时，自动取所有行出现过的键的并集作为表头。
    """
    if not rows and not columns:
        return ""
    cols = columns
    if cols is None:
        # ★ 用 dict 而不是 set 来收集列名，因为 Python 的 dict 保持插入顺序，
        # 而 set 是无序的。这样导出的列顺序每次都一样，不会今天一个样明天一个样。
        seen: dict[str, None] = {}
        for r in rows:
            for k in r.keys():
                seen[k] = None
        cols = list(seen.keys())

    # StringIO = 内存里的「假文件」。csv 模块要写文件，但我们只想要字符串。
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(cols)          # 第一行是表头
    for r in rows:
        # r.get(c) 而不是 r[c]：某一行缺这个列时填空，不报错
        writer.writerow([_format(r.get(c)) for c in cols])
    return buf.getvalue()


# ── 第 2 块：单元格取值转文字 ─────────────────────────────────────────────
def _format(v: Any) -> str:
    """把各种 Python 类型转成 CSV 单元格里的文本。

    CSV 里一切都是文字，所以日期、字典、布尔值都得先转成字符串。
    转法要统一，否则同一列里出现 True/true/1 三种写法，统计软件会懵。
    """
    if v is None:
        return ""                       # 空值 → 空单元格
    if isinstance(v, datetime):
        return v.isoformat()            # 时间 → 2026-08-05T01:23:45+00:00
    if isinstance(v, (dict, list, tuple)):
        import json
        # 嵌套结构 → JSON 字符串塞进一个单元格。
        # ensure_ascii=False 很关键：不加的话中文会变成 中文 这种转义，
        # Excel 打开就是一堆乱码看不懂。
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, bool):
        return "true" if v else "false"  # 统一小写，别让 Excel 自作聪明地转换
    return str(v)


# ── 第 3 块：把嵌套汇总摊平 ───────────────────────────────────────────────
def flatten_summary(s: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten /api/admin/summary JSON into a single CSV-friendly table.

    中文：汇总接口返回的是层层嵌套的 JSON（完成率、混淆矩阵、每题、每人），
    CSV 是平的表格，装不下嵌套结构。所以这里把它们摊成一张长表，
    用第一列 "kind" 区分每行属于哪一部分。
    """
    rows: list[dict[str, Any]] = []
    completion = s["completion"]      # 完成率那一块
    cm = s["confusionMatrix"]         # 混淆矩阵那一块

    # ---- 第 1 类行：总体完成情况，只有一行 ----
    rows.append(
        {
            "kind": "completion",
            "totalParticipants": completion["totalParticipants"],
            "completed": completion["completed"],
            "completionRate": completion["completionRate"],
            "byCondition": completion["byCondition"],
            "accuracy": cm["accuracy"],
            "totalActions": cm["total"],
        }
    )
    # ---- 第 2 类行：混淆矩阵，摊成 4×4 = 16 行 ----
    # 原本是个二维数组，CSV 装不下，所以拆成"标准答案 / 实际选择 / 次数"三列。
    # enumerate 同时给出下标和值：gi 是行号（标准答案），si 是列号（实际选择）。
    for gi, gold in enumerate(cm["actions"]):
        for si, sel in enumerate(cm["actions"]):
            rows.append(
                {
                    "kind": "confusion_matrix",
                    "goldAction": gold,
                    "selectedAction": sel,
                    "count": cm["matrix"][gi][si],
                }
            )
    # ---- 第 3、4 类行：每道题的统计、每个人的统计 ----
    # {"kind": "per_case", **r} 里的 ** 是"把 r 这个字典的所有键值展开进来"，
    # 相当于在原有字段前面加了一列 kind 用来标明这行是哪一类。
    for r in s["perCase"]:
        rows.append({"kind": "per_case", **r})
    for r in s["perParticipant"]:
        rows.append({"kind": "per_participant", **r})
    return rows
