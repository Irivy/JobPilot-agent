# AGENTS.md

This file defines the repository rules Codex must follow when working in
JobPilot.

## Before Starting

- Read `README.md`, `docs/PRD.md`, `docs/AGENT_SPEC.md`,
  `docs/TOOL_CONTRACTS.md`, `docs/ARCHITECTURE.md`, and `docs/DECISIONS.md`.
- Check Git status before making changes.

## Directory Responsibilities

- `README.md`: project overview and developer entrypoint.
- `docs/`: requirements, architecture, agent spec, tool contracts, and ADRs.
- Future code should follow the structure defined in `docs/ARCHITECTURE.md`.
- `app/agent`: LangGraph orchestration, state, prompts, and strategy.
- `app/tools`: the six agent tools.
- `app/schemas`: Pydantic data models.
- `app/providers`: LLM and future external service adapters.
- `app/api`: FastAPI routes.
- `app/services`: deterministic internal services that are not agent tools.

## Coding And Design Rules

- Python code must use type annotations.
- Network calls must be encapsulated in a `Provider` or `Adapter`.
- Never hardcode API keys, tokens, passwords, or secrets.
- Do not swallow exceptions; handle them explicitly or re-raise with context.
- Do not add production dependencies without an explicit user request.
- All user experience, resume, and skill claims must link to `evidence_id`.
- Any operation with external side effects requires explicit user confirmation.

## Testing And Quality

- Unit tests must not access the real network.
- Each task should modify only files relevant to the current requirement.
- Run checks appropriate to the current stage before finishing work.
- Available install command:
  `python -m pip install -e ".[dev]"`
- Available checks:
  `python -m ruff check app tests`
- Available checks:
  `python -m mypy app`
- Available checks:
  `python -m pytest`
- Available checks:
  `python -m pytest --cov=app --cov-report=term-missing`
- Available run command:
  `python -m uvicorn app.main:app --reload`

## Final Response Requirements

- Report modified files.
- Report checks run and their results.
- Report known limitations, gaps, and risks.
