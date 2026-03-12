# Vector

Persistent AI Workspace

Vector is the isolated browser and terminal workspace extracted from SynapseLabPro.

It does not start, stop, or own Synapse. If you want Synapse-backed memory, run Synapse separately and point Vector at it over HTTP.

## Install

```bash
cd /Users/briansifrar/SynapseWorkspaceStandalone
./workspace_standalone/scripts/install.sh
```

## Configure

Copy `.env.example` to `.env` if you want stable local defaults.

Key env vars:
- `WORKSPACE_ADAPTER_MODE=null|synapse`
- `WORKSPACE_SYNAPSE_BASE_URL=http://127.0.0.1:8080`
- `WORKSPACE_OPENAI_API_KEY=...`
- `WORKSPACE_MODEL=gpt-5.4`

## Run Without Synapse

```bash
export WORKSPACE_ADAPTER_MODE=null
./workspace_standalone/scripts/start.sh
```

## Run With Synapse As External Dependency

```bash
export WORKSPACE_ADAPTER_MODE=synapse
export WORKSPACE_SYNAPSE_BASE_URL=http://127.0.0.1:8080
export WORKSPACE_OPENAI_API_KEY=...
./workspace_standalone/scripts/start.sh
```

## Stop

```bash
./workspace_standalone/scripts/stop.sh
```

## Status

```bash
./workspace_standalone/scripts/status.sh
```

## Smoke Test

```bash
./workspace_standalone/scripts/smoke_test.sh
```
