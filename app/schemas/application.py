"""Application-pack output schemas."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from app.schemas.base import JobPilotBaseModel, NonEmptyStr
from app.schemas.common import ToolError, ToolWarning


class FactCheckStatus(StrEnum):
    """Fact-check result labels for generated application content."""

    VERIFIED = "verified"
    NEEDS_REVIEW = "needs_review"
    UNSUPPORTED = "unsupported"


class EvidenceBackedStatement(JobPilotBaseModel):
    """Statement that must cite evidence."""

    text: NonEmptyStr
    evidence_ids: list[NonEmptyStr] = Field(min_length=1)


class ResumeAdjustmentSuggestion(JobPilotBaseModel):
    """Actionable resume-edit suggestion that may cite supporting evidence."""

    suggestion: NonEmptyStr
    rationale: NonEmptyStr
    evidence_ids: list[NonEmptyStr] = Field(default_factory=list)


class FactCheckItem(JobPilotBaseModel):
    """Fact check record for generated material."""

    statement: NonEmptyStr
    status: FactCheckStatus
    evidence_ids: list[NonEmptyStr] = Field(min_length=1)
    notes: NonEmptyStr | None = None


class ApplicationPack(JobPilotBaseModel):
    """Final application-pack output presented to the user."""

    application_pack_id: NonEmptyStr
    candidate_summary: list[EvidenceBackedStatement] = Field(default_factory=list)
    role_fit_summary: list[EvidenceBackedStatement] = Field(default_factory=list)
    resume_adjustment_suggestions: list[ResumeAdjustmentSuggestion] = Field(
        default_factory=list
    )
    cover_letter_points: list[EvidenceBackedStatement] = Field(default_factory=list)
    fact_check_items: list[FactCheckItem] = Field(default_factory=list)
    warnings: list[ToolWarning] = Field(default_factory=list)
    errors: list[ToolError] = Field(default_factory=list)
