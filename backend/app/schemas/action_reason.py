from __future__ import annotations

from enum import Enum


class ActionReasonCode(str, Enum):
    """受试者选择当前处理方式的主要原因（问卷 7.0：case_action_reason）。"""

    safety_risk = "safety_risk"
    insufficient_info = "insufficient_info"
    wording_issue = "wording_issue"
    basically_ok = "basically_ok"
    other = "other"


ACTION_REASON_LABEL_ZH: dict[str, str] = {
    "safety_risk": "安全风险或患者安全顾虑",
    "insufficient_info": "信息不足，无法据此回复",
    "wording_issue": "措辞或语气需要调整",
    "basically_ok": "整体基本可用，仅需少量修改",
    "other": "其他原因",
}
