from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any, Iterable


def to_csv(rows: list[dict[str, Any]], columns: list[str] | None = None) -> str:
    """Convert a list of plain dicts to a CSV string.

    Header is the union of keys from all rows (or `columns` if provided).
    Date / dict / list values are serialized via JSON-ish helpers.
    """
    if not rows and not columns:
        return ""
    cols = columns
    if cols is None:
        seen: dict[str, None] = {}
        for r in rows:
            for k in r.keys():
                seen[k] = None
        cols = list(seen.keys())

    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(cols)
    for r in rows:
        writer.writerow([_format(r.get(c)) for c in cols])
    return buf.getvalue()


def _format(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, (dict, list, tuple)):
        import json

        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def flatten_summary(s: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten /api/admin/summary JSON into a single CSV-friendly table."""
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


def coerce_iter_to_list(rows: Iterable[dict]) -> list[dict]:
    return list(rows)
