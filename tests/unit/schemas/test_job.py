"""Tests for job schemas."""

from __future__ import annotations

from app.schemas import (
    JobDetail,
    JobRequirement,
    JobRequirementType,
    JobSourceType,
    JobSummary,
    RequirementPriority,
)
from pydantic import ValidationError


def make_requirement() -> JobRequirement:
    return JobRequirement(
        requirement_id="req-1",
        text="3+ years of Python experience",
        requirement_type=JobRequirementType.EXPERIENCE,
        priority=RequirementPriority.REQUIRED,
    )


def test_job_models_can_be_created() -> None:
    summary = JobSummary(
        job_id="job-1",
        source=JobSourceType.JOBS_DATASET,
        title="Backend Engineer",
        company="Acme",
        seniority="mid",
        work_mode="hybrid",
    )
    detail = JobDetail(
        job_id="job-1",
        source=JobSourceType.PROVIDED_JD,
        title="Backend Engineer",
        company="Acme",
        seniority="mid",
        work_mode="hybrid",
        responsibilities=["Build APIs"],
        requirements=[make_requirement()],
    )

    assert summary.job_id == "job-1"
    assert detail.source is JobSourceType.PROVIDED_JD
    assert JobSummary.model_validate(summary.model_dump()) == summary
    assert JobDetail.model_validate(detail.model_dump()) == detail


def test_job_summary_rejects_blank_title() -> None:
    try:
        JobSummary(
            job_id="job-1",
            source=JobSourceType.JOBS_DATASET,
            title=" ",
            company="Acme",
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("Expected blank job title to be rejected.")
