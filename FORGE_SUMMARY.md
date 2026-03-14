# Forge-AI Summary

This note is a repo-grounded summary of Forge-AI as it exists in the current codebase. It is intended to replace broader speculative descriptions that mixed in generic agent-platform ideas not implemented here.

## What Forge-AI Is

Forge-AI is a small Python-based workspace app for running persistent AI-assisted developer workflows. It provides:

- A FastAPI backend for sessions, debates, executions, imports, settings, and status endpoints.
- A lightweight single-page UI served by the app.
- SQLite-backed persistence for workspace state.
- Provider abstraction for OpenAI and xAI models.
- A terminal-oriented launcher flow through `./workspace.sh`.

It is not currently a Rust daemon, microservice platform, vector database stack, or knowledge-graph system.

## Current Architecture

### App entry

- `workspace_ai/app/main.py` builds the FastAPI app.
- `workspace_ai/workspace_api/router.py` exposes the API surface under `/workspace`.
- `workspace.sh` is the top-level launcher for install, start, stop, status, smoke, and secrets flows.

### Runtime services

- `workspace_ai/workspace_runtime/session_manager.py` coordinates the main workspace operations.
- `workspace_ai/workspace_runtime/debate_service.py` runs provider-backed debates and stores the result.
- `workspace_ai/workspace_runtime/executor_service.py` creates approval-gated read-only executions from plans.
- `workspace_ai/workspace_runtime/chat_service.py` handles model-backed responses for chat/debate paths.
- `workspace_ai/workspace_runtime/settings_service.py` manages selected provider/model settings and API key access.

### Persistence

- `workspace_ai/workspace_memory/session_store.py` stores sessions, debates, rounds, executions, messages, checkpoints, and imports in SQLite.
- `workspace_ai/workspace_memory/context_service.py` builds context from recent messages, checkpoints, and adapter previews.

### Providers and adapters

- `workspace_ai/providers/openai_provider.py` uses the OpenAI Responses API.
- `workspace_ai/providers/xai_provider.py` uses the xAI chat completions API.
- Providers support mock behavior when API keys are absent.
- Adapter mode can be `null` for local development or `external` for remote integration.

### UI

- `workspace_ai/ui/index.html` is the shipped frontend.
- The backend serves `/`, `/ui`, `/health`, and `/workspace/*` endpoints.

## What It Does Today

- Starts locally with `./workspace.sh start` on port `8092` by default.
- Persists workspace state in `workspace_ai/storage/workspace.db`.
- Supports debates between providers with a simple round-robin loop.
- Finalizes debates either on convergence via `AGREED`, on max rounds, or on total provider failure.
- Supports approval-gated executions, but current execution mode is `read_only_v1`.
- Supports ChatGPT import flows, including file-based upload endpoints.
- Exposes status, settings, adapter status, events, session, debate, execution, and import APIs.

## Important Limits

- Execution does not currently mutate the workspace or run shell commands. Approved executions are recorded as reviewed read-only steps.
- Debate convergence is heuristic-based and currently relies on simple prompt/response patterns.
- There is no implemented vector memory, graph memory, Rust runtime, Kafka pipeline, or Electron app in this repo.
- File support exists for import flows, but not as a full artifact-management layer for arbitrary execution context.

## Current Validation State

At the time of this note:

- The repo test suite passes locally with `26 passed`.
- Forge boots successfully on `http://127.0.0.1:8092`.
- `./workspace.sh smoke` passes against the running server.
- The startup script includes an extra post-launch stability check so it does not report readiness too early.

## Practical Next Steps

If Forge is the focus, the highest-value next steps are:

- Make execution modes real beyond read-only recording.
- Improve debate output structure beyond freeform text plus `AGREED`.
- Add stronger startup and integration regression coverage.
- Expand artifact/context ingestion in a way that matches the current Python app, instead of designing a larger platform prematurely.
