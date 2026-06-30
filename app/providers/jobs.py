"""Local jobs dataset provider and its internal error boundary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from app.schemas.job import JobDetail, JobSourceType


class JobsProviderError(Exception):
    """Base exception for jobs provider failures."""


class JobsDatasetNotFoundError(JobsProviderError):
    """Raised when the configured jobs dataset does not exist."""

    def __init__(self, dataset_path: Path) -> None:
        self.dataset_path = dataset_path
        super().__init__("jobs dataset was not found")


class JobsDatasetReadError(JobsProviderError):
    """Raised when the configured jobs dataset cannot be read."""

    def __init__(self, dataset_path: Path) -> None:
        self.dataset_path = dataset_path
        super().__init__("jobs dataset could not be read")


class JobsDatasetInvalidError(JobsProviderError):
    """Raised when the jobs dataset has invalid JSON or top-level structure."""

    def __init__(self, dataset_path: Path, reason: str) -> None:
        self.dataset_path = dataset_path
        self.reason = reason
        super().__init__(f"jobs dataset is invalid: {reason}")


class JobRecordInvalidError(JobsDatasetInvalidError):
    """Raised when one job record cannot be validated."""

    def __init__(self, dataset_path: Path, record_index: int, reason: str) -> None:
        self.record_index = record_index
        super().__init__(dataset_path, reason)


class DuplicateJobIdError(JobsDatasetInvalidError):
    """Raised when multiple records use the same job identifier."""

    def __init__(self, dataset_path: Path, job_id: str) -> None:
        self.job_id = job_id
        super().__init__(dataset_path, "duplicate job_id")


class JobNotFoundError(JobsProviderError):
    """Raised when a requested job identifier is absent."""

    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        super().__init__("job_id was not found")


class JobsProvider(Protocol):
    """Data access boundary consumed by deterministic job tools."""

    def list_jobs(self) -> tuple[JobDetail, ...]:
        """Return all available jobs in deterministic provider order."""

    def get_job(self, job_id: str) -> JobDetail:
        """Return one job or raise JobNotFoundError."""


class LocalJobsProvider:
    """Lazy, cached provider for a local UTF-8 JSON jobs dataset."""

    def __init__(self, dataset_path: Path) -> None:
        self._dataset_path = dataset_path
        self._jobs: tuple[JobDetail, ...] | None = None
        self._jobs_by_id: dict[str, JobDetail] | None = None

    def list_jobs(self) -> tuple[JobDetail, ...]:
        jobs, _ = self._ensure_loaded()
        return tuple(job.model_copy(deep=True) for job in jobs)

    def get_job(self, job_id: str) -> JobDetail:
        _, jobs_by_id = self._ensure_loaded()
        try:
            job = jobs_by_id[job_id]
        except KeyError as exc:
            raise JobNotFoundError(job_id) from exc
        return job.model_copy(deep=True)

    def _ensure_loaded(self) -> tuple[tuple[JobDetail, ...], dict[str, JobDetail]]:
        if self._jobs is None or self._jobs_by_id is None:
            jobs = self._load_jobs()
            self._jobs = jobs
            self._jobs_by_id = {job.job_id: job for job in jobs}
        return self._jobs, self._jobs_by_id

    def _load_jobs(self) -> tuple[JobDetail, ...]:
        try:
            content = self._dataset_path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise JobsDatasetNotFoundError(self._dataset_path) from exc
        except OSError as exc:
            raise JobsDatasetReadError(self._dataset_path) from exc

        try:
            raw_dataset: object = json.loads(content)
        except json.JSONDecodeError as exc:
            raise JobsDatasetInvalidError(
                self._dataset_path,
                "invalid JSON syntax",
            ) from exc

        if not isinstance(raw_dataset, list):
            raise JobsDatasetInvalidError(
                self._dataset_path,
                "top-level value must be a list",
            )

        jobs: list[JobDetail] = []
        job_ids: set[str] = set()
        for record_index, raw_record in enumerate(raw_dataset):
            try:
                job = JobDetail.model_validate(raw_record)
            except ValidationError as exc:
                raise JobRecordInvalidError(
                    self._dataset_path,
                    record_index,
                    "record failed schema validation",
                ) from exc

            if job.source is not JobSourceType.JOBS_DATASET:
                raise JobRecordInvalidError(
                    self._dataset_path,
                    record_index,
                    "source must be jobs_dataset",
                )
            if job.warnings or job.errors:
                raise JobRecordInvalidError(
                    self._dataset_path,
                    record_index,
                    "dataset records must not contain runtime warnings or errors",
                )
            if job.job_id in job_ids:
                raise DuplicateJobIdError(self._dataset_path, job.job_id)

            job_ids.add(job.job_id)
            jobs.append(job)

        return tuple(jobs)
