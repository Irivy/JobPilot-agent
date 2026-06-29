# JobPilot

JobPilot is currently in the Python scaffold stage. This repository now contains
project configuration, package layout, a minimal FastAPI application entrypoint,
and a local in-process health check test.

## Current Status

- The repository is at the engineering scaffold stage.
- A minimal FastAPI app exists at `app/main.py`.
- `GET /health` returns `{"status": "ok"}`.
- FastAPI docs are available at `/docs` when the local server is running.
- No JobPilot agent logic, tool implementations, business schemas, or Streamlit
  business pages have been implemented yet.

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
