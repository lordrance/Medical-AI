from __future__ import annotations

from enum import Enum


class ActionReasonCode(str, Enum):
    """受试者选择当前处理方式的主要原因（问卷 7.0：case_action_reason）。

    `nothing_to_change` 是 V4 新增的 send_as_is 专属选项，表示「基本无误，
    可直接发送」——区别于 `basically_ok`（V3 用于 edit_then_send 的「整体
    基本可用，仅需少量修改」）。前端按 selectedAction 过滤可选项。

    ★ 中文：医生选完处理方式后，还要选一个「为什么这么选」。
    这个理由是把「行为」和「认知」连起来的关键——
    同样是「原样发送」，理由是「确实没问题」还是「懒得改」，含义天差地别。

    前端会按医生选的处理方式过滤可选理由（见 CasePage.tsx 的
    reasonsForAction）：选「原样发送」时才出现 nothing_to_change，
    其余情况用另一套 5 个选项。
    """

    safety_risk = "safety_risk"              # 存在安全风险
    insufficient_info = "insufficient_info"  # 信息不足以作答
    wording_issue = "wording_issue"          # 表述/语气有问题
    basically_ok = "basically_ok"            # 整体基本可用，只需少量修改
    nothing_to_change = "nothing_to_change"  # 基本无误，可直接发送（V4 新增，仅 send_as_is）
    other = "other"                          # 其他 —— ★ 选了必须填文字说明
