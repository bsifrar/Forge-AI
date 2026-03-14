# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running tests

All tests use the venv inside `workspace_ai/.venv`. The system `pytest` does not have `workspace_ai` on its path.

```bash
# Full unit + integration suite (normal workflow)
workspace_ai/.venv/bin/python -m pytest tests/unit tests/integration -v

# Single test file
workspace_ai/.venv/bin/python -m pytest tests/unit/test_debate_service.py -v

# Single test by name
workspace_ai/.venv/bin/python -m pytest tests/unit/test_debate_service.py::test_debate_service_marks_failed_when_all_participants_error -v

# Smoke tests (require a running server on port 8092)
workspace_ai/.venv/bin/python -m pytest tests/smoke -v
```

## Starting and stopping the server

```bash
./workspace.sh start        # start on http://127.0.0.1:8092
./workspace.sh stop
./workspace.sh status
./workspace.sh smoke        # smoke-test against a running server
./workspace.sh install      # set up venv and dependencies
```

Config lives at the project root: `.env.workspace` (non-secret) and `.env.workspace.secret` (API keys).

## Architecture

### Provider abstraction

`workspace_ai/providers/` is the core extension point:

- `base.py` — `LLMProvider` ABC with `generate`, `generate_stream`, `capabilities`
- `openai_provider.py` — OpenAI Responses API (`/v1/responses`)
- `xai_provider.py` — xAI chat completions (`/v1/chat/completions`)
- `anthropic_provider.py` — Anthropic Messages API (`/v1/messages`)
- `__init__.py` — `get_provider(name)` factory; add new providers here

All providers mock (return `mode: "mock"`) when their API key is absent. The mock path is the default for tests.

### Settings

`workspace_ai/app/settings.py` — `WorkspaceSettings` dataclass loaded from env vars. Key vars:

| Env var | Purpose |
|---|---|
| `WORKSPACE_PROVIDER` | default provider (`openai`, `xai`, `anthropic`) |
| `WORKSPACE_MODEL` | default model for OpenAI |
| `WORKSPACE_API_KEY` / `OPENAI_API_KEY` | OpenAI key |
| `WORKSPACE_XAI_API_KEY` / `XAI_API_KEY` | xAI key |
| `WORKSPACE_ANTHROPIC_API_KEY` / `ANTHROPIC_API_KEY` | Anthropic key |
| `ANTHROPIC_MODEL` | Anthropic model (default: `claude-sonnet-4-20250514`) |

### Runtime services

`workspace_ai/workspace_runtime/`:

- `settings_service.py` — wraps `WorkspaceSettings` + per-provider key lookup from SQLite; exposes `available_providers`
- `chat_service.py` — routes `respond` / `respond_stream` to the right provider
- `debate_service.py` — round-robin debate loop between providers; validates provider names against the allowed set (`{"openai", "xai", "anthropic"}`); convergence via `agreed: true` in structured JSON or `max_rounds` cutoff; judge summary called after convergence
- `executor_service.py` — two non-destructive execution modes: `read_only_v1` (records steps, no mutations) and `change_plan_v1` (produces command suggestions + patch outline, no mutations)
- `artifact_service.py` — normalizes file inputs into artifact records with preview text; injected into debate prompts and executor proposals

### Persistence

`workspace_ai/workspace_memory/session_store.py` — SQLite via stdlib `sqlite3`. All state (sessions, debates, rounds, executions, messages, checkpoints, imports, settings) stored here.

### Adding a new provider

1. Create `workspace_ai/providers/<name>_provider.py` implementing `LLMProvider` (follow `xai_provider.py` for chat-completions-style APIs)
2. Add `api_key` and `default_model` fields to `WorkspaceSettings` in `app/settings.py`
3. Wire env vars in `get_settings()`
4. Add the factory case in `providers/__init__.py`
5. Add the provider name to `settings_service.py`: `api_enabled`, `api_key()`, `available_providers`
6. Add the provider name to `debate_service.py` `_normalize_provider` allowed set
7. Add provider env vars to the `isolated_workspace_env` fixture in `tests/conftest.py`
8. Add a test file `tests/unit/test_<name>_provider.py`
