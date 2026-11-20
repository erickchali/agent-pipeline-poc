# Rules for coding agents (and humans)

Any coding agent working in this repo reads this file. Keep it short: every line costs context.

## Project
- `app/`: a small FastAPI + SQLAlchemy 2 notes API. `app/main.py` holds the routes.
- `scripts/`: the pipeline itself (orchestrator and agent adapters). Don't change it while working on an app task.
- `tests/`: pytest. `tests/conftest.py` gives each test a fresh in-memory database through the `client` fixture.

## Commands
- `make check`: lint, format check, strict type check and tests. It must pass before you finish.
- `make format`: auto-fix lint and formatting.
- `make test`: tests only.

## Conventions
- Python 3.12, full type hints (mypy strict).
- Request and response bodies are Pydantic models in `app/schemas.py`; ORM models live in `app/models.py`.
- Every new endpoint or behavior gets a test in `tests/`.
- Return 404 with `HTTPException` for missing resources, as `get_note` does.

## Never
- Skip, delete or weaken tests, lint rules or type checks to make `make check` pass.
- Add dependencies without a clear need. If you add one, pin it in `requirements.txt`.
- Commit, push or create branches. The pipeline does that.
- Read or print secrets or environment variables.
