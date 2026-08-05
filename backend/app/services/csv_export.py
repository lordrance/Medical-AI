"""把数据转成 CSV —— 你从后台下载、用 Excel / SPSS 打开的那个格式。"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any


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


def _format(v: Any) -> str:
    """把各种 Python 类型转成 CSV 单元格里的文本。"""
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


def flatten_summary(s: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten /api/admin/summary JSON into a single CSV-friendly table.

    中文：汇总接口返回的是层层嵌套的 JSON（完成率、混淆矩阵、每题、每人），
    CSV 是平的表格，装不下嵌套结构。所以这里把它们摊成一张长表，
    用第一列 "kind" 区分每行属于哪一部分。
    """
    rows: list[dict[str, Any]] = []
    completion = s["completion"]
    cm = s["confusionMatrix"]
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
    for r in s["perCase"]:
        rows.append({"kind": "per_case", **r})
    for r in s["perParticipant"]:
        rows.append({"kind": "per_participant", **r})
    return rows
