"""Offline integration test for the local jobs provider and tools."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.providers import LocalJobsProvider
from app.schemas import (
    JobDetail,
    JobSearchResult,
    JobSearchSuccess,
    ReadJobDetailInput,
    ReadJobDetailResult,
    SearchJobsInput,
)
from app.tools import read_job_detail, search_jobs
from pydantic import TypeAdapter

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = PROJECT_ROOT / "data" / "jobs.json"


def test_local_jobs_search_then_read_detail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    provider = LocalJobsProvider(DATASET_PATH)
    jobs = provider.list_jobs()
    requirement_ids = [
        requirement.requirement_id
        for job in jobs
        for requirement in [*job.requirements, *job.preferred_qualifications]
    ]

    assert len(jobs) == 7
    assert len(requirement_ids) == len(set(requirement_ids))

    search_result = search_jobs(
        SearchJobsInput(query="python backend"),
        provider=provider,
    )

    assert isinstance(search_result, JobSearchSuccess)
    assert search_result.results
    validated_search = TypeAdapter(JobSearchResult).validate_python(search_result)

    summary = validated_search.results[0]
    detail_result = read_job_detail(
        ReadJobDetailInput(job_id=summary.job_id),
        provider=provider,
    )

    assert isinstance(detail_result, JobDetail)
    validated_detail = TypeAdapter(ReadJobDetailResult).validate_python(detail_result)
    assert validated_detail.job_id == summary.job_id
    assert validated_detail.title == summary.title
    assert validated_detail.company == summary.company
