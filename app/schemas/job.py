"""Job domain schemas."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from app.schemas.base import JobPilotBaseModel, NonEmptyStr
from app.schemas.common import ToolError, ToolWarning


class JobSourceType(StrEnum):
    """Source of a normalized job record."""

    PROVIDED_JD = "provided_jd"
    JOBS_DATASET = "jobs_dataset"


class JobRequirementType(StrEnum):
    """High-level requirement categories."""

    SKILL = "skill"
    EXPERIENCE = "experience"
    EDUCATION = "education"
    CERTIFICATION = "certification"
    RESPONSIBILITY = "responsibility"
    OTHER = "other"


class RequirementPriority(StrEnum):
    """Priority label for a job requirement."""

    REQUIRED = "required"
    PREFERRED = "preferred"
    BONUS = "bonus"


class JobRequirement(JobPilotBaseModel):
    """Structured job requirement."""

    requirement_id: NonEmptyStr
    text: NonEmptyStr
    requirement_type: JobRequirementType
    priority: RequirementPriority
    is_required: bool = True
    is_scorable: bool = True


class JobSummary(JobPilotBaseModel):
    """Compact job summary returned by search results."""

    job_id: NonEmptyStr
    source: JobSourceType
    title: NonEmptyStr
    company: NonEmptyStr
    location: NonEmptyStr | None = None
    employment_type: NonEmptyStr | None = None
    summary: NonEmptyStr | None = None


class JobDetail(JobPilotBaseModel):
    """Normalized job detail record for both provided JD and local job data."""

    job_id: NonEmptyStr
    source: JobSourceType
    title: NonEmptyStr
    company: NonEmptyStr
    location: NonEmptyStr | None = None
    employment_type: NonEmptyStr | None = None
    responsibilities: list[NonEmptyStr] = Field(default_factory=list)
    requirements: list[JobRequirement] = Field(default_factory=list)
    preferred_qualifications: list[JobRequirement] = Field(default_factory=list)
    raw_text: NonEmptyStr | None = None
    warnings: list[ToolWarning] = Field(default_factory=list)
    errors: list[ToolError] = Field(default_factory=list)
