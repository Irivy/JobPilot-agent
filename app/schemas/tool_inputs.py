"""Strongly typed input contracts for JobPilot agent tools."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BeforeValidator,
    ConfigDict,
    Field,
    RootModel,
    field_validator,
    model_validator,
)

from app.schemas.base import JobPilotBaseModel, NonEmptyStr
from app.schemas.candidate import CandidateProfile
from app.schemas.evidence import EvidenceItem
from app.schemas.job import JobDetail, JobSourceType
from app.schemas.matching import FitReport

_URI_SCHEME = re.compile(r"^([a-z][a-z0-9+.-]*):", re.IGNORECASE)
_FILE_EXTENSION = re.compile(r"^\.[a-z0-9]+$")


def _validate_local_path(value: str) -> str:
    """Reject network locations without resolving or accessing the path."""

    if value.startswith(("\\\\", "//")):
        msg = "network and UNC paths are not allowed"
        raise ValueError(msg)

    scheme_match = _URI_SCHEME.match(value)
    if scheme_match is not None and len(scheme_match.group(1)) > 1:
        msg = "URI paths are not allowed"
        raise ValueError(msg)
    return value


LocalPathStr = Annotated[NonEmptyStr, AfterValidator(_validate_local_path)]


def _normalize_file_extension(value: object) -> object:
    """Normalize extension strings before applying their shape constraint."""

    if not isinstance(value, str):
        return value

    normalized = value.strip().lower()
    if not normalized.startswith("."):
        normalized = f".{normalized}"
    return normalized


def _validate_file_extension(value: str) -> str:
    if not _FILE_EXTENSION.fullmatch(value):
        msg = "file extension must contain only a leading dot and alphanumeric characters"
        raise ValueError(msg)
    return value


FileExtension = Annotated[
    str,
    BeforeValidator(_normalize_file_extension),
    AfterValidator(_validate_file_extension),
]
NonNegativeFiniteFloat = Annotated[float, Field(ge=0.0, allow_inf_nan=False)]


class ScoringWeights(RootModel[dict[NonEmptyStr, NonNegativeFiniteFloat]]):
    """Extensible scoring weight mapping without prescribing dimensions."""

    model_config = ConfigDict(validate_assignment=True)
    root: dict[NonEmptyStr, NonNegativeFiniteFloat] = Field(min_length=1)


def _deduplicate_casefold(values: list[str]) -> list[str]:
    """Remove case-insensitive duplicates while preserving input order."""

    seen: set[str] = set()
    deduplicated: list[str] = []
    for value in values:
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            deduplicated.append(value)
    return deduplicated


def _candidate_evidence_ids(candidate_profile: CandidateProfile) -> set[str]:
    """Collect every evidence reference carried by a candidate profile."""

    evidence_ids: set[str] = set()
    for fact in candidate_profile.summary_facts:
        evidence_ids.update(fact.evidence_ids)
    for skill in candidate_profile.skills:
        evidence_ids.update(skill.evidence_ids)
    for experience in candidate_profile.experiences:
        evidence_ids.update(experience.evidence_ids)
    for education in candidate_profile.education:
        evidence_ids.update(education.evidence_ids)
    for certification in candidate_profile.certifications:
        evidence_ids.update(certification.evidence_ids)
    return evidence_ids


def _fit_report_evidence_ids(fit_report: FitReport) -> set[str]:
    """Collect every evidence reference carried by a fit report."""

    evidence_ids = set(fit_report.matched_evidence_ids)
    for match in fit_report.dimension_scores:
        evidence_ids.update(match.evidence_ids)
    for claim in fit_report.uncertain_claims:
        evidence_ids.update(claim.evidence_ids)
    return evidence_ids


def _evidence_ledger_ids(evidence_ledger: list[EvidenceItem]) -> set[str]:
    evidence_ids = {item.evidence_id for item in evidence_ledger}
    if len(evidence_ids) != len(evidence_ledger):
        msg = "evidence_ledger must not contain duplicate evidence_id values"
        raise ValueError(msg)
    return evidence_ids


def _validate_evidence_references(
    referenced_ids: set[str],
    evidence_ledger: list[EvidenceItem],
) -> None:
    ledger_ids = _evidence_ledger_ids(evidence_ledger)
    missing_ids = referenced_ids - ledger_ids
    if missing_ids:
        msg = f"referenced evidence_ids are missing from evidence_ledger: {sorted(missing_ids)}"
        raise ValueError(msg)


class LoadCandidateProfileInput(JobPilotBaseModel):
    """Input contract for loading a candidate profile."""

    resume_text: NonEmptyStr | None = None
    resume_path: LocalPathStr | None = None
    parsing_mode: NonEmptyStr
    target_role_hint: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_resume_source(self) -> LoadCandidateProfileInput:
        if (self.resume_text is None) == (self.resume_path is None):
            msg = "exactly one of resume_text or resume_path must be provided"
            raise ValueError(msg)
        return self


class SearchJobsInput(JobPilotBaseModel):
    """Input contract for searching the local jobs dataset."""

    query: NonEmptyStr | None = None
    location_preferences: list[NonEmptyStr] = Field(default_factory=list)
    keywords: list[NonEmptyStr] = Field(default_factory=list)
    seniority: NonEmptyStr | None = None
    work_mode: NonEmptyStr | None = None
    limit: int = Field(default=10, ge=1, le=100)

    @field_validator("location_preferences", "keywords")
    @classmethod
    def deduplicate_lists(cls, values: list[str]) -> list[str]:
        return _deduplicate_casefold(values)

    @model_validator(mode="after")
    def validate_search_terms(self) -> SearchJobsInput:
        if self.query is None and not self.keywords:
            msg = "query or at least one keyword must be provided"
            raise ValueError(msg)
        return self


class ReadJobDetailInput(JobPilotBaseModel):
    """Input contract for reading one local job record."""

    job_id: NonEmptyStr
    source: Literal[JobSourceType.JOBS_DATASET] = JobSourceType.JOBS_DATASET


class InspectProjectEvidenceInput(JobPilotBaseModel):
    """Input contract for inspecting an authorized local project path."""

    project_path: LocalPathStr
    skills_to_verify: list[NonEmptyStr] = Field(default_factory=list)
    keywords: list[NonEmptyStr] = Field(default_factory=list)
    max_files: int = Field(default=200, ge=1, le=1000)
    allowed_extensions: list[FileExtension] = Field(min_length=1)

    @field_validator("skills_to_verify", "keywords", "allowed_extensions")
    @classmethod
    def deduplicate_lists(cls, values: list[str]) -> list[str]:
        return _deduplicate_casefold(values)

    @model_validator(mode="after")
    def validate_scan_terms(self) -> InspectProjectEvidenceInput:
        if not self.skills_to_verify and not self.keywords:
            msg = "skills_to_verify or at least one keyword must be provided"
            raise ValueError(msg)
        return self


class ScoreJobFitInput(JobPilotBaseModel):
    """Input contract for deterministic job-fit scoring."""

    target_job: JobDetail
    candidate_profile: CandidateProfile
    evidence_ledger: list[EvidenceItem] = Field(min_length=1)
    scoring_version: NonEmptyStr
    weights: ScoringWeights | None = None

    @model_validator(mode="after")
    def validate_evidence_ledger(self) -> ScoreJobFitInput:
        _validate_evidence_references(
            _candidate_evidence_ids(self.candidate_profile),
            self.evidence_ledger,
        )
        return self


class GenerateApplicationPackInput(JobPilotBaseModel):
    """Input contract for generating an evidence-backed application pack."""

    candidate_profile: CandidateProfile
    target_job: JobDetail
    fit_report: FitReport
    evidence_ledger: list[EvidenceItem] = Field(min_length=1)
    output_language: NonEmptyStr
    tone: NonEmptyStr

    @model_validator(mode="after")
    def validate_evidence_ledger(self) -> GenerateApplicationPackInput:
        referenced_ids = _candidate_evidence_ids(self.candidate_profile)
        referenced_ids.update(_fit_report_evidence_ids(self.fit_report))
        _validate_evidence_references(referenced_ids, self.evidence_ledger)
        return self
