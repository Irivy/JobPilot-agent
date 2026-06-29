"""Candidate domain schemas."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from app.schemas.base import JobPilotBaseModel, NonEmptyStr


class CandidateSkillLevel(StrEnum):
    """Normalized skill familiarity labels."""

    BASIC = "basic"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class CandidateFact(JobPilotBaseModel):
    """Fact statement that must be traceable to evidence."""

    text: NonEmptyStr
    evidence_ids: list[NonEmptyStr] = Field(min_length=1)


class CandidateSkill(JobPilotBaseModel):
    """Candidate skill with explicit evidence references."""

    name: NonEmptyStr
    level: CandidateSkillLevel | None = None
    evidence_ids: list[NonEmptyStr] = Field(min_length=1)
    notes: NonEmptyStr | None = None


class CandidateExperience(JobPilotBaseModel):
    """Candidate work or project experience entry."""

    title: NonEmptyStr
    organization: NonEmptyStr | None = None
    project_name: NonEmptyStr | None = None
    start_date: NonEmptyStr | None = None
    end_date: NonEmptyStr | None = None
    is_current: bool = False
    summary: NonEmptyStr
    highlights: list[NonEmptyStr] = Field(default_factory=list)
    evidence_ids: list[NonEmptyStr] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_current_experience(self) -> CandidateExperience:
        """Current roles should not also declare an end date."""

        if self.is_current and self.end_date is not None:
            msg = "end_date must be omitted when is_current is true"
            raise ValueError(msg)
        return self


class EducationItem(JobPilotBaseModel):
    """Education entry with evidence linkage."""

    institution: NonEmptyStr
    degree: NonEmptyStr
    field_of_study: NonEmptyStr | None = None
    start_date: NonEmptyStr | None = None
    end_date: NonEmptyStr | None = None
    summary: NonEmptyStr | None = None
    evidence_ids: list[NonEmptyStr] = Field(min_length=1)


class CertificationItem(JobPilotBaseModel):
    """Certification entry with evidence linkage."""

    name: NonEmptyStr
    issuer: NonEmptyStr | None = None
    issued_date: NonEmptyStr | None = None
    expires_date: NonEmptyStr | None = None
    credential_id: NonEmptyStr | None = None
    summary: NonEmptyStr | None = None
    evidence_ids: list[NonEmptyStr] = Field(min_length=1)


class CandidateProfile(JobPilotBaseModel):
    """Structured candidate profile extracted from resume evidence."""

    candidate_profile_id: NonEmptyStr
    summary_facts: list[CandidateFact] = Field(default_factory=list)
    skills: list[CandidateSkill] = Field(default_factory=list)
    experiences: list[CandidateExperience] = Field(default_factory=list)
    education: list[EducationItem] = Field(default_factory=list)
    certifications: list[CertificationItem] = Field(default_factory=list)
    missing_fields: list[NonEmptyStr] = Field(default_factory=list)
    headline: NonEmptyStr | None = None
    target_role_hint: NonEmptyStr | None = None
