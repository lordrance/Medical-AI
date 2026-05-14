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
    post_qual_future_ai_roles: str = Field(max_length=20000)
    post_qual_trust_conditions: str = Field(max_length=20000)
    post_qual_workflow_responsibility: str = Field(max_length=20000)

    @field_validator(
        "post_qual_future_ai_roles",
        "post_qual_trust_conditions",
        "post_qual_workflow_responsibility",
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
    d["post_qual_future_ai_roles"] = (
        "测试作答占位：AI 可承担低风险文书与信息整理，临床判断与沟通仍由医生主导。"
    )
    d["post_qual_trust_conditions"] = (
        "测试作答占位：需来源依据、可解释性与审计记录，数据安全与人工把关可增强信任。"
    )
    d["post_qual_workflow_responsibility"] = (
        "测试作答占位：流程效率或提升，但需防范过度依赖；责任应由机构政策与临床把关共同界定。"
    )
    return d
