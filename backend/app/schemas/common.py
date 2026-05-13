from __future__ import annotations

from enum import Enum


class Condition(str, Enum):
    plain = "plain"
    guardrail = "guardrail"


class SelectedAction(str, Enum):
    send_as_is = "send_as_is"
    edit_then_send = "edit_then_send"
    discard_and_rewrite = "discard_and_rewrite"
    escalate = "escalate"


# Chinese-localized labels for the four actions, exposed via /api/meta or copied
# into the frontend i18n dict. Keeping them server-side ensures admin export
# uses identical labels.
ACTION_LABEL_ZH: dict[str, str] = {
    "send_as_is": "原样发送",
    "edit_then_send": "编辑后发送",
    "discard_and_rewrite": "弃用并重写",
    "escalate": "升级处理",
}

# 问卷 7.0：`log_final_action` 类别取值（与 PDF「1=直接发送…」表格用语一致；UI 仍可用「原样发送」）
LOG_FINAL_ACTION_PDF: dict[str, str] = {
    "send_as_is": "直接发送",
    "edit_then_send": "编辑后发送",
    "discard_and_rewrite": "弃用并重写",
    "escalate": "升级处理",
}


class EscalateSubtype(str, Enum):
    urgent_evaluation = "urgent_evaluation"
    call_patient = "call_patient"
    other = "other"


ESCALATE_SUBTYPE_LABEL_ZH: dict[str, str] = {
    "urgent_evaluation": "建议立即就诊或急诊",
    "call_patient": "电话回访患者",
    "other": "其他升级处理",
}
