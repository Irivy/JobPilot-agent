"""Tests for matching schemas."""

from __future__ import annotations

from app.schemas import (
    FitReport,
    FitScoreBand,
    JobRequirement,
    JobRequirementType,
    RequirementMatch,
    RequirementMatchStatus,
    RequirementPriority,
)
from pydantic import ValidationError


def make_requirement() -> JobRequirement:
    return JobRequirement(
        requirement_id="req-1",
        text="Experience with FastAPI",
        requirement_type=JobRequirementType.SKILL,
        priority=RequirementPriority.REQUIRED,
    )


def test_requirement_match_requires_evidence_for_matched_status() -> None:
    for status in (
        RequirementMatchStatus.MATCHED,
        RequirementMatchStatus.PARTIALLY_MATCHED,
    ):
        try:
            RequirementMatch(
                requirement=make_requirement(),
                status=status,
                evidence_ids=[],
                score_contribution=10.0,
            )
        except ValidationError:
            continue
        raise AssertionError(f"Expected {status} RequirementMatch without evidence to fail.")


def test_unmatched_statuses_allow_no_evidence_and_negative_contribution() -> None:
    for status in (
        RequirementMatchStatus.INSUFFICIENT_EVIDENCE,
        RequirementMatchStatus.NOT_MATCHED,
    ):
        match = RequirementMatch(
            requirement=make_requirement(),
            status=status,
            score_contribution=-2.5,
        )

        assert match.evidence_ids == []
        assert match.score_contribution == -2.5


def test_fit_report_uses_dimension_scores_field() -> None:
    report = FitReport(
        fit_report_id="fit-1",
        overall_score=82.5,
        score_band=FitScoreBand.STRONG,
        dimension_scores=[
            RequirementMatch(
                requirement=make_requirement(),
                status=RequirementMatchStatus.PARTIALLY_MATCHED,
                evidence_ids=["ev-1"],
                score_contribution=12.5,
            )
        ],
    )

    assert report.dimension_scores[0].status is RequirementMatchStatus.PARTIALLY_MATCHED


def test_fit_report_rejects_requirement_matches_alias() -> None:
    try:
        FitReport(
            fit_report_id="fit-1",
            overall_score=82.5,
            score_band=FitScoreBand.STRONG,
            requirement_matches=[],
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("Expected incorrect requirement_matches field to be rejected.")


def test_fit_report_rejects_out_of_range_score() -> None:
    for invalid_score in (-1.0, 120.0):
        try:
            FitReport(
                fit_report_id="fit-1",
                overall_score=invalid_score,
                score_band=FitScoreBand.WEAK,
            )
        except ValidationError:
            continue
        raise AssertionError("Expected out-of-range overall_score to be rejected.")
