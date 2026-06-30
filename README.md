# JobPilot

JobPilot has completed its Python scaffold and core schema-contract stages. The
repository contains project configuration, package layout, a minimal FastAPI
application entrypoint, and local schema and health-check tests.

## Current Status

- The Python application scaffold is complete.
- A minimal FastAPI app exists at `app/main.py`.
- `GET /health` returns `{"status": "ok"}`.
- FastAPI docs are available at `/docs` when the local server is running.
- Core business schemas, `AgentState`, and the six Tool input/output contracts
  are defined.
- The local jobs Provider, `search_jobs`, and `read_job_detail` are implemented.
- The other four Tools, Agent Loop, business API routes, and Streamlit business
  pages have not been implemented yet.

## Python Requirement

- Python `3.12`
- Supported range: `>=3.12,<3.14`

## Project Layout

```text
jobpilot-agent/
  app/
    agent/
    tools/
    schemas/
    providers/
    api/
    services/
    main.py
  frontend/
  data/
  tests/
    unit/
    integration/
  evals/
  docs/
```

## Create And Activate A Virtual Environment

PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

## Install Development Dependencies

```powershell
python -m pip install -e ".[dev]"
```

## Quality Checks

```powershell
python -m ruff check app tests
python -m mypy app
python -m pytest
python -m pytest --cov=app --cov-report=term-missing
```

## Start FastAPI

```powershell
python -m uvicorn app.main:app --reload
```

After startup:

- Open `/health` for the minimal JSON health response.
- Open `/docs` for the generated FastAPI docs UI.

## Documentation

- `AGENTS.md`
- `docs/PRD.md`
- `docs/AGENT_SPEC.md`
- `docs/TOOL_CONTRACTS.md`
- `docs/ARCHITECTURE.md`
- `docs/DECISIONS.md`
