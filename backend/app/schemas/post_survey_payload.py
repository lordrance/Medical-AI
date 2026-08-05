"""问卷 7.0 后测 payload：Likert 题 + 注意力检测 + 末尾开放式补充题。

★ 中文：后测问卷的**校验规则**。这是数据质量的守门员。

医生提交后测时，整包答案先过这里。任何一项不合规就返回 422，
数据根本进不了数据库。所以库里的每一份后测问卷都是完整合规的。

★ 加一道新题必须同时改三个地方：
  1. frontend/src/lib/forms/postSurveyConfig.ts —— 前端显示
  2. 这个文件                                    —— 后端校验
  3. backend/data/post_survey.json               —— 题库存档
只改前端的话，医生能填，但一提交就被这里挡下来报 422。

★ 字段名 = 数据库 JSON 的键名 = 导出 CSV 的列名 = 论文编码表的变量名。
四者必须一致，所以不能改名。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# 所有量表题共用的约束：必须是 1~5 的整数。
# 提出来复用，省得写 40 多遍 Field(ge=1, le=5)。
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
    """与 `backend/data/post_survey.json` 中各题 `id` 一致。

    下面每一行 `xxx: int = _L` 的意思是：必须有这个字段，且值在 1~5 之间。
    字段名的前缀标明了它属于哪个测量维度：
      pre_ai_readiness_*  数字工具接受度      post_utility_*      有用性
      post_transparency_* 透明度              post_comm_*         沟通质量
      post_burden_*       负担                post_governance_*   治理/责任
      post_reliance_*     依赖程度            post_hallu_*        对幻觉的担忧
      post_calibration_*  信任校准            post_dissent_*      表达异议
      post_accept_*       接受意愿            attn_post_1         ★注意力检查
    """

    # ★ extra="forbid"：出现任何未定义的字段就报错。
    # 这样前端多传了字段（比如改题目时漏删了旧题）会被立刻发现，
    # 而不是把脏数据静默地存进数据库。
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
    # 三道开放题（L1/L2/L3）。上限 2 万字，防止有人粘贴超大文本撑爆数据库。
    post_qual_l1_ehr_pain_ai_substitution: str = Field(max_length=20000)  # EHR 痛点与 AI 可替代性
    post_qual_l2_human_ai_boundary: str = Field(max_length=20000)         # 人机职责边界
    post_qual_l3_system_transformation: str = Field(max_length=20000)     # 医疗体系变革
    # 手机号后 4 位，用于匹配作答与发放报酬。
    post_phone_last4: str = Field(min_length=4, max_length=4)

    @field_validator(
        "post_qual_l1_ehr_pain_ai_substitution",
        "post_qual_l2_human_ai_boundary",
        "post_qual_l3_system_transformation",
    )
    @classmethod
    def _strip_open_text(cls, v: str) -> str:
        """三道开放题的校验：去掉首尾空白，且不能是空的。

        ★ 关键是 strip 之后再判断。否则医生打几个空格就能过关，
        存进来一堆空白字符串，质性分析时全是废数据。
        """
        s = v.strip()
        if not s:
            raise ValueError("开放式补充题须填写后再提交")
        if len(s) > 20000:
            raise ValueError("单题回答长度超出上限")
        return s  # 返回值会**替换**原值，所以存进库的是已经 strip 过的

    @field_validator("post_phone_last4")
    @classmethod
    def _validate_phone_last4(cls, v: str) -> str:
        """手机尾号必须正好 4 位纯数字。上面的 min/max_length 只管长度，
        这里还要确认全是数字（防止填 "abcd"）。"""
        s = v.strip()
        if not (len(s) == 4 and s.isdigit()):
            raise ValueError("请填写手机号后 4 位数字")
        return s

    @model_validator(mode="after")
    def _attention_check(self) -> PostSurveyV7Payload:
        """★ 注意力检查。题干明写「请在本题选择 4」，没选 4 就直接拒收。

        用来筛掉「一路点到底」的敷衍作答者——问卷研究的标准做法。
        mode="after" 表示等所有字段都校验完了再跑这个整体检查。
        """
        if self.attn_post_1 != 4:
            raise ValueError("注意力检测题须选择 4")
        return self


def post_survey_v7_all_threes() -> dict[str, int | str]:
    """测试用：Likert 除注意力题外均为 3，注意力题为 4；开放式题为占位文本。

    中文：生成一份合规的假答案，给自动化测试和压测脚本用。
    ★ 加了新题之后这个函数也要跟着补，否则所有用到它的测试都会 422 失败——
    这其实是个有用的提醒机制。
    """
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
