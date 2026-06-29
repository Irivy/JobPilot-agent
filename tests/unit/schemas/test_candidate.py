"""Tests for candidate schemas."""

from __future__ import annotations

from app.schemas import (
    CandidateExperience,
    CandidateFact,
    CandidateProfile,
    CandidateSkill,
    CandidateSkillLevel,
    CertificationItem,
    EducationItem,
)
from pydantic import ValidationError


def test_candidate_models_can_be_created() -> None:
    profile = CandidateProfile(
        candidate_profile_id="candidate-1",
        headline="Backend Engineer",
        target_role_hint="Python Engineer",
        summary_facts=[CandidateFact(text="Built internal APIs", evidence_ids=["ev-1"])],
        skills=[
            CandidateSkill(
                name="Python",
                level=CandidateSkillLevel.ADVANCED,
                evidence_ids=["ev-1"],
            )
        ],
        experiences=[
            CandidateExperience(
                title="Software Engineer",
                organization="Acme",
                start_date="2024.03",
                end_date="2024.12",
                summary="Worked on backend systems",
                evidence_ids=["ev-2"],
            )
        ],
        education=[
            EducationItem(
                institution="Example University",
                degree="BSc",
                field_of_study="Computer Science",
                evidence_ids=["ev-3"],
            )
        ],
        certifications=[
            CertificationItem(
                name="AWS Certified Developer",
                issuer="AWS",
                evidence_ids=["ev-4"],
            )
        ],
    )

    assert profile.skills[0].name == "Python"


def test_candidate_fact_requires_evidence_ids() -> None:
    try:
        CandidateFact(text="Built internal APIs", evidence_ids=[])
    except ValidationError:
        pass
    else:
        raise AssertionError("Expected CandidateFact without evidence_ids to be rejected.")


def test_candidate_skill_requires_evidence_ids() -> None:
    try:
        CandidateSkill(name="Python", evidence_ids=[])
    except ValidationError:
        pass
    else:
        raise AssertionError("Expected CandidateSkill without evidence_ids to be rejected.")


def test_candidate_experience_requires_evidence_ids() -> None:
    try:
        CandidateExperience(
            title="Engineer",
            summary="Worked on systems",
            evidence_ids=[],
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("Expected CandidateExperience without evidence_ids to be rejected.")


def test_education_and_certification_require_evidence_ids() -> None:
    invalid_entry_factories = (
        lambda: EducationItem(
            institution="Example University",
            degree="BSc",
            evidence_ids=[],
        ),
        lambda: CertificationItem(name="AWS Certified Developer", evidence_ids=[]),
    )

    for make_invalid_entry in invalid_entry_factories:
        try:
            make_invalid_entry()
        except ValidationError:
            continue
        raise AssertionError("Expected education and certification facts to require evidence.")


def test_candidate_experience_rejects_end_date_for_current_role() -> None:
    try:
        CandidateExperience(
            title="Engineer",
            start_date="2024",
            end_date="至今",
            is_current=True,
            summary="Current role",
            evidence_ids=["ev-1"],
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("Expected end_date with is_current=True to be rejected.")


def test_candidate_experience_accepts_resume_style_time_strings() -> None:
    experience = CandidateExperience(
        title="Engineer",
        start_date="2024",
        end_date="2024.03",
        summary="Worked on systems",
        highlights=["Migrated services"],
        evidence_ids=["ev-1"],
    )
    current_experience = CandidateExperience(
        title="Senior Engineer",
        start_date="2024.03",
        is_current=True,
        summary="Leading backend work",
        evidence_ids=["ev-2"],
    )

    assert experience.start_date == "2024"
    assert experience.end_date == "2024.03"
    assert current_experience.is_current is True


def test_candidate_profile_rejects_unknown_fields() -> None:
    try:
        CandidateProfile(candidate_profile_id="candidate-1", unknown_field="value")
    except ValidationError:
        pass
    else:
        raise AssertionError("Expected unknown fields to be rejected.")
