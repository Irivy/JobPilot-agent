"""Unit tests for deterministic local job tools."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.providers import (
    DuplicateJobIdError,
    JobNotFoundError,
    JobRecordInvalidError,
    JobsDatasetInvalidError,
    JobsDatasetNotFoundError,
    JobsDatasetReadError,
    JobsProviderError,
)
from app.schemas import (
    JobDetail,
    JobRequirement,
    JobRequirementType,
    JobSearchResult,
    JobSearchSuccess,
    JobSourceType,
    ReadJobDetailInput,
    ReadJobDetailResult,
    RequirementPriority,
    SearchJobsInput,
    ToolFailure,
)
from app.tools import jobs as jobs_module
from app.tools import read_job_detail, search_jobs
from pydantic import TypeAdapter


def make_requirement(
    text: str,
    *,
    requirement_id: str = "req-1",
) -> JobRequirement:
    return JobRequirement(
        requirement_id=requirement_id,
        text=text,
        requirement_type=JobRequirementType.SKILL,
        priority=RequirementPriority.REQUIRED,
    )


def make_job(
    job_id: str,
    *,
    title: str = "Backend Engineer",
    company: str = "Example Labs",
    location: str = "Shanghai",
    employment_type: str = "full_time",
    seniority: str = "mid",
    work_mode: str = "hybrid",
    summary: str = "Build reliable services",
    responsibilities: list[str] | None = None,
    requirements: list[JobRequirement] | None = None,
    preferred: list[JobRequirement] | None = None,
) -> JobDetail:
    return JobDetail(
        job_id=job_id,
        source=JobSourceType.JOBS_DATASET,
        title=title,
        company=company,
        location=location,
        employment_type=employment_type,
        seniority=seniority,
        work_mode=work_mode,
        summary=summary,
        responsibilities=responsibilities or ["Ship tested software"],
        requirements=requirements or [],
        preferred_qualifications=preferred or [],
        raw_text="Raw text is deliberately excluded from search scoring.",
    )


class FakeJobsProvider:
    def __init__(
        self,
        jobs: tuple[JobDetail, ...] = (),
        *,
        list_error: JobsProviderError | None = None,
        get_error: JobsProviderError | None = None,
    ) -> None:
        self.jobs = jobs
        self.list_error = list_error
        self.get_error = get_error

    def list_jobs(self) -> tuple[JobDetail, ...]:
        if self.list_error is not None:
            raise self.list_error
        return self.jobs

    def get_job(self, job_id: str) -> JobDetail:
        if self.get_error is not None:
            raise self.get_error
        for job in self.jobs:
            if job.job_id == job_id:
                return job
        raise JobNotFoundError(job_id)


@pytest.mark.parametrize(
    ("job", "query"),
    [
        (make_job("title", title="Python Backend Engineer"), "python"),
        (
            make_job(
                "requirement",
                requirements=[make_requirement("Python programming")],
            ),
            "python",
        ),
        (
            make_job(
                "preferred",
                preferred=[make_requirement("FastAPI experience")],
            ),
            "fastapi",
        ),
        (
            make_job(
                "content",
                summary="Distributed data systems",
                responsibilities=["Maintain streaming pipelines"],
            ),
            "streaming",
        ),
        (make_job("metadata", company="Python Harbor"), "python"),
        (make_job("chinese", title="数据平台工程师"), "数据平台"),
    ],
)
def test_search_matches_each_searchable_field(job: JobDetail, query: str) -> None:
    result = search_jobs(
        SearchJobsInput(query=query),
        provider=FakeJobsProvider((job,)),
    )

    assert isinstance(result, JobSearchSuccess)
    assert [item.job_id for item in result.results] == [job.job_id]


def test_search_normalizes_nfkc_case_punctuation_and_spaces() -> None:
    job = make_job("python", title="Python, Backend Engineer")

    result = search_jobs(
        SearchJobsInput(query="  ＰＹＴＨＯＮ，   BACKEND  "),
        provider=FakeJobsProvider((job,)),
    )

    assert isinstance(result, JobSearchSuccess)
    assert result.result_count == 1


def test_query_tokens_use_and_semantics() -> None:
    job = make_job("python", title="Python Engineer")

    result = search_jobs(
        SearchJobsInput(query="python missing"),
        provider=FakeJobsProvider((job,)),
    )

    assert isinstance(result, JobSearchSuccess)
    assert result.results == []


def test_search_rejects_terms_empty_after_normalization() -> None:
    result = search_jobs(
        SearchJobsInput(query="---"),
        provider=FakeJobsProvider((make_job("job-1"),)),
    )

    assert isinstance(result, ToolFailure)
    assert result.errors[0].code == "search_query_empty"
    assert result.errors[0].recoverable is True


def test_keywords_use_or_semantics_and_combine_with_query() -> None:
    matching = make_job(
        "matching",
        title="Python Engineer",
        requirements=[make_requirement("FastAPI development")],
    )
    query_only = make_job("query-only", title="Python Engineer")

    result = search_jobs(
        SearchJobsInput(
            query="python",
            keywords=["django", "fastapi"],
        ),
        provider=FakeJobsProvider((query_only, matching)),
    )

    assert isinstance(result, JobSearchSuccess)
    assert [item.job_id for item in result.results] == ["matching"]


def test_location_seniority_and_work_mode_filters_are_exact_and_composable() -> None:
    match = make_job(
        "match",
        location="Shanghai",
        seniority="senior",
        work_mode="remote",
    )
    wrong_location = make_job(
        "wrong-location",
        location="Beijing",
        seniority="senior",
        work_mode="remote",
    )
    wrong_seniority = make_job(
        "wrong-seniority",
        location="Shanghai",
        seniority="mid",
        work_mode="remote",
    )
    wrong_work_mode = make_job(
        "wrong-work-mode",
        location="Shanghai",
        seniority="senior",
        work_mode="onsite",
    )

    result = search_jobs(
        SearchJobsInput(
            query="engineer",
            location_preferences=["Beijing", "Shanghai"],
            seniority="SENIOR",
            work_mode="remote",
        ),
        provider=FakeJobsProvider(
            (wrong_location, wrong_seniority, wrong_work_mode, match)
        ),
    )

    assert isinstance(result, JobSearchSuccess)
    assert [item.job_id for item in result.results] == ["match", "wrong-location"]
    assert result.results[0].seniority == "senior"
    assert result.results[0].work_mode == "remote"

    exact_location_result = search_jobs(
        SearchJobsInput(query="engineer", location_preferences=["Shanghai"]),
        provider=FakeJobsProvider((wrong_location, match)),
    )
    assert isinstance(exact_location_result, JobSearchSuccess)
    assert [item.job_id for item in exact_location_result.results] == ["match"]


def test_raw_text_does_not_participate_in_search() -> None:
    job = make_job("job-1")

    result = search_jobs(
        SearchJobsInput(query="deliberately excluded"),
        provider=FakeJobsProvider((job,)),
    )

    assert isinstance(result, JobSearchSuccess)
    assert result.results == []


def test_search_uses_fixed_max_field_weights() -> None:
    title_job = make_job("1-title", title="Needle Engineer")
    requirement_job = make_job(
        "2-requirement",
        requirements=[make_requirement("Needle")],
    )
    preferred_job = make_job(
        "3-preferred",
        preferred=[make_requirement("Needle")],
    )
    summary_job = make_job("4-summary", summary="Needle")
    metadata_job = make_job("5-metadata", company="Needle")

    result = search_jobs(
        SearchJobsInput(keywords=["needle"]),
        provider=FakeJobsProvider(
            (
                metadata_job,
                summary_job,
                preferred_job,
                requirement_job,
                title_job,
            )
        ),
    )

    assert isinstance(result, JobSearchSuccess)
    assert [item.job_id for item in result.results] == [
        "1-title",
        "2-requirement",
        "3-preferred",
        "4-summary",
        "5-metadata",
    ]
    assert jobs_module._matches_search(
        title_job,
        SearchJobsInput(keywords=["needle"]),
    ) == (8, 1)


def test_same_term_uses_only_highest_weight_once() -> None:
    repeated = make_job(
        "z-repeated",
        title="Python Engineer",
        company="Python Company",
        summary="Python Python Python",
        requirements=[make_requirement("Python")],
    )

    score = jobs_module._matches_search(
        repeated,
        SearchJobsInput(keywords=["python", "PYTHON"]),
    )

    assert score == (8, 1)


def test_query_and_keyword_normalizing_to_same_term_score_once() -> None:
    job = make_job("job-1", title="Python Engineer")

    score = jobs_module._matches_search(
        job,
        SearchJobsInput(query="ＰＹＴＨＯＮ", keywords=["python"]),
    )

    assert score == (8, 1)


def test_title_hit_count_breaks_equal_score_tie() -> None:
    title_hit = make_job(
        "z-title-hit",
        title="Alpha Engineer",
        company="Beta",
    )
    no_title_hit = make_job(
        "a-no-title-hit",
        requirements=[make_requirement("Alpha")],
        preferred=[make_requirement("Beta")],
    )

    result = search_jobs(
        SearchJobsInput(query="alpha beta"),
        provider=FakeJobsProvider((no_title_hit, title_hit)),
    )

    assert isinstance(result, JobSearchSuccess)
    assert [item.job_id for item in result.results] == [
        "z-title-hit",
        "a-no-title-hit",
    ]


def test_job_id_breaks_full_tie_and_limit_applies_after_sorting() -> None:
    jobs = (
        make_job("job-B", title="Python Engineer"),
        make_job("job-a", title="Python Engineer"),
    )

    result = search_jobs(
        SearchJobsInput(query="python", limit=1),
        provider=FakeJobsProvider(jobs),
    )

    assert isinstance(result, JobSearchSuccess)
    assert [item.job_id for item in result.results] == ["job-a"]
    assert result.result_count == 1


@pytest.mark.parametrize("jobs", [(), (make_job("job-1"),)])
def test_zero_results_are_success_with_stable_warning(
    jobs: tuple[JobDetail, ...],
) -> None:
    result = search_jobs(
        SearchJobsInput(query="no-such-skill"),
        provider=FakeJobsProvider(jobs),
    )

    assert isinstance(result, JobSearchSuccess)
    assert result.results == []
    assert result.result_count == 0
    assert [warning.code for warning in result.warnings] == ["no_job_matches"]


@pytest.mark.parametrize(
    ("error", "expected_code", "expected_category"),
    [
        (
            JobsDatasetNotFoundError(Path("C:/private/jobs.json")),
            "jobs_dataset_missing",
            "dataset_missing",
        ),
        (
            JobsDatasetReadError(Path("C:/private/jobs.json")),
            "jobs_dataset_invalid",
            "dataset_read_error",
        ),
        (
            JobsDatasetInvalidError(Path("C:/private/jobs.json"), "bad"),
            "jobs_dataset_invalid",
            "dataset_validation_error",
        ),
        (
            DuplicateJobIdError(Path("C:/private/jobs.json"), "duplicate"),
            "jobs_dataset_invalid",
            "duplicate_job_id",
        ),
        (
            JobRecordInvalidError(Path("C:/private/jobs.json"), 3, "bad"),
            "jobs_dataset_invalid",
            "invalid_job_record",
        ),
    ],
)
def test_search_maps_provider_errors_without_leaking_paths(
    error: JobsProviderError,
    expected_code: str,
    expected_category: str,
) -> None:
    result = search_jobs(
        SearchJobsInput(query="python"),
        provider=FakeJobsProvider(list_error=error),
    )

    assert isinstance(result, ToolFailure)
    assert result.errors[0].code == expected_code
    assert result.errors[0].recoverable is False
    assert result.errors[0].context["category"] == expected_category
    assert "C:/private" not in str(result.model_dump())


def test_read_returns_known_job_without_modifying_it() -> None:
    job = make_job("job-1", title="Python Engineer")
    before = job.model_dump()

    result = read_job_detail(
        ReadJobDetailInput(job_id="job-1"),
        provider=FakeJobsProvider((job,)),
    )

    assert isinstance(result, JobDetail)
    assert result.title == "Python Engineer"
    assert job.model_dump() == before
    assert TypeAdapter(ReadJobDetailResult).validate_python(result) == result


def test_read_maps_job_not_found_to_recoverable_failure() -> None:
    result = read_job_detail(
        ReadJobDetailInput(job_id="missing"),
        provider=FakeJobsProvider(get_error=JobNotFoundError("missing")),
    )

    assert isinstance(result, ToolFailure)
    assert result.errors[0].code == "job_not_found"
    assert result.errors[0].recoverable is True
    assert result.errors[0].context["job_id"] == "missing"
    assert TypeAdapter(ReadJobDetailResult).validate_python(result) == result


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (
            JobsDatasetNotFoundError(Path("C:/private/jobs.json")),
            "jobs_dataset_missing",
        ),
        (
            JobsDatasetReadError(Path("C:/private/jobs.json")),
            "jobs_dataset_invalid",
        ),
        (
            JobsDatasetInvalidError(Path("C:/private/jobs.json"), "bad"),
            "jobs_dataset_invalid",
        ),
        (
            DuplicateJobIdError(Path("C:/private/jobs.json"), "duplicate"),
            "jobs_dataset_invalid",
        ),
        (
            JobRecordInvalidError(Path("C:/private/jobs.json"), 2, "bad"),
            "job_record_invalid",
        ),
    ],
)
def test_read_maps_provider_errors(
    error: JobsProviderError,
    expected_code: str,
) -> None:
    result = read_job_detail(
        ReadJobDetailInput(job_id="job-1"),
        provider=FakeJobsProvider(get_error=error),
    )

    assert isinstance(result, ToolFailure)
    assert result.errors[0].code == expected_code
    assert result.errors[0].recoverable is False
    assert "C:/private" not in str(result.model_dump())


def test_search_result_validates_and_provider_jobs_are_unchanged() -> None:
    job = make_job("job-1", title="Python Engineer")
    before = job.model_dump()

    result = search_jobs(
        SearchJobsInput(query="python"),
        provider=FakeJobsProvider((job,)),
    )

    assert TypeAdapter(JobSearchResult).validate_python(result) == result
    assert job.model_dump() == before
