"""问卷 7.0 后测 payload：Likert 题 + 注意力检测 + 末尾开放式补充题。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_L = Field(ge=1, le=5)

POST_SURVEY_LIKERT_KEYS: list[str] = [
    "pre_ai_readiness_1",
    "pre_ai_readiness_2",
    "pre_ai_readiness_3",
    "pre_ai_readiness_4",
    "post_utility_1",
    "post_utility_2",
    "post_utility_3",
    "post_utility_4",
    "post_transparency_1",
    "post_transparency_2",
    "post_transparency_3",
    "post_comm_1",
    "post_comm_2",
    "post_comm_3",
    "post_comm_4",
    "post_burden_1",
    "post_burden_2",
    "post_burden_3",
    "post_governance_1",
    "post_governance_2",
    "post_governance_3",
    "post_governance_4",
    "post_reliance_1",
    "post_reliance_2",
    "post_reliance_3",
    "post_reliance_4",
    "post_hallu_1",
    "post_hallu_2",
    "post_hallu_3",
    "post_hallu_4",
    "attn_post_1",
    "post_calibration_1",
    "post_calibration_2",
    "post_calibration_3",
    "post_dissent_1",
    "post_dissent_2",
    "post_dissent_3_reverse",
    "post_accept_trust",
    "post_accept_future_use",
    "post_accept_limited_use",
    "post_accept_optional",
]


class PostSurveyV7Payload(BaseModel):
    """与 `backend/data/post_survey.json` 中各题 `id` 一致。"""

    model_config = ConfigDict(extra="forbid")

    pre_ai_readiness_1: int = _L
    pre_ai_readiness_2: int = _L
    pre_ai_readiness_3: int = _L
    pre_ai_readiness_4: int = _L
    post_utility_1: int = _L
    post_utility_2: int = _L
    post_utility_3: int = _L
    post_utility_4: int = _L
    post_transparency_1: int = _L
    post_transparency_2: int = _L
    post_transparency_3: int = _L
    post_comm_1: int = _L
    post_comm_2: int = _L
    post_comm_3: int = _L
    post_comm_4: int = _L
    post_burden_1: int = _L
    post_burden_2: int = _L
    post_burden_3: int = _L
    post_governance_1: int = _L
    post_governance_2: int = _L
    post_governance_3: int = _L
    post_governance_4: int = _L
    post_reliance_1: int = _L
    post_reliance_2: int = _L
    post_reliance_3: int = _L
    post_reliance_4: int = _L
    post_hallu_1: int = _L
    post_hallu_2: int = _L
    post_hallu_3: int = _L
    post_hallu_4: int = _L
    attn_post_1: int = _L
    post_calibration_1: int = _L
    post_calibration_2: int = _L
    post_calibration_3: int = _L
    post_dissent_1: int = _L
    post_dissent_2: int = _L
    post_dissent_3_reverse: int = _L
    post_accept_trust: int = _L
    post_accept_future_use: int = _L
    post_accept_limited_use: int = _L
    post_accept_optional: int = _L
    post_qual_ehr_redesign: str = Field(max_length=20000)
    post_qual_ai_autonomy: str = Field(max_length=20000)
    post_qual_infrastructure_impact: str = Field(max_length=20000)

    @field_validator(
        "post_qual_ehr_redesign",
        "post_qual_ai_autonomy",
        "post_qual_infrastructure_impact",
    )
    @classmethod
    def _strip_open_text(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("开放式补充题须填写后再提交")
        if len(s) > 20000:
            raise ValueError("单题回答长度超出上限")
        return s

    @model_validator(mode="after")
    def _attention_check(self) -> PostSurveyV7Payload:
        if self.attn_post_1 != 4:
            raise ValueError("注意力检测题须选择 4")
        return self


def post_survey_v7_all_threes() -> dict[str, int | str]:
    """测试用：Likert 除注意力题外均为 3，注意力题为 4；开放式题为占位文本。"""
    d: dict[str, int | str] = {k: 3 for k in POST_SURVEY_LIKERT_KEYS}
    d["attn_post_1"] = 4
    d["post_qual_ehr_redesign"] = (
        "测试作答占位：希望 EHR 减少重复文书与多系统切换，AI 可整合病史、预测随访并降低点击查找负担。"
    )
    d["post_qual_ai_autonomy"] = (
        "测试作答占位：可将风险提醒、信息整理与低风险流程交给 AI；诊断治疗决策与最终责任不可交出。"
    )
    d["post_qual_infrastructure_impact"] = (
        "测试作答占位：基础设施化或重塑临床能力但带来责任模糊；医院应建立 AI 审核岗位、审计记录与问责机制。"
    )
    return d
