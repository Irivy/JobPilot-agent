"""Unit tests for the local jobs provider."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.providers import (
    DuplicateJobIdError,
    JobNotFoundError,
    JobRecordInvalidError,
    JobsDatasetInvalidError,
    JobsDatasetNotFoundError,
    JobsDatasetReadError,
    LocalJobsProvider,
)
from app.schemas import (
    JobDetail,
    JobRequirement,
    JobRequirementType,
    JobSourceType,
    RequirementPriority,
    ToolError,
    ToolWarning,
)


def make_job(
    job_id: str = "job-1",
    *,
    title: str = "Python Backend Engineer",
) -> JobDetail:
    return JobDetail(
        job_id=job_id,
        source=JobSourceType.JOBS_DATASET,
        title=title,
        company="Example Labs",
        location="Shanghai",
        employment_type="full_time",
        seniority="mid",
        work_mode="hybrid",
        summary="Build Python services",
        responsibilities=["Build APIs"],
        raw_text="Python backend role",
    )


def write_dataset(path: Path, records: object) -> None:
    path.write_text(
        json.dumps(records, ensure_ascii=False),
        encoding="utf-8",
    )


def job_payload(job: JobDetail | None = None) -> dict[str, object]:
    return (job or make_job()).model_dump(mode="json", exclude={"warnings", "errors"})


def test_provider_lazily_loads_valid_dataset_and_preserves_order(tmp_path: Path) -> None:
    dataset_path = tmp_path / "jobs.json"
    provider = LocalJobsProvider(dataset_path)
    write_dataset(
        dataset_path,
        [
            job_payload(make_job("job-2", title="Second")),
            job_payload(make_job("job-1", title="First")),
        ],
    )

    jobs = provider.list_jobs()

    assert [job.job_id for job in jobs] == ["job-2", "job-1"]
    assert provider.get_job("job-1").title == "First"


def test_provider_accepts_empty_dataset(tmp_path: Path) -> None:
    dataset_path = tmp_path / "jobs.json"
    write_dataset(dataset_path, [])

    assert LocalJobsProvider(dataset_path).list_jobs() == ()


def test_provider_wraps_missing_file_with_cause(tmp_path: Path) -> None:
    provider = LocalJobsProvider(tmp_path / "missing.json")

    with pytest.raises(JobsDatasetNotFoundError) as exc_info:
        provider.list_jobs()

    assert isinstance(exc_info.value.__cause__, FileNotFoundError)


def test_provider_retries_after_failed_load(tmp_path: Path) -> None:
    dataset_path = tmp_path / "jobs.json"
    provider = LocalJobsProvider(dataset_path)

    with pytest.raises(JobsDatasetNotFoundError):
        provider.list_jobs()

    write_dataset(dataset_path, [job_payload()])

    assert provider.get_job("job-1").job_id == "job-1"


def test_provider_wraps_read_failure_with_cause(tmp_path: Path) -> None:
    provider = LocalJobsProvider(tmp_path)

    with pytest.raises(JobsDatasetReadError) as exc_info:
        provider.list_jobs()

    assert isinstance(exc_info.value.__cause__, OSError)


def test_provider_wraps_invalid_json_with_cause(tmp_path: Path) -> None:
    dataset_path = tmp_path / "jobs.json"
    dataset_path.write_text("{invalid", encoding="utf-8")

    with pytest.raises(JobsDatasetInvalidError) as exc_info:
        LocalJobsProvider(dataset_path).list_jobs()

    assert isinstance(exc_info.value.__cause__, json.JSONDecodeError)


def test_provider_rejects_non_list_top_level(tmp_path: Path) -> None:
    dataset_path = tmp_path / "jobs.json"
    write_dataset(dataset_path, {"jobs": []})

    with pytest.raises(JobsDatasetInvalidError, match="top-level"):
        LocalJobsProvider(dataset_path).list_jobs()


def test_provider_wraps_invalid_record_with_index_and_cause(tmp_path: Path) -> None:
    dataset_path = tmp_path / "jobs.json"
    write_dataset(dataset_path, [{"job_id": "missing-fields"}])

    with pytest.raises(JobRecordInvalidError) as exc_info:
        LocalJobsProvider(dataset_path).list_jobs()

    assert exc_info.value.record_index == 0
    assert exc_info.value.__cause__ is not None


def test_get_job_validates_dataset_before_reporting_unknown_id(tmp_path: Path) -> None:
    dataset_path = tmp_path / "jobs.json"
    write_dataset(dataset_path, [{"job_id": "invalid-record"}])

    with pytest.raises(JobRecordInvalidError):
        LocalJobsProvider(dataset_path).get_job("unknown")


def test_provider_rejects_non_dataset_source(tmp_path: Path) -> None:
    dataset_path = tmp_path / "jobs.json"
    payload = job_payload()
    payload["source"] = "provided_jd"
    write_dataset(dataset_path, [payload])

    with pytest.raises(JobRecordInvalidError, match="source"):
        LocalJobsProvider(dataset_path).list_jobs()


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        (
            "warnings",
            [{"code": "runtime_warning", "message": "Do not persist"}],
        ),
        (
            "errors",
            [
                {
                    "code": "runtime_error",
                    "message": "Do not persist",
                    "recoverable": False,
                }
            ],
        ),
    ],
)
def test_provider_rejects_runtime_messages(
    tmp_path: Path,
    field_name: str,
    field_value: list[dict[str, object]],
) -> None:
    dataset_path = tmp_path / "jobs.json"
    payload = job_payload()
    payload[field_name] = field_value
    write_dataset(dataset_path, [payload])

    with pytest.raises(JobRecordInvalidError, match="runtime"):
        LocalJobsProvider(dataset_path).list_jobs()


def test_provider_rejects_duplicate_job_ids(tmp_path: Path) -> None:
    dataset_path = tmp_path / "jobs.json"
    write_dataset(dataset_path, [job_payload(), job_payload()])

    with pytest.raises(DuplicateJobIdError) as exc_info:
        LocalJobsProvider(dataset_path).list_jobs()

    assert exc_info.value.job_id == "job-1"


def test_provider_raises_for_unknown_job_id(tmp_path: Path) -> None:
    dataset_path = tmp_path / "jobs.json"
    write_dataset(dataset_path, [job_payload()])

    with pytest.raises(JobNotFoundError) as exc_info:
        LocalJobsProvider(dataset_path).get_job("unknown")

    assert exc_info.value.job_id == "unknown"
    assert isinstance(exc_info.value.__cause__, KeyError)


def test_provider_caches_first_successful_load(tmp_path: Path) -> None:
    dataset_path = tmp_path / "jobs.json"
    write_dataset(dataset_path, [job_payload(make_job(title="Original"))])
    provider = LocalJobsProvider(dataset_path)

    assert provider.get_job("job-1").title == "Original"
    write_dataset(dataset_path, [job_payload(make_job(title="Updated"))])

    assert provider.get_job("job-1").title == "Original"
    assert LocalJobsProvider(dataset_path).get_job("job-1").title == "Updated"


def test_provider_returns_deep_copies_without_cache_pollution(tmp_path: Path) -> None:
    dataset_path = tmp_path / "jobs.json"
    write_dataset(dataset_path, [job_payload()])
    provider = LocalJobsProvider(dataset_path)

    listed_job = provider.list_jobs()[0]
    listed_job.title = "Mutated"
    listed_job.responsibilities.append("Mutated responsibility")
    listed_job.requirements.append(
        JobRequirement(
            requirement_id="mutated-required",
            text="Mutated requirement",
            requirement_type=JobRequirementType.SKILL,
            priority=RequirementPriority.REQUIRED,
        )
    )
    listed_job.preferred_qualifications.append(
        JobRequirement(
            requirement_id="mutated-preferred",
            text="Mutated preference",
            requirement_type=JobRequirementType.SKILL,
            priority=RequirementPriority.PREFERRED,
            is_required=False,
        )
    )
    listed_job.warnings.append(ToolWarning(code="mutated", message="Mutated warning"))
    listed_job.errors.append(
        ToolError(code="mutated", message="Mutated error", recoverable=True)
    )
    fetched_job = provider.get_job("job-1")
    fetched_job.company = "Mutated company"

    pristine = provider.get_job("job-1")
    next_listed = provider.list_jobs()[0]
    assert pristine.title == "Python Backend Engineer"
    assert pristine.company == "Example Labs"
    assert pristine.responsibilities == ["Build APIs"]
    assert pristine.requirements == []
    assert pristine.preferred_qualifications == []
    assert pristine.warnings == []
    assert pristine.errors == []
    assert next_listed == pristine
    assert provider.list_jobs()[0] is not pristine
