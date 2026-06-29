"""Tests for common and evidence schemas."""

from __future__ import annotations

from app.schemas import EvidenceConfidence, EvidenceItem, EvidenceSourceType, ToolError, ToolWarning
from pydantic import ValidationError


def test_tool_error_preserves_recoverable_flag_and_json_context() -> None:
    error = ToolError(
        code="resume_parse_failed",
        message="Could not parse resume",
        recoverable=True,
        context={
            "path": "resume.pdf",
            "attempts": 2,
            "retryable": True,
            "tags": ["resume", "parse"],
        },
    )

    assert error.recoverable is True
    assert error.context["attempts"] == 2
    assert error.context["tags"] == ["resume", "parse"]


def test_tool_warning_rejects_blank_message() -> None:
    try:
        ToolWarning(code="warning_code", message="   ")
    except ValidationError:
        pass
    else:
        raise AssertionError("Expected blank warning message to be rejected.")


def test_evidence_item_rejects_blank_required_fields() -> None:
    try:
        EvidenceItem(
            evidence_id=" ",
            source_type=EvidenceSourceType.RESUME,
            source_label="Resume",
            excerpt="Built APIs",
            confidence=EvidenceConfidence.HIGH,
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("Expected blank evidence_id to be rejected.")


def test_evidence_item_accepts_json_metadata() -> None:
    item = EvidenceItem(
        evidence_id="ev-1",
        source_type=EvidenceSourceType.PROJECT,
        source_label="jobpilot-agent",
        excerpt="Implemented schema models",
        locator="app/schemas",
        confidence=EvidenceConfidence.MEDIUM,
        metadata={"lines": 42, "verified": True, "notes": ["schema", "tests"]},
    )

    assert item.metadata["lines"] == 42
    assert item.metadata["verified"] is True
