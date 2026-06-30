"""Tests for strongly typed agent-tool output contracts."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from app.schemas import (
    ApplicationPack,
    CandidateFact,
    CandidateProfile,
    CandidateProfileResult,
    CandidateProfileSuccess,
    EvidenceConfidence,
    EvidenceItem,
    EvidenceScanResult,
    EvidenceScanSuccess,
    EvidenceSourceType,
    FitReport,
    FitScoreBand,
    GenerateApplicationPackResult,
    JobDetail,
    JobSearchResult,
    JobSearchSuccess,
    JobSourceType,
    JobSummary,
    ReadJobDetailResult,
    ScoreJobFitResult,
    SearchJobsInput,
    ToolError,
    ToolFailure,
)
from pydantic import TypeAdapter, ValidationError


def make_error(recoverable: bool) -> ToolError:
    return ToolError(
        code="tool_error",
        message="Tool could not complete",
        recoverable=recoverable,
    )


def make_evidence(
    evidence_id: str = "ev-1",
    source_type: EvidenceSourceType = EvidenceSourceType.RESUME,
) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        source_type=source_type,
        source_label="Resume",
        excerpt="Built APIs",
        confidence=EvidenceConfidence.HIGH,
    )


def make_candidate(evidence_id: str = "ev-1") -> CandidateProfile:
    return CandidateProfile(
        candidate_profile_id="candidate-1",
        summary_facts=[CandidateFact(text="Built APIs", evidence_ids=[evidence_id])],
    )


def make_job(errors: list[ToolError] | None = None) -> JobDetail:
    return JobDetail(
        job_id="job-1",
        source=JobSourceType.JOBS_DATASET,
        title="Backend Engineer",
        company="Acme",
        errors=errors or [],
    )


def make_fit_report(errors: list[ToolError] | None = None) -> FitReport:
    return FitReport(
        fit_report_id="fit-1",
        overall_score=80,
        score_band=FitScoreBand.STRONG,
        errors=errors or [],
    )


def make_application_pack(
    errors: list[ToolError] | None = None,
) -> ApplicationPack:
    return ApplicationPack(application_pack_id="pack-1", errors=errors or [])


def make_candidate_success() -> CandidateProfileSuccess:
    return CandidateProfileSuccess(
        candidate_profile=make_candidate(),
        evidence_items=[make_evidence()],
    )


def make_job_search_success() -> JobSearchSuccess:
    return JobSearchSuccess(
        result_count=0,
        applied_filters=SearchJobsInput(query="backend"),
    )


def make_evidence_scan_success() -> EvidenceScanSuccess:
    return EvidenceScanSuccess(
        project_path="project",
        files_scanned=0,
        truncated=False,
    )


def test_tool_failure_requires_errors_with_any_recoverability() -> None:
    with pytest.raises(ValidationError):
        ToolFailure(errors=[])

    recoverable_failure = ToolFailure(errors=[make_error(recoverable=True)])
    nonrecoverable_failure = ToolFailure(errors=[make_error(recoverable=False)])

    assert recoverable_failure.status == "failure"
    assert nonrecoverable_failure.status == "failure"


def test_candidate_profile_success_validates_evidence_integrity() -> None:
    success = CandidateProfileSuccess(
        candidate_profile=make_candidate(),
        evidence_items=[make_evidence(), make_evidence("ev-unused")],
    )
    assert success.candidate_profile.candidate_profile_id == "candidate-1"
    assert len(success.evidence_items) == 2

    with pytest.raises(ValidationError):
        CandidateProfileSuccess(
            candidate_profile=make_candidate("missing"),
            evidence_items=[make_evidence()],
        )

    with pytest.raises(ValidationError):
        CandidateProfileSuccess(
            candidate_profile=make_candidate(),
            evidence_items=[make_evidence(), make_evidence()],
        )


def test_job_search_success_validates_count_and_unique_job_ids() -> None:
    job = JobSummary(
        job_id="job-1",
        source=JobSourceType.JOBS_DATASET,
        title="Backend Engineer",
        company="Acme",
    )
    filters = SearchJobsInput(query="backend")

    with pytest.raises(ValidationError):
        JobSearchSuccess(results=[job], result_count=0, applied_filters=filters)

    with pytest.raises(ValidationError):
        JobSearchSuccess(
            results=[job, job],
            result_count=2,
            applied_filters=filters,
        )


def test_evidence_scan_success_enforces_local_project_evidence() -> None:
    success = EvidenceScanSuccess(
        project_path=r"D:\projects\jobpilot-agent",
        evidence_hits=[make_evidence(source_type=EvidenceSourceType.PROJECT)],
        files_scanned=1,
        truncated=False,
    )
    assert success.project_path == r"D:\projects\jobpilot-agent"

    with pytest.raises(ValidationError):
        EvidenceScanSuccess(
            project_path="project",
            evidence_hits=[make_evidence(source_type=EvidenceSourceType.RESUME)],
            files_scanned=1,
            truncated=False,
        )

    with pytest.raises(ValidationError):
        EvidenceScanSuccess(
            project_path="project",
            files_scanned=-1,
            truncated=False,
        )

    with pytest.raises(ValidationError):
        EvidenceScanSuccess(
            project_path="project",
            evidence_hits=[
                make_evidence(source_type=EvidenceSourceType.PROJECT),
                make_evidence(source_type=EvidenceSourceType.PROJECT),
            ],
            files_scanned=1,
            truncated=False,
        )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: CandidateProfileSuccess(
            candidate_profile=CandidateProfile(candidate_profile_id="candidate-1"),
            errors=[make_error(recoverable=False)],
        ),
        lambda: JobSearchSuccess(
            result_count=0,
            applied_filters=SearchJobsInput(query="backend"),
            errors=[make_error(recoverable=False)],
        ),
        lambda: EvidenceScanSuccess(
            project_path="project",
            files_scanned=0,
            truncated=False,
            errors=[make_error(recoverable=False)],
        ),
    ],
)
def test_success_models_reject_nonrecoverable_errors(
    factory: Callable[[], object],
) -> None:
    with pytest.raises(ValidationError):
        factory()


@pytest.mark.parametrize(
    ("result_type", "success_factory"),
    [
        (CandidateProfileResult, make_candidate_success),
        (JobSearchResult, make_job_search_success),
        (ReadJobDetailResult, make_job),
        (EvidenceScanResult, make_evidence_scan_success),
        (ScoreJobFitResult, make_fit_report),
        (GenerateApplicationPackResult, make_application_pack),
    ],
)
def test_complete_result_types_validate_and_round_trip_success(
    result_type: object,
    success_factory: Callable[[], object],
) -> None:
    adapter = TypeAdapter(result_type)
    expected = success_factory()

    validated = adapter.validate_python(expected)
    dumped = adapter.dump_python(validated, mode="json")
    round_tripped = adapter.validate_python(dumped)

    assert type(validated) is type(expected)
    assert round_tripped == validated


@pytest.mark.parametrize(
    "result_type",
    [
        CandidateProfileResult,
        JobSearchResult,
        ReadJobDetailResult,
        EvidenceScanResult,
        ScoreJobFitResult,
        GenerateApplicationPackResult,
    ],
)
def test_complete_result_types_validate_and_round_trip_tool_failure(
    result_type: object,
) -> None:
    failure_payload = {
        "status": "failure",
        "errors": [
            {
                "code": "fatal",
                "message": "No result available",
                "recoverable": False,
            }
        ],
    }
    adapter = TypeAdapter(result_type)

    result = adapter.validate_python(failure_payload)
    round_tripped = adapter.validate_python(adapter.dump_python(result, mode="json"))

    assert isinstance(result, ToolFailure)
    assert round_tripped == result


@pytest.mark.parametrize(
    "result_type",
    [
        CandidateProfileResult,
        JobSearchResult,
        ReadJobDetailResult,
        EvidenceScanResult,
        ScoreJobFitResult,
        GenerateApplicationPackResult,
    ],
)
def test_complete_result_types_accept_recoverable_tool_failure(
    result_type: object,
) -> None:
    failure_payload = {
        "status": "failure",
        "errors": [
            {
                "code": "retryable",
                "message": "A retry may succeed",
                "recoverable": True,
            }
        ],
    }

    result = TypeAdapter(result_type).validate_python(failure_payload)

    assert isinstance(result, ToolFailure)
    assert result.errors[0].recoverable is True


@pytest.mark.parametrize(
    ("result_type", "domain_factory"),
    [
        (ReadJobDetailResult, make_job),
        (ScoreJobFitResult, make_fit_report),
        (GenerateApplicationPackResult, make_application_pack),
    ],
)
def test_direct_success_branches_accept_recoverable_errors(
    result_type: object,
    domain_factory: Callable[[list[ToolError] | None], object],
) -> None:
    expected = domain_factory([make_error(recoverable=True)])

    validated = TypeAdapter(result_type).validate_python(expected)

    assert validated == expected


@pytest.mark.parametrize(
    ("result_type", "domain_factory"),
    [
        (ReadJobDetailResult, make_job),
        (ScoreJobFitResult, make_fit_report),
        (GenerateApplicationPackResult, make_application_pack),
    ],
)
def test_direct_success_branches_reject_nonrecoverable_errors(
    result_type: object,
    domain_factory: Callable[[list[ToolError] | None], object],
) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(result_type).validate_python(
            domain_factory([make_error(recoverable=False)])
        )


@pytest.mark.parametrize(
    ("result_type", "success_factory"),
    [
        (CandidateProfileResult, make_candidate_success),
        (JobSearchResult, make_job_search_success),
        (ReadJobDetailResult, make_job),
        (EvidenceScanResult, make_evidence_scan_success),
        (ScoreJobFitResult, make_fit_report),
        (GenerateApplicationPackResult, make_application_pack),
    ],
)
def test_complete_result_types_reject_unknown_fields(
    result_type: object,
    success_factory: Callable[[], object],
) -> None:
    payload = success_factory().model_dump()
    payload["unknown_field"] = "unexpected"

    with pytest.raises(ValidationError):
        TypeAdapter(result_type).validate_python(payload)


def test_output_models_reject_side_effect_fields() -> None:
    payload = CandidateProfileSuccess(
        candidate_profile=make_candidate(),
        evidence_items=[make_evidence()],
    ).model_dump()
    payload["send_email"] = True

    with pytest.raises(ValidationError):
        CandidateProfileSuccess.model_validate(payload)
