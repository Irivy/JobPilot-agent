"""Tests for agent state schemas."""

from __future__ import annotations

from app.schemas import (
    AgentMessage,
    AgentMessageRole,
    AgentState,
    AgentStatus,
    ApplicationPack,
    EvidenceBackedStatement,
    FactCheckItem,
    FactCheckStatus,
    JobDetail,
    JobSourceType,
)
from pydantic import ValidationError


def make_job_detail(source: JobSourceType = JobSourceType.JOBS_DATASET) -> JobDetail:
    return JobDetail(
        job_id="job-1",
        source=source,
        title="Backend Engineer",
        company="Acme",
    )


def make_application_pack() -> ApplicationPack:
    return ApplicationPack(
        application_pack_id="pack-1",
        candidate_summary=[
            EvidenceBackedStatement(text="Built APIs", evidence_ids=["ev-1"])
        ],
        role_fit_summary=[
            EvidenceBackedStatement(text="Matches backend role", evidence_ids=["ev-2"])
        ],
        cover_letter_points=[
            EvidenceBackedStatement(text="Can discuss schema design", evidence_ids=["ev-3"])
        ],
        fact_check_items=[
            FactCheckItem(
                statement="Built APIs",
                status=FactCheckStatus.VERIFIED,
                evidence_ids=["ev-4"],
            )
        ],
    )


def test_agent_status_values_are_all_constructible() -> None:
    for status in AgentStatus:
        if status in {
            AgentStatus.COMPLETED_WITH_REPORT,
            AgentStatus.COMPLETED_WITH_GAP_NOTICE,
        }:
            state = AgentState(status=status, final_report=make_application_pack())
        else:
            state = AgentState(status=status)
        assert state.status is status


def test_agent_state_defaults_are_not_shared_between_instances() -> None:
    state_one = AgentState()
    state_two = AgentState()

    state_one.messages.append(AgentMessage(role=AgentMessageRole.USER, content="hello"))
    state_one.inspected_jobs["job-1"] = make_job_detail()

    assert state_two.messages == []
    assert state_two.inspected_jobs == {}


def test_agent_state_round_trip_dump_and_validate() -> None:
    original = AgentState(
        user_goal="Find a backend Python role",
        status=AgentStatus.RUNNING,
        target_job=make_job_detail(JobSourceType.PROVIDED_JD),
    )

    round_tripped = AgentState.model_validate(original.model_dump())

    assert round_tripped == original


def test_agent_state_accepts_both_target_job_sources() -> None:
    provided_jd_state = AgentState(target_job=make_job_detail(JobSourceType.PROVIDED_JD))
    dataset_state = AgentState(target_job=make_job_detail(JobSourceType.JOBS_DATASET))

    assert provided_jd_state.target_job is not None
    assert dataset_state.target_job is not None


def test_agent_state_rejects_negative_tool_call_count() -> None:
    try:
        AgentState(tool_call_count=-1)
    except ValidationError:
        pass
    else:
        raise AssertionError("Expected negative tool_call_count to be rejected.")


def test_agent_state_rejects_non_positive_max_tool_calls() -> None:
    for invalid_count in (0, -1):
        try:
            AgentState(max_tool_calls=invalid_count)
        except ValidationError:
            continue
        raise AssertionError("Expected non-positive max_tool_calls to be rejected.")


def test_agent_state_default_max_tool_calls_is_twelve() -> None:
    assert AgentState().max_tool_calls == 12


def test_agent_state_inspected_jobs_uses_job_id_keys() -> None:
    state = AgentState(inspected_jobs={"job-1": make_job_detail()})

    assert state.inspected_jobs["job-1"].job_id == "job-1"


def test_agent_state_rejects_mismatched_inspected_job_key() -> None:
    try:
        AgentState(inspected_jobs={"wrong-job-id": make_job_detail()})
    except ValidationError:
        pass
    else:
        raise AssertionError("Expected inspected_jobs key to match JobDetail.job_id.")


def test_agent_state_completed_status_requires_final_report() -> None:
    try:
        AgentState(status=AgentStatus.COMPLETED_WITH_REPORT)
    except ValidationError:
        pass
    else:
        raise AssertionError("Expected completed state without final_report to fail.")
