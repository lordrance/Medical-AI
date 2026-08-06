"""
================================================================================
文件作用：定义「医生为什么这么选」的六个理由选项
================================================================================

医生选完处理方式之后，还要回答一道题：为什么这么选。

★ 为什么要问这个：理由是把「行为」和「认知」连起来的关键。
  同样是选「原样发送」，理由是"确实没问题"还是"懒得改"，
  含义天差地别——前者是恰当的信任，后者是敷衍。
  光看行为数据分不出这两种人，加上理由就能分。

★ 前端会按医生选的处理方式，只显示对应的一组理由
  （见前端 CasePage.tsx 里的 reasonsForAction）：
      选「原样发送」    → nothing_to_change / safety_risk / wording_issue / other
      选其他三种        → safety_risk / insufficient_info / wording_issue /
                          basically_ok / other

--------------------------------------------------------------------------------
本文件的代码块：
--------------------------------------------------------------------------------
  第 1 块  ActionReasonCode   六个理由选项
================================================================================
"""

from __future__ import annotations

from enum import Enum


# ── 第 1 块：六个理由选项 ──────────────────────────────────────────────────
class ActionReasonCode(str, Enum):
    """受试者选择当前处理方式的主要原因（问卷 7.0：case_action_reason）。

    `nothing_to_change` 是 V4 新增的 send_as_is 专属选项，表示「基本无误，
    可直接发送」——区别于 `basically_ok`（V3 用于 edit_then_send 的「整体
    基本可用，仅需少量修改」）。前端按 selectedAction 过滤可选项。

    ★ 中文补充：最后两个选项看起来很像，但含义不同，别搞混：
        nothing_to_change  "不用改"    → 配合「原样发送」
        basically_ok       "只需小改"  → 配合「编辑后发送」
      分开是为了区分"完全没问题"和"有点小问题但不严重"这两种判断。
    """

    safety_risk = "safety_risk"              # 存在安全风险
    insufficient_info = "insufficient_info"  # 信息不足，无法据此作答
    wording_issue = "wording_issue"          # 表述或语气有问题
    basically_ok = "basically_ok"            # 整体基本可用，只需少量修改
    nothing_to_change = "nothing_to_change"  # 基本无误，可直接发送（V4 新增）
    # ★ 选了「其他」就必须填一段文字说明，否则这条数据没有分析价值。
    #   这条规则在 api/action.py 的 _other_reason_requires_text 里强制执行。
    other = "other"
