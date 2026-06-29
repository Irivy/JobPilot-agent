"""Agent state schemas."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import Field, model_validator

from app.schemas.application import ApplicationPack
from app.schemas.base import JobPilotBaseModel, NonEmptyStr
from app.schemas.candidate import CandidateProfile
from app.schemas.common import ToolError
from app.schemas.evidence import EvidenceItem
from app.schemas.job import JobDetail, JobSummary
from app.schemas.matching import FitReport


class AgentMessageRole(StrEnum):
    """Message roles stored in agent state."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class AgentMessage(JobPilotBaseModel):
    """Agent-visible message entry."""

    role: AgentMessageRole
    content: NonEmptyStr
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    tool_name: NonEmptyStr | None = None
    tool_call_id: NonEmptyStr | None = None


class AgentStatus(StrEnum):
    """Agent execution lifecycle statuses."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED_WITH_REPORT = "completed_with_report"
    COMPLETED_WITH_GAP_NOTICE = "completed_with_gap_notice"
    FAILED_MISSING_REQUIRED_INPUT = "failed_missing_required_input"
    FAILED_NO_JOB_CONTEXT = "failed_no_job_context"
    FAILED_TOOL_ERROR = "failed_tool_error"
    FAILED_TOOL_CALL_LIMIT = "failed_tool_call_limit"


class AgentState(JobPilotBaseModel):
    """In-memory working state for a single JobPilot agent run."""

    messages: list[AgentMessage] = Field(default_factory=list)
    user_goal: NonEmptyStr | None = None
    resume_text: NonEmptyStr | None = None
    resume_path: NonEmptyStr | None = None
    provided_jd: NonEmptyStr | None = None
    project_path: NonEmptyStr | None = None
    candidate_profile: CandidateProfile | None = None
    job_candidates: list[JobSummary] = Field(default_factory=list)
    inspected_jobs: dict[NonEmptyStr, JobDetail] = Field(default_factory=dict)
    target_job: JobDetail | None = None
    evidence_ledger: list[EvidenceItem] = Field(default_factory=list)
    fit_reports: list[FitReport] = Field(default_factory=list)
    final_report: ApplicationPack | None = None
    errors: list[ToolError] = Field(default_factory=list)
    tool_call_count: int = Field(default=0, ge=0)
    max_tool_calls: int = Field(default=12, gt=0)
    status: AgentStatus = AgentStatus.PENDING

    @model_validator(mode="after")
    def validate_terminal_report(self) -> AgentState:
        """Completed states should include a final report."""

        if self.status in {
            AgentStatus.COMPLETED_WITH_REPORT,
            AgentStatus.COMPLETED_WITH_GAP_NOTICE,
        } and self.final_report is None:
            msg = "final_report is required for completed agent states"
            raise ValueError(msg)

        for job_id, job_detail in self.inspected_jobs.items():
            if job_id != job_detail.job_id:
                msg = "inspected_jobs keys must match JobDetail.job_id"
                raise ValueError(msg)
        return self
