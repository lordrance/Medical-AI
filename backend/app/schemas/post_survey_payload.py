"""问卷 7.0 后测 payload：固定 41 个 Likert 题 + 注意力检测。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

_L = Field(ge=1, le=5)


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

    @model_validator(mode="after")
    def _attention_check(self) -> PostSurveyV7Payload:
        if self.attn_post_1 != 4:
            raise ValueError("注意力检测题须选择 4")
        return self


POST_SURVEY_V7_FIELD_IDS: list[str] = list(PostSurveyV7Payload.model_fields.keys())


def post_survey_v7_all_threes() -> dict[str, int]:
    """测试用：除注意力题外均为 3，注意力题为 4。"""
    d = {k: 3 for k in POST_SURVEY_V7_FIELD_IDS}
    d["attn_post_1"] = 4
    return d
