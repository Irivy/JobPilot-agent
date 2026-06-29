"""Common schema objects shared across JobPilot domains."""

from __future__ import annotations

from pydantic import Field

from app.schemas.base import JobPilotBaseModel, JsonValue, NonEmptyStr


class ToolWarning(JobPilotBaseModel):
    """Recoverable warning emitted by a tool or internal step."""

    code: NonEmptyStr
    message: NonEmptyStr
    context: dict[str, JsonValue] = Field(default_factory=dict)


class ToolError(JobPilotBaseModel):
    """Structured error emitted by a tool or internal step."""

    code: NonEmptyStr
    message: NonEmptyStr
    recoverable: bool
    context: dict[str, JsonValue] = Field(default_factory=dict)
