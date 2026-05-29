"""Validate the integrity of `backend/data/*.json`.

Run: `python -m app.scripts.validate_data`.
Exits with non-zero code if any error is found.
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


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    cases_raw = load_cases()
    cases: list[CaseRaw] = []
    for raw in cases_raw:
        try:
            cases.append(CaseRaw.model_validate(raw))
        except Exception as e:
            errors.append(f"case {raw.get('id')}: schema invalid -> {e}")

    formal = [c for c in cases if not c.isPractice]
    if len(formal) != 8:
        errors.append(f"正式 case 数量应为 8，实际 {len(formal)}")

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

    formal_ids = {c.id for c in formal}
    defective_ids = {c.id for c in formal if c.defectPresent}
    non_defective_ids = formal_ids - defective_ids
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
