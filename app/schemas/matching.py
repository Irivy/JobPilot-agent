"""Matching and fit-report schemas."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from app.schemas.base import JobPilotBaseModel, NonEmptyStr
from app.schemas.common import ToolError, ToolWarning
from app.schemas.job import JobRequirement


class RequirementMatchStatus(StrEnum):
    """Supported requirement match states."""

    MATCHED = "matched"
    PARTIALLY_MATCHED = "partially_matched"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NOT_MATCHED = "not_matched"


class FitScoreBand(StrEnum):
    """High-level score band labels."""

    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    UNCERTAIN = "uncertain"


class RequirementMatch(JobPilotBaseModel):
    """Match result for a single job requirement."""

    requirement: JobRequirement
    status: RequirementMatchStatus
    evidence_ids: list[NonEmptyStr] = Field(default_factory=list)
    gap_reason: NonEmptyStr | None = None
    score_contribution: float
    notes: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_evidence_expectations(self) -> RequirementMatch:
        """Enforce minimal consistency between match status and evidence."""

        if self.status in {
            RequirementMatchStatus.MATCHED,
            RequirementMatchStatus.PARTIALLY_MATCHED,
        } and not self.evidence_ids:
            msg = "evidence_ids must be provided for matched or partially_matched results"
            raise ValueError(msg)
        return self


class FitReport(JobPilotBaseModel):
    """Deterministic fit report structure produced by scoring logic."""

    fit_report_id: NonEmptyStr
    overall_score: float = Field(ge=0.0, le=100.0)
    score_band: FitScoreBand
    dimension_scores: list[RequirementMatch] = Field(default_factory=list)
    matched_evidence_ids: list[NonEmptyStr] = Field(default_factory=list)
    missing_requirements: list[JobRequirement] = Field(default_factory=list)
    uncertain_claims: list[RequirementMatch] = Field(default_factory=list)
    rationale_codes: list[NonEmptyStr] = Field(default_factory=list)
    warnings: list[ToolWarning] = Field(default_factory=list)
    errors: list[ToolError] = Field(default_factory=list)
