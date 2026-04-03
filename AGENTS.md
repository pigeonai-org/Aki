# Repository Guidelines

## Project Structure & Module Organization
- Core package: `aki/`
- Agent orchestration: `aki/agent/`
- Execution tools (audio/subtitle/vision/io): `aki/tools/`
- Model providers and typed interfaces: `aki/models/`
- Playbooks: `aki/playbook/`
- Runtime entrypoints: `aki/cli/`, `aki/mcp/`
- Tests: `tests/` (pytest + async tests)
- Docs and examples: `docs/`
- Runtime artifacts: `outputs/` (generated files; do not treat as source)
- Personality system: `aki/tools/personality/`

## Build, Test, and Development Commands
- `uv sync` — install project dependencies.
- `uv sync --extra dev` — install dev tools (ruff, mypy, pytest extras).
- `uv run aki --help` — verify CLI entrypoint.
- `uv run pytest -q` — run full test suite.
- `uv run pytest tests/test_audio_vad_tool.py -q` — run one focused test file.
- `uv run ruff check aki tests` — lint checks.
- `uv run mypy aki` — static typing checks.

## Coding Style & Naming Conventions
- Python 3.11+ with 4-space indentation and explicit type hints.
- Follow Ruff config in `pyproject.toml` (line length 100, selected lint rules).
- Naming: `snake_case` for functions/variables/modules, `PascalCase` for classes, `UPPER_CASE` for constants.
- Keep tools deterministic and side-effect scoped; keep agent behavior in agent classes.
- Prefer small, testable helpers for parsing/normalization logic.

## Testing Guidelines
- Framework: `pytest` + `pytest-asyncio` (`asyncio_mode=auto`).
- Test file pattern: `tests/test_*.py`; test names: `test_<behavior>()`.
- Mock network/SDK calls (DashScope, pyannote, external HTTP). Avoid live API dependency in unit tests.
- For bug fixes, add/adjust regression tests near the changed module.
- Useful pre-PR sweep: run full suite multiple times and in targeted subsets.

## Commit & Pull Request Guidelines
- Use conventional-style commits consistent with history, e.g.:
  - `feat(vad): migrate to pyannote VAD with pydub chunk export`
  - `fix(qwen): improve dashscope auth fallback`
  - `test: expand coverage for chunk metadata`
- Keep commits scoped to one logical change.
- PRs should include:
  - What changed and why
  - Risk/rollback notes
  - Exact validation commands and results
  - Related issue/task IDs when available

## Security & Configuration Tips
- Keep secrets in `.env`; do not commit API keys.
- Common env vars: `AKI_DASHSCOPE_API_KEY`, `AKI_PYANNOTE_API_KEY`, provider base URLs.
- Avoid committing generated artifacts from `outputs/` unless explicitly required for debugging.
