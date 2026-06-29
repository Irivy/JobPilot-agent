"""Tests for application-pack schemas."""

from __future__ import annotations

from app.schemas import (
    ApplicationPack,
    EvidenceBackedStatement,
    FactCheckItem,
    FactCheckStatus,
    ResumeAdjustmentSuggestion,
)
from pydantic import ValidationError


def test_application_pack_can_be_created() -> None:
    pack = ApplicationPack(
        application_pack_id="app-pack-1",
        candidate_summary=[
            EvidenceBackedStatement(
                text="Built backend APIs for internal tooling",
                evidence_ids=["ev-1"],
            )
        ],
        role_fit_summary=[
            EvidenceBackedStatement(
                text="Matches Python and API requirements",
                evidence_ids=["ev-2"],
            )
        ],
        resume_adjustment_suggestions=[
            ResumeAdjustmentSuggestion(
                suggestion="Move API delivery bullets higher",
                rationale="Aligns with role priorities",
            )
        ],
        cover_letter_points=[
            EvidenceBackedStatement(
                text="Can speak to schema design experience",
                evidence_ids=["ev-3"],
            )
        ],
        fact_check_items=[
            FactCheckItem(
                statement="Led schema implementation",
                status=FactCheckStatus.VERIFIED,
                evidence_ids=["ev-4"],
            )
        ],
    )

    assert pack.application_pack_id == "app-pack-1"


def test_evidence_backed_statement_requires_evidence_ids() -> None:
    try:
        EvidenceBackedStatement(text="Built backend APIs", evidence_ids=[])
    except ValidationError:
        pass
    else:
        raise AssertionError("Expected evidence-backed statement without evidence to fail.")


def test_fact_check_item_requires_evidence_ids() -> None:
    try:
        FactCheckItem(
            statement="Built backend APIs",
            status=FactCheckStatus.VERIFIED,
            evidence_ids=[],
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("Expected fact-check item without evidence to fail.")
