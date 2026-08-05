"""★ 四种处理方式的定义 —— 整个实验的因变量就是它。

医生看完 AI 草稿后必须四选一，这个选择就是研究要观测的核心行为。
这个文件定义了它的取值、中文标签、以及问卷 PDF 里的对应术语。
"""

from __future__ import annotations

from enum import Enum


class SelectedAction(str, Enum):
    """四种处理方式。继承 str 是为了能直接当字符串用、也能直接存数据库。

    ★ 这些字符串会写进数据库、导出到 CSV、对应论文的编码表，
    改动等于让已收集的 296 条数据对不上号。不要改。
    """

    send_as_is = "send_as_is"                  # 原样发送：完全信任 AI
    edit_then_send = "edit_then_send"          # 改一改再发：部分信任
    discard_and_rewrite = "discard_and_rewrite"  # 弃用重写：基本不信任
    escalate = "escalate"                      # 上报：认为超出消息回复的范围


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
    """选了「上报」之后再细分成哪一种。医生还要填一段自由文本说明理由。"""

    urgent_evaluation = "urgent_evaluation"  # 需要紧急面诊评估
    call_patient = "call_patient"            # 需要电话联系患者
    other = "other"                          # 其他
