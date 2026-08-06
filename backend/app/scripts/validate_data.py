"""
================================================================================
文件作用：★ 题库的体检工具 —— 改完题目一定要跑一遍再提交
================================================================================

    cd backend
    PYTHONIOENCODING=utf-8 python -m app.scripts.validate_data

它检查的是那些「程序不会报错、但会毁掉研究」的问题：

  * 正式题不是 8 道
  * goldAction 写了四种动作之外的值（比如拼错成 "send_as_it"）
  * 某道题没写次优答案，导致判分过于严苛
  * ★ 顺序模板里，唯一那道「AI 草稿没出错」的题排到了后半段

  最后这一条最要命：如果医生前几题看到的 AI 草稿全都有错，
  他会很快形成「这个 AI 总是出错」的预期，之后所有判断都带着这个偏见。
  所以那道"没错"的题必须早点出现，把基线拉正。

发现任何错误就返回非零退出码，CI 会因此失败，提交不上去。

--------------------------------------------------------------------------------
本文件的代码块：
--------------------------------------------------------------------------------
  第 1 块  main()   全部检查都在这一个函数里，按关卡顺序往下走
================================================================================
"""

from __future__ import annotations

import sys

from app.schemas.case import CaseRaw
from app.schemas.common import SelectedAction
from app.scripts.data_loader import (
    load_case_quick_survey,
    load_cases,
    load_order_templates,
    load_post_survey,
    load_pre_survey,
)


# ── 第 1 块：全部检查 ────────────────────────────────────────────────────
def main() -> int:
    # errors = 必须修的（会让脚本返回非零退出码）
    # warnings = 提醒一下，不阻塞
    errors: list[str] = []
    warnings: list[str] = []

    # ---- 第 1 关：每道题的字段格式对不对 ----
    cases_raw = load_cases()
    cases: list[CaseRaw] = []
    for raw in cases_raw:
        try:
            cases.append(CaseRaw.model_validate(raw))
        except Exception as e:
            # 收集错误而不是直接抛出，这样一次能报出所有问题，
            # 不用改一个跑一次。
            errors.append(f"case {raw.get('id')}: schema invalid -> {e}")

    # ---- 第 2 关：题目数量 ----
    formal = [c for c in cases if not c.isPractice]
    if len(formal) != 8:
        errors.append(f"正式 case 数量应为 8，实际 {len(formal)}")

    # ---- 第 3 关：每道题的内容完整性 ----
    allowed_actions = {a.value for a in SelectedAction}
    for c in cases:
        if c.goldAction not in allowed_actions:
            errors.append(f"case {c.id} goldAction 不在四种动作内: {c.goldAction}")
        if not c.guardrail.factsUsed:
            errors.append(f"case {c.id} guardrail.factsUsed 为空")
        if not c.guardrail.riskCue:
            errors.append(f"case {c.id} guardrail.riskCue 为空")
        if len(c.guardrail.checklist) < 3:
            errors.append(f"case {c.id} guardrail.checklist 应至少 3 条")

    # ---- 第 4 关：题目顺序模板的约束 ----
    # 先把题目按属性分组，下面检查顺序模板时要用
    formal_ids = {c.id for c in formal}
    defective_ids = {c.id for c in formal if c.defectPresent}      # AI 有错的题（7 道）
    non_defective_ids = formal_ids - defective_ids                 # AI 没错的题（1 道）
    high_risk_ids = {c.id for c in formal if c.riskLevel == "high"}
    low_risk_ids = {c.id for c in formal if c.riskLevel == "low"}

    templates = load_order_templates().get("templates", [])
    if len(templates) != 4:
        errors.append(f"需要 4 套顺序模板，实际 {len(templates)}")
    for t in templates:
        order = t["order"]
        if len(order) != 8:
            errors.append(f"模板 {t['id']} 顺序长度应为 8")
        if len(set(order)) != len(order):
            errors.append(f"模板 {t['id']} 包含重复 case")
        for cid in order:
            if cid not in formal_ids:
                errors.append(f"模板 {t['id']} 包含未知 case {cid}")

        first_half = order[:4]
        last_half = order[4:]

        # V3 加难版：仅保留 1 个 non-defect 校准 case（case_01）时，要求它必须出现
        # 在前半段，让受试者在前期看到 AI 至少有一次写对，避免「AI 必有错」的预期。
        if non_defective_ids:
            if not (non_defective_ids & set(first_half)):
                errors.append(
                    f"模板 {t['id']} 前半段未包含任何 non-defect case；"
                    f"trust 校准要求至少 1 个 non-defect 在位置 1-4"
                )

        # 多元素集合时才检查「不全在某半段」（单 case 集合下该约束无意义）
        if len(high_risk_ids) >= 2:
            if len([c for c in last_half if c in high_risk_ids]) == len(high_risk_ids):
                errors.append(f"模板 {t['id']} 所有高风险 case 都集中在后半段")
        low_accurate = low_risk_ids - defective_ids
        if len(low_accurate) >= 2:
            if len([c for c in first_half if c in low_accurate]) == len(low_accurate):
                warnings.append(f"模板 {t['id']} 所有 low-accurate case 都在前半段（建议打散）")

    pre = load_pre_survey()
    if not pre.get("items"):
        errors.append("pre_survey.items 为空")
    post = load_post_survey()
    if not post.get("blocks"):
        errors.append("post_survey.blocks 为空")
    quick = load_case_quick_survey()
    if not quick.get("items") or len(quick["items"]) != 2:
        errors.append("case_quick_survey 应有 2 个题目")

    if not errors:
        print("✅ 数据校验通过")
        print(f"  正式 case: {len(formal)}")
        print(f"  defective: {len(defective_ids)}")
        print(f"  high-risk: {len(high_risk_ids)}")
        print(f"  low-risk: {len(low_risk_ids)}")
        print(f"  顺序模板: {len(templates)}")
        if warnings:
            print("\n⚠️  警告：")
            for w in warnings:
                print("  -", w)
        return 0

    print("❌ 数据校验失败：")
    for e in errors:
        print("  -", e)
    if warnings:
        print("\n⚠️  另有警告：")
        for w in warnings:
            print("  -", w)
    return 1


if __name__ == "__main__":
    sys.exit(main())
