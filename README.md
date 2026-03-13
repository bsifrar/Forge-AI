# Synapse Workspace Standalone

This is the isolated browser and terminal workspace extracted from SynapseLabPro.

It does not start, stop, or own Synapse. If you want Synapse-backed memory, run Synapse separately and point this app at it over HTTP.

## Install

```bash
cd /Users/briansifrar/SynapseWorkspaceStandalone
./workspace_standalone/scripts/install.sh
```

## Run Without Synapse

```bash
export WORKSPACE_ADAPTER_MODE=null
./workspace_standalone/scripts/start.sh

Use `.env.workspace` for non-secret config and `.env.workspace.secret` for local secrets.
```

## Run With Synapse As External Dependency

```bash
export WORKSPACE_ADAPTER_MODE=synapse
export WORKSPACE_SYNAPSE_BASE_URL=http://127.0.0.1:8080
export WORKSPACE_API_KEY=...
./workspace_standalone/scripts/start.sh

Use `.env.workspace` for non-secret config and `.env.workspace.secret` for local secrets.
```

## Stop

```bash
./workspace_standalone/scripts/stop.sh
```
