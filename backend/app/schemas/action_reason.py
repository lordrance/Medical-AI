from __future__ import annotations

from enum import Enum


class ActionReasonCode(str, Enum):
    """受试者选择当前处理方式的主要原因（问卷 7.0：case_action_reason）。

    `nothing_to_change` 是 V4 新增的 send_as_is 专属选项，表示「基本无误，
    可直接发送」——区别于 `basically_ok`（V3 用于 edit_then_send 的「整体
    基本可用，仅需少量修改」）。前端按 selectedAction 过滤可选项。
    """

    safety_risk = "safety_risk"
    insufficient_info = "insufficient_info"
    wording_issue = "wording_issue"
    basically_ok = "basically_ok"
    nothing_to_change = "nothing_to_change"
    other = "other"
