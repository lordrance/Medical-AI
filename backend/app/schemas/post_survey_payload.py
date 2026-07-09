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
    post_qual_l1_ehr_pain_ai_substitution: str = Field(max_length=20000)
    post_qual_l2_human_ai_boundary: str = Field(max_length=20000)
    post_qual_l3_system_transformation: str = Field(max_length=20000)
    # 手机号后 4 位，用于匹配作答与发放报酬。
    post_phone_last4: str = Field(min_length=4, max_length=4)

    @field_validator(
        "post_qual_l1_ehr_pain_ai_substitution",
        "post_qual_l2_human_ai_boundary",
        "post_qual_l3_system_transformation",
    )
    @classmethod
    def _strip_open_text(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("开放式补充题须填写后再提交")
        if len(s) > 20000:
            raise ValueError("单题回答长度超出上限")
        return s

    @field_validator("post_phone_last4")
    @classmethod
    def _validate_phone_last4(cls, v: str) -> str:
        s = v.strip()
        if not (len(s) == 4 and s.isdigit()):
            raise ValueError("请填写手机号后 4 位数字")
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
    d["post_qual_l1_ehr_pain_ai_substitution"] = (
        "测试作答占位：EHR 文档填写与多系统信息整合最费力；AI 可协助病史摘要、警报去重、自动结构化录入；诊断与告知仍需医生本人完成。"
    )
    d["post_qual_l2_human_ai_boundary"] = (
        "测试作答占位：Agentic AI 可独立承担行政工作、异常标记、风险预警；用药决策、诊断、敏感沟通与最终责任必须保留给医生；最担心 AI 越权调药的边界。"
    )
    d["post_qual_l3_system_transformation"] = (
        "测试作答占位：医院组织管理与分级诊疗将被重塑，医生角色更偏审核；最期待文书负担下降，最担心责任模糊与患者隐私风险。"
    )
    d["post_phone_last4"] = "1234"
    return d
