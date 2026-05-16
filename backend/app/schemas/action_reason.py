from __future__ import annotations

from enum import Enum


class ActionReasonCode(str, Enum):
    """受试者选择当前处理方式的主要原因（问卷 7.0：case_action_reason）。"""

    safety_risk = "safety_risk"
    insufficient_info = "insufficient_info"
    wording_issue = "wording_issue"
    basically_ok = "basically_ok"
    other = "other"
