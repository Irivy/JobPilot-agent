"""Strongly typed output contracts for JobPilot agent tools."""

from __future__ import annotations

from typing import Annotated, Literal, Protocol

from pydantic import AfterValidator, Field, field_validator, model_validator

from app.schemas.application import ApplicationPack
from app.schemas.base import JobPilotBaseModel
from app.schemas.candidate import CandidateProfile
from app.schemas.common import ToolError, ToolWarning
from app.schemas.evidence import EvidenceItem, EvidenceSourceType
from app.schemas.job import JobDetail, JobSourceType, JobSummary
from app.schemas.matching import FitReport
from app.schemas.tool_inputs import (
    LocalPathStr,
    SearchJobsInput,
    _candidate_evidence_ids,
)


def _validate_recoverable_errors(errors: list[ToolError]) -> list[ToolError]:
    if any(not error.recoverable for error in errors):
        msg = "successful tool results may only contain recoverable errors"
        raise ValueError(msg)
    return errors


class _HasToolErrors(Protocol):
    errors: list[ToolError]


def _validate_domain_success[DomainResult: _HasToolErrors](
    result: DomainResult,
) -> DomainResult:
    _validate_recoverable_errors(result.errors)
    return result


class ToolFailure(JobPilotBaseModel):
    """Failure branch used when no valid domain result can be constructed."""

    status: Literal["failure"] = "failure"
    warnings: list[ToolWarning] = Field(default_factory=list)
    errors: list[ToolError] = Field(min_length=1)


class CandidateProfileSuccess(JobPilotBaseModel):
    """Successful candidate-profile result and its extracted evidence."""

    candidate_profile: CandidateProfile
    evidence_items: list[EvidenceItem] = Field(default_factory=list)
    warnings: list[ToolWarning] = Field(default_factory=list)
    errors: list[ToolError] = Field(default_factory=list)

    @field_validator("errors")
    @classmethod
    def validate_errors(cls, errors: list[ToolError]) -> list[ToolError]:
        return _validate_recoverable_errors(errors)

    @model_validator(mode="after")
    def validate_evidence_items(self) -> CandidateProfileSuccess:
        evidence_ids = {item.evidence_id for item in self.evidence_items}
        if len(evidence_ids) != len(self.evidence_items):
            msg = "evidence_items must not contain duplicate evidence_id values"
            raise ValueError(msg)

        missing_ids = _candidate_evidence_ids(self.candidate_profile) - evidence_ids
        if missing_ids:
            msg = f"candidate evidence_ids are missing from evidence_items: {sorted(missing_ids)}"
            raise ValueError(msg)
        return self


type CandidateProfileResult = CandidateProfileSuccess | ToolFailure


class JobSearchSuccess(JobPilotBaseModel):
    """Successful local job-search result."""

    results: list[JobSummary] = Field(default_factory=list)
    result_count: int = Field(ge=0)
    applied_filters: SearchJobsInput
    search_source: Literal[JobSourceType.JOBS_DATASET] = JobSourceType.JOBS_DATASET
    warnings: list[ToolWarning] = Field(default_factory=list)
    errors: list[ToolError] = Field(default_factory=list)

    @field_validator("errors")
    @classmethod
    def validate_errors(cls, errors: list[ToolError]) -> list[ToolError]:
        return _validate_recoverable_errors(errors)

    @model_validator(mode="after")
    def validate_results(self) -> JobSearchSuccess:
        if self.result_count != len(self.results):
            msg = "result_count must equal the number of results"
            raise ValueError(msg)

        job_ids = {result.job_id for result in self.results}
        if len(job_ids) != len(self.results):
            msg = "results must not contain duplicate job_id values"
            raise ValueError(msg)
        return self


type JobSearchResult = JobSearchSuccess | ToolFailure


class EvidenceScanSuccess(JobPilotBaseModel):
    """Successful local project-evidence scan result."""

    project_path: LocalPathStr
    evidence_hits: list[EvidenceItem] = Field(default_factory=list)
    files_scanned: int = Field(ge=0)
    truncated: bool
    warnings: list[ToolWarning] = Field(default_factory=list)
    errors: list[ToolError] = Field(default_factory=list)

    @field_validator("errors")
    @classmethod
    def validate_errors(cls, errors: list[ToolError]) -> list[ToolError]:
        return _validate_recoverable_errors(errors)

    @model_validator(mode="after")
    def validate_evidence_hits(self) -> EvidenceScanSuccess:
        evidence_ids = {item.evidence_id for item in self.evidence_hits}
        if len(evidence_ids) != len(self.evidence_hits):
            msg = "evidence_hits must not contain duplicate evidence_id values"
            raise ValueError(msg)

        if any(
            item.source_type is not EvidenceSourceType.PROJECT
            for item in self.evidence_hits
        ):
            msg = "evidence_hits must only contain project evidence"
            raise ValueError(msg)
        return self


type EvidenceScanResult = EvidenceScanSuccess | ToolFailure
type ReadJobDetailResult = (
    Annotated[JobDetail, AfterValidator(_validate_domain_success)] | ToolFailure
)
type ScoreJobFitResult = (
    Annotated[FitReport, AfterValidator(_validate_domain_success)] | ToolFailure
)
type GenerateApplicationPackResult = (
    Annotated[ApplicationPack, AfterValidator(_validate_domain_success)] | ToolFailure
)
