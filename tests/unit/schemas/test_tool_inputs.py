"""Tests for strongly typed agent-tool input contracts."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from app.schemas import (
    CandidateExperience,
    CandidateFact,
    CandidateProfile,
    CandidateSkill,
    CertificationItem,
    EducationItem,
    EvidenceConfidence,
    EvidenceItem,
    EvidenceSourceType,
    FileExtension,
    FitReport,
    FitScoreBand,
    GenerateApplicationPackInput,
    InspectProjectEvidenceInput,
    JobDetail,
    JobRequirement,
    JobRequirementType,
    JobSourceType,
    LoadCandidateProfileInput,
    LocalPathStr,
    ReadJobDetailInput,
    RequirementMatch,
    RequirementMatchStatus,
    RequirementPriority,
    ScoreJobFitInput,
    ScoringWeights,
    SearchJobsInput,
)
from pydantic import TypeAdapter, ValidationError


def make_evidence(
    evidence_id: str = "ev-1",
    source_type: EvidenceSourceType = EvidenceSourceType.RESUME,
) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        source_type=source_type,
        source_label="Resume",
        excerpt="Built backend APIs",
        confidence=EvidenceConfidence.HIGH,
    )


def make_candidate(evidence_id: str = "ev-1") -> CandidateProfile:
    return CandidateProfile(
        candidate_profile_id="candidate-1",
        summary_facts=[CandidateFact(text="Built APIs", evidence_ids=[evidence_id])],
        skills=[CandidateSkill(name="Python", evidence_ids=[evidence_id])],
        experiences=[
            CandidateExperience(
                title="Engineer",
                summary="Built services",
                evidence_ids=[evidence_id],
            )
        ],
        education=[
            EducationItem(
                institution="Example University",
                degree="BSc",
                evidence_ids=[evidence_id],
            )
        ],
        certifications=[
            CertificationItem(name="Cloud Certificate", evidence_ids=[evidence_id])
        ],
    )


def make_job() -> JobDetail:
    return JobDetail(
        job_id="job-1",
        source=JobSourceType.JOBS_DATASET,
        title="Backend Engineer",
        company="Acme",
    )


def make_fit_report(evidence_id: str = "ev-1") -> FitReport:
    return FitReport(
        fit_report_id="fit-1",
        overall_score=80,
        score_band=FitScoreBand.STRONG,
        matched_evidence_ids=[evidence_id],
    )


def make_valid_inputs() -> list[object]:
    evidence = make_evidence()
    candidate = make_candidate()
    job = make_job()
    fit_report = make_fit_report()
    return [
        LoadCandidateProfileInput(resume_text="Resume text", parsing_mode="auto"),
        SearchJobsInput(query="backend"),
        ReadJobDetailInput(job_id="job-1"),
        InspectProjectEvidenceInput(
            project_path=r"D:\projects\jobpilot-agent",
            skills_to_verify=["Python"],
            allowed_extensions=["py"],
        ),
        ScoreJobFitInput(
            target_job=job,
            candidate_profile=candidate,
            evidence_ledger=[evidence],
            scoring_version="v1",
        ),
        GenerateApplicationPackInput(
            candidate_profile=candidate,
            target_job=job,
            fit_report=fit_report,
            evidence_ledger=[evidence],
            output_language="zh-CN",
            tone="professional",
        ),
    ]


def test_all_six_inputs_construct_and_round_trip() -> None:
    for tool_input in make_valid_inputs():
        round_tripped = type(tool_input).model_validate(tool_input.model_dump())
        assert round_tripped == tool_input


def test_all_six_inputs_reject_unknown_fields() -> None:
    for tool_input in make_valid_inputs():
        payload = tool_input.model_dump()
        payload["webhook"] = "https://example.com"
        with pytest.raises(ValidationError):
            type(tool_input).model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"parsing_mode": "auto"},
        {
            "resume_text": "Resume text",
            "resume_path": "resume.pdf",
            "parsing_mode": "auto",
        },
    ],
)
def test_load_candidate_profile_requires_exactly_one_resume_source(
    payload: dict[str, str],
) -> None:
    with pytest.raises(ValidationError):
        LoadCandidateProfileInput.model_validate(payload)


@pytest.mark.parametrize(
    "path",
    [
        r"D:\projects\jobpilot-agent",
        "C:/projects/jobpilot-agent",
        r".\project",
        "../project",
        "project",
        "/home/user/project",
    ],
)
def test_local_path_accepts_local_path_forms(path: str) -> None:
    assert TypeAdapter(LocalPathStr).validate_python(path) == path


@pytest.mark.parametrize(
    "path",
    [
        "http://example.com/project",
        "https://example.com/project",
        "ftp://example.com/project",
        "file://server/share",
        "file:///home/user/project",
        r"\\server\share",
        "smb://server/share",
        "   ",
    ],
)
def test_local_path_rejects_network_locations(path: str) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(LocalPathStr).validate_python(path)


def test_search_requires_query_or_keywords() -> None:
    with pytest.raises(ValidationError):
        SearchJobsInput()


def test_search_normalizes_lists_and_validates_limit() -> None:
    tool_input = SearchJobsInput(
        keywords=["Python", "python", "FastAPI"],
        location_preferences=["Shanghai", "shanghai", "Remote"],
        limit=100,
    )

    assert tool_input.keywords == ["Python", "FastAPI"]
    assert tool_input.location_preferences == ["Shanghai", "Remote"]

    for invalid_limit in (0, 101):
        with pytest.raises(ValidationError):
            SearchJobsInput(query="backend", limit=invalid_limit)

    with pytest.raises(ValidationError):
        SearchJobsInput(keywords=[" "])


def test_read_job_detail_only_accepts_local_dataset_source() -> None:
    tool_input = ReadJobDetailInput.model_validate(
        {"job_id": "job-1", "source": "jobs_dataset"}
    )
    assert tool_input.source is JobSourceType.JOBS_DATASET

    with pytest.raises(ValidationError):
        ReadJobDetailInput(job_id="job-1", source=JobSourceType.PROVIDED_JD)


def test_file_extensions_are_normalized_and_deduplicated() -> None:
    tool_input = InspectProjectEvidenceInput(
        project_path="project",
        keywords=["schema"],
        allowed_extensions=["py", ".PY", " md "],
    )
    assert tool_input.allowed_extensions == [".py", ".md"]


@pytest.mark.parametrize("extension", ["", ".", "*", "*.py", "src/main.py", r"src\main.py"])
def test_file_extension_rejects_invalid_shapes(extension: str) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(FileExtension).validate_python(extension)


def test_project_inspection_validates_terms_and_file_limit() -> None:
    base_payload = {"project_path": "project", "allowed_extensions": ["py"]}

    with pytest.raises(ValidationError):
        InspectProjectEvidenceInput.model_validate(base_payload)

    for invalid_limit in (0, 1001):
        with pytest.raises(ValidationError):
            InspectProjectEvidenceInput.model_validate(
                {**base_payload, "keywords": ["schema"], "max_files": invalid_limit}
            )


def test_scoring_weights_validate_values_without_requiring_unit_sum() -> None:
    weights = ScoringWeights.model_validate({" skills ": 2.0, "experience": 3.0})
    assert weights.root == {"skills": 2.0, "experience": 3.0}

    for invalid_value in (-1.0, float("inf"), float("nan")):
        with pytest.raises(ValidationError):
            ScoringWeights.model_validate({"skills": invalid_value})

    with pytest.raises(ValidationError):
        ScoringWeights.model_validate({})

    with pytest.raises(ValidationError):
        ScoringWeights.model_validate({" ": 1.0})


def test_score_input_rejects_blank_version_and_duplicate_evidence() -> None:
    payload = {
        "target_job": make_job(),
        "candidate_profile": make_candidate(),
        "evidence_ledger": [make_evidence()],
        "scoring_version": " ",
    }
    with pytest.raises(ValidationError):
        ScoreJobFitInput.model_validate(payload)

    payload["scoring_version"] = "v1"
    payload["evidence_ledger"] = [make_evidence(), make_evidence()]
    with pytest.raises(ValidationError):
        ScoreJobFitInput.model_validate(payload)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: ScoreJobFitInput(
            target_job=make_job(),
            candidate_profile=make_candidate("missing"),
            evidence_ledger=[make_evidence()],
            scoring_version="v1",
        ),
        lambda: GenerateApplicationPackInput(
            candidate_profile=make_candidate(),
            target_job=make_job(),
            fit_report=make_fit_report("missing"),
            evidence_ledger=[make_evidence()],
            output_language="en",
            tone="concise",
        ),
    ],
)
def test_tool_inputs_reject_missing_evidence_references(
    factory: Callable[[], object],
) -> None:
    with pytest.raises(ValidationError):
        factory()


def test_evidence_ledgers_may_include_unreferenced_evidence() -> None:
    evidence_ledger = [make_evidence(), make_evidence("ev-unused")]

    score_input = ScoreJobFitInput(
        target_job=make_job(),
        candidate_profile=make_candidate(),
        evidence_ledger=evidence_ledger,
        scoring_version="v1",
    )
    application_input = GenerateApplicationPackInput(
        candidate_profile=make_candidate(),
        target_job=make_job(),
        fit_report=make_fit_report(),
        evidence_ledger=evidence_ledger,
        output_language="en",
        tone="concise",
    )

    assert len(score_input.evidence_ledger) == 2
    assert len(application_input.evidence_ledger) == 2


def test_application_input_checks_all_fit_report_evidence_references() -> None:
    requirement = JobRequirement(
        requirement_id="req-1",
        text="Python experience",
        requirement_type=JobRequirementType.SKILL,
        priority=RequirementPriority.REQUIRED,
    )
    fit_report = FitReport(
        fit_report_id="fit-1",
        overall_score=50,
        score_band=FitScoreBand.MODERATE,
        dimension_scores=[
            RequirementMatch(
                requirement=requirement,
                status=RequirementMatchStatus.MATCHED,
                evidence_ids=["missing-dimension"],
                score_contribution=10,
            )
        ],
        uncertain_claims=[
            RequirementMatch(
                requirement=requirement,
                status=RequirementMatchStatus.INSUFFICIENT_EVIDENCE,
                evidence_ids=["missing-uncertain"],
                score_contribution=0,
            )
        ],
    )

    with pytest.raises(ValidationError):
        GenerateApplicationPackInput(
            candidate_profile=make_candidate(),
            target_job=make_job(),
            fit_report=fit_report,
            evidence_ledger=[make_evidence()],
            output_language="en",
            tone="concise",
        )
