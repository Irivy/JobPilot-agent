"""Evidence domain schemas."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from app.schemas.base import JobPilotBaseModel, JsonValue, NonEmptyStr


class EvidenceSourceType(StrEnum):
    """Supported evidence source categories."""

    RESUME = "resume"
    PROVIDED_JD = "provided_jd"
    JOB_DATASET = "job_dataset"
    PROJECT = "project"
    USER_NOTE = "user_note"


class EvidenceConfidence(StrEnum):
    """Confidence levels for evidence-backed statements."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EvidenceItem(JobPilotBaseModel):
    """Atomic evidence record used across candidate, job, and report schemas."""

    evidence_id: NonEmptyStr
    source_type: EvidenceSourceType
    source_label: NonEmptyStr
    excerpt: NonEmptyStr
    locator: NonEmptyStr | None = None
    confidence: EvidenceConfidence
    related_skills: list[NonEmptyStr] = Field(default_factory=list)
    related_requirement_ids: list[NonEmptyStr] = Field(default_factory=list)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
