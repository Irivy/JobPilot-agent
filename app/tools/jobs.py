"""Deterministic local job search and detail tools."""

from __future__ import annotations

import unicodedata

from app.providers.jobs import (
    DuplicateJobIdError,
    JobNotFoundError,
    JobRecordInvalidError,
    JobsDatasetInvalidError,
    JobsDatasetNotFoundError,
    JobsDatasetReadError,
    JobsProvider,
)
from app.schemas.base import JsonValue
from app.schemas.common import ToolError, ToolWarning
from app.schemas.job import JobDetail, JobSourceType, JobSummary
from app.schemas.tool_inputs import ReadJobDetailInput, SearchJobsInput
from app.schemas.tool_outputs import (
    JobSearchResult,
    JobSearchSuccess,
    ReadJobDetailResult,
    ToolFailure,
)

_TITLE_WEIGHT = 8
_REQUIREMENTS_WEIGHT = 5
_PREFERRED_QUALIFICATIONS_WEIGHT = 4
_CONTENT_WEIGHT = 3
_METADATA_WEIGHT = 1


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    without_punctuation = "".join(
        " " if unicodedata.category(character).startswith("P") else character
        for character in normalized
    )
    return " ".join(without_punctuation.split())


def _searchable_fields(job: JobDetail) -> tuple[tuple[str, int], ...]:
    requirements = " ".join(requirement.text for requirement in job.requirements)
    preferred = " ".join(
        requirement.text for requirement in job.preferred_qualifications
    )
    responsibilities = " ".join(job.responsibilities)
    return (
        (_normalize_text(job.title), _TITLE_WEIGHT),
        (_normalize_text(requirements), _REQUIREMENTS_WEIGHT),
        (_normalize_text(preferred), _PREFERRED_QUALIFICATIONS_WEIGHT),
        (_normalize_text(job.summary or ""), _CONTENT_WEIGHT),
        (_normalize_text(responsibilities), _CONTENT_WEIGHT),
        (_normalize_text(job.company), _METADATA_WEIGHT),
        (_normalize_text(job.location or ""), _METADATA_WEIGHT),
        (_normalize_text(job.employment_type or ""), _METADATA_WEIGHT),
        (_normalize_text(job.seniority or ""), _METADATA_WEIGHT),
        (_normalize_text(job.work_mode or ""), _METADATA_WEIGHT),
    )


def _unique_search_terms(
    query_tokens: list[str],
    keyword_phrases: list[str],
) -> list[str]:
    seen: set[str] = set()
    terms: list[str] = []
    for term in [*query_tokens, *keyword_phrases]:
        if term not in seen:
            seen.add(term)
            terms.append(term)
    return terms


def _normalized_search_terms(
    tool_input: SearchJobsInput,
) -> tuple[list[str], list[str]]:
    query_tokens = _normalize_text(tool_input.query or "").split()
    keyword_phrases = [
        normalized
        for keyword in tool_input.keywords
        if (normalized := _normalize_text(keyword))
    ]
    return query_tokens, keyword_phrases


def _matches_exact_filter(value: str | None, accepted_values: list[str]) -> bool:
    if not accepted_values:
        return True
    normalized_value = _normalize_text(value or "")
    if not normalized_value:
        return False
    return any(
        normalized_value == normalized_accepted
        for accepted_value in accepted_values
        if (normalized_accepted := _normalize_text(accepted_value))
    )


def _matches_search(
    job: JobDetail,
    tool_input: SearchJobsInput,
) -> tuple[int, int] | None:
    if not _matches_exact_filter(job.location, tool_input.location_preferences):
        return None
    if tool_input.seniority is not None and not _matches_exact_filter(
        job.seniority,
        [tool_input.seniority],
    ):
        return None
    if tool_input.work_mode is not None and not _matches_exact_filter(
        job.work_mode,
        [tool_input.work_mode],
    ):
        return None

    fields = _searchable_fields(job)
    query_tokens, keyword_phrases = _normalized_search_terms(tool_input)

    if query_tokens and not all(
        any(token in field_value for field_value, _ in fields)
        for token in query_tokens
    ):
        return None
    if keyword_phrases and not any(
        any(keyword in field_value for field_value, _ in fields)
        for keyword in keyword_phrases
    ):
        return None

    terms = _unique_search_terms(query_tokens, keyword_phrases)
    score = sum(
        max(
            (
                weight
                for field_value, weight in fields
                if term in field_value
            ),
            default=0,
        )
        for term in terms
    )
    normalized_title = _normalize_text(job.title)
    title_hits = sum(term in normalized_title for term in terms)
    return score, title_hits


