# Workspace

Persistent AI Workspace.

Workspace is the isolated browser and terminal application.

It does not start, stop, or own any external runtime. If you want external-service-backed memory, run the external memory service separately and point Workspace at it over HTTP.

## Install

```bash
cd /Users/briansifrar/Workspace-AI
./workspace_ai/scripts/install.sh
```

Use `.env.workspace` for non-secret config and `.env.workspace.secret` for local secrets.

## Env Files

- `.env.workspace`
- `.env.workspace.secret`

## Run Without External Memory Service

```bash
cd /Users/briansifrar/Workspace-AI
./workspace_ai/scripts/start.sh
```

## Run With External Memory Service

Set these in `.env.workspace`:

- `WORKSPACE_ADAPTER_MODE=external`
- `WORKSPACE_EXTERNAL_BASE_URL=http://127.0.0.1:8080`

Then run:

```bash
cd /Users/briansifrar/Workspace-AI
./workspace_ai/scripts/start.sh
```

## Stop

```bash
./workspace_ai/scripts/stop.sh
```

## Status

```bash
./workspace_ai/scripts/status.sh
```

## Smoke Test

```bash
./workspace_ai/scripts/smoke_test.sh
```

## Secret Scan

```bash
./workspace_ai/scripts/check_secrets.sh
```
