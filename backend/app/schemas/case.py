from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GuardrailContent(BaseModel):
    factsUsed: list[str] = Field(default_factory=list)
    riskCue: str = ""
    checklist: list[str] = Field(default_factory=list)


class CasePayload(BaseModel):
    """Case content returned to the frontend. Already filtered by condition."""

    id: str
    isPractice: bool
    riskLevel: str
    patientMessage: str
    chartSnapshot: dict[str, Any]
    aiDraft: str
    guardrail: GuardrailContent | None = None


class CaseResponse(BaseModel):
    case: CasePayload


# ---------------------------------------------------------------------------
# Raw JSON ingest schema (used by seed.py / validate_data.py)
# ---------------------------------------------------------------------------


class CaseRawGuardrail(BaseModel):
    factsUsed: list[str]
    riskCue: str
    checklist: list[str]


class CaseRaw(BaseModel):
    id: str
    isPractice: bool
    riskLevel: str
    defectPresent: bool
    defectType: str | None = None
    purpose: str | None = None
    patientMessage: str
    chartSnapshot: dict[str, Any]
    aiDraft: str
    guardrail: CaseRawGuardrail
    goldAction: str
    goldActionAlternates: list[str] = Field(default_factory=list)
