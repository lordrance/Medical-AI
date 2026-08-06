"""
================================================================================
文件作用：题目的两套数据格式 —— 一套给前端，一套读题库文件
================================================================================

同样是"一道题"，在两个地方长得不一样：

  CasePayload / CaseResponse
      **发给前端**的格式。只包含医生该看到的内容。

  CaseRaw / CaseRawGuardrail
      **读 backend/data/cases.json** 用的格式。包含标准答案、
      埋了什么错等全部字段。

--------------------------------------------------------------------------------
★ 为什么要分成两套（这是本项目最重要的一处安全设计）
--------------------------------------------------------------------------------
CasePayload 这个类里**根本就没有定义** goldAction、defectPresent、
defectType 这几个字段。

所以就算哪天有人写代码时手滑，想把整个 case 对象直接返回给前端，
Pydantic 也会自动把这些字段丢掉——它只认自己声明过的字段。

如果不分两套、直接把数据库对象扔给前端，医生随便打开浏览器的开发者工具
（F12 → 网络），就能在返回内容里看到这道题的标准答案。整个实验就废了。

这种"靠类型定义来兜底"的做法比"记得别返回敏感字段"可靠得多——
前者是机器保证的，后者靠人记性。

--------------------------------------------------------------------------------
本文件的代码块（从上到下）：
--------------------------------------------------------------------------------
  第 1 块  GuardrailContent    风险提示面板的内容（V4 不显示）
  第 2 块  CasePayload         ★ 发给前端的题目（不含答案）
  第 3 块  CaseResponse        接口的最外层包装
  第 4 块  CaseRawGuardrail    读 JSON 用的 guardrail 段格式
  第 5 块  CaseRaw             ★ 读 JSON 用的完整格式（含答案）
================================================================================
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ── 第 1 块：风险提示面板内容 ────────────────────────────────────────────
class GuardrailContent(BaseModel):
    """V3 的「风险提示面板」内容。V4 单一条件，不再显示，恒为 None。"""

    factsUsed: list[str] = Field(default_factory=list)  # AI 用到了病历里的哪些事实
    riskCue: str = ""                                    # 风险提示语
    checklist: list[str] = Field(default_factory=list)   # 核对清单


# ── 第 2 块：发给前端的题目 ★ ───────────────────────────────────────────
class CasePayload(BaseModel):
    """Case content returned to the frontend. Already filtered by condition.

    ★ 发给医生的题目内容。注意这里**没有** goldAction、defectPresent、
    defectType、purpose —— 那些是答案和实验设计，绝不能出现在这里。
    """

    id: str
    isPractice: bool
    riskLevel: str                    # 高/低风险，前端目前不显示，保留供将来用
    patientMessage: str               # 患者发来的消息
    chartSnapshot: dict[str, Any]     # 病历摘要（键值对，前端折叠展示）
    aiDraft: str                      # ★ AI 起草的回复
    guardrail: GuardrailContent | None = None  # V4 恒为 None


# ── 第 3 块：接口的最外层包装 ───────────────────────────────────────────
class CaseResponse(BaseModel):
    """接口的最外层包装：{"case": {...}}。

    多包一层是为了将来能加同级字段（如 {"case":..., "meta":...}）
    而不破坏已有的前端代码。
    """

    case: CasePayload


# ---------------------------------------------------------------------------
# Raw JSON ingest schema (used by seed.py / validate_data.py)
# ---------------------------------------------------------------------------


# ── 第 4 块：读 JSON 用的 guardrail 段 ──────────────────────────────────
class CaseRawGuardrail(BaseModel):
    """cases.json 里 guardrail 段的格式。三个字段都必填（不像 CasePayload 有默认值），
    这样题目文件里漏写会在 seed 时立刻报错，而不是悄悄存成空。"""

    factsUsed: list[str]
    riskCue: str
    checklist: list[str]


# ── 第 5 块：读 JSON 用的完整格式 ★ ─────────────────────────────────────
class CaseRaw(BaseModel):
    """★ backend/data/cases.json 里一道题的完整格式。

    seed.py 灌数据、validate_data.py 校验数据时都按这个格式解析。
    你改题目时如果字段写错或漏写，运行 validate_data 会立刻报出来。
    """

    id: str
    isPractice: bool
    riskLevel: str
    # --- 实验设计字段（只存数据库，绝不发给前端）---
    defectPresent: bool                    # 这道题的 AI 草稿有没有埋错
    defectType: str | None = None          # 埋的是哪类错（漏诊提示、剂量错误…）
    purpose: str | None = None             # 这道题想测什么
    # --- 医生会看到的 ---
    patientMessage: str
    chartSnapshot: dict[str, Any]
    aiDraft: str
    guardrail: CaseRawGuardrail
    # --- 参考答案 ---
    goldAction: str                        # 标准答案
    # 次优但可接受的处理方式。★ 每道题至少要有一个，否则判分过于严苛。
    goldActionAlternates: list[str] = Field(default_factory=list)