def _to_job_summary(job: JobDetail) -> JobSummary:
    return JobSummary(
        job_id=job.job_id,
        source=job.source,
        title=job.title,
        company=job.company,
        location=job.location,
        employment_type=job.employment_type,
        seniority=job.seniority,
        work_mode=job.work_mode,
        summary=job.summary,
    )


def _tool_failure(
    *,
    code: str,
    message: str,
    recoverable: bool,
    category: str,
    record_index: int | None = None,
    job_id: str | None = None,
) -> ToolFailure:
    context: dict[str, JsonValue] = {"category": category}
    if record_index is not None:
        context["record_index"] = record_index
    if job_id is not None:
        context["job_id"] = job_id
    return ToolFailure(
        errors=[
            ToolError(
                code=code,
                message=message,
                recoverable=recoverable,
                context=context,
            )
        ]
    )


def _missing_dataset_failure() -> ToolFailure:
    return _tool_failure(
        code="jobs_dataset_missing",
        message="Local jobs dataset is unavailable.",
        recoverable=False,
        category="dataset_missing",
    )


def _invalid_dataset_failure(category: str) -> ToolFailure:
    return _tool_failure(
        code="jobs_dataset_invalid",
        message="Local jobs dataset is invalid or unreadable.",
        recoverable=False,
        category=category,
    )


def search_jobs(
    tool_input: SearchJobsInput,
    *,
    provider: JobsProvider,
) -> JobSearchResult:
    """Search local jobs using deterministic field matching and filters."""

    query_tokens, keyword_phrases = _normalized_search_terms(tool_input)
    if not query_tokens and not keyword_phrases:
        return _tool_failure(
            code="search_query_empty",
            message="Search terms are empty after normalization.",
            recoverable=True,
            category="invalid_search_input",
        )

    try:
        jobs = provider.list_jobs()
    except JobsDatasetNotFoundError:
        return _missing_dataset_failure()
    except JobsDatasetReadError:
        return _invalid_dataset_failure("dataset_read_error")
    except DuplicateJobIdError:
        return _invalid_dataset_failure("duplicate_job_id")
    except JobRecordInvalidError as exc:
        return _tool_failure(
            code="jobs_dataset_invalid",
            message="Local jobs dataset contains an invalid record.",
            recoverable=False,
            category="invalid_job_record",
            record_index=exc.record_index,
        )
    except JobsDatasetInvalidError:
        return _invalid_dataset_failure("dataset_validation_error")

    ranked_jobs: list[tuple[int, int, JobDetail]] = []
    for job in jobs:
        match = _matches_search(job, tool_input)
        if match is not None:
            score, title_hits = match
            ranked_jobs.append((score, title_hits, job))

    ranked_jobs.sort(
        key=lambda ranked: (
            -ranked[0],
            -ranked[1],
            ranked[2].job_id.casefold(),
            ranked[2].job_id,
        )
    )
    results = [
        _to_job_summary(job)
        for _, _, job in ranked_jobs[: tool_input.limit]
    ]
    warnings: list[ToolWarning] = []
    if not results:
        warnings.append(
            ToolWarning(
                code="no_job_matches",
                message="No jobs matched the requested search criteria.",
            )
        )

    return JobSearchSuccess(
        results=results,
        result_count=len(results),
        applied_filters=tool_input.model_copy(deep=True),
        search_source=JobSourceType.JOBS_DATASET,
        warnings=warnings,
    )


def read_job_detail(
    tool_input: ReadJobDetailInput,
    *,
    provider: JobsProvider,
) -> ReadJobDetailResult:
    """Read one complete job from the local jobs provider."""

    try:
        return provider.get_job(tool_input.job_id)
    except JobsDatasetNotFoundError:
        return _missing_dataset_failure()
    except JobsDatasetReadError:
        return _invalid_dataset_failure("dataset_read_error")
    except DuplicateJobIdError:
        return _invalid_dataset_failure("duplicate_job_id")
    except JobRecordInvalidError as exc:
        return _tool_failure(
            code="job_record_invalid",
            message="The requested job record is invalid.",
            recoverable=False,
            category="invalid_job_record",
            record_index=exc.record_index,
        )
    except JobsDatasetInvalidError:
        return _invalid_dataset_failure("dataset_validation_error")
    except JobNotFoundError as exc:
        return _tool_failure(
            code="job_not_found",
            message="The requested job was not found.",
            recoverable=True,
            category="job_not_found",
            job_id=exc.job_id,
        )
