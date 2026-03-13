# Workspace-AI

Standalone Workspace product.

## Main entrypoint

Use the root launcher:

```bash
cd /Users/briansifrar/Workspace-AI
./workspace.sh start
```

Other commands:

```bash
./workspace.sh install
./workspace.sh stop
./workspace.sh status
./workspace.sh smoke
./workspace.sh secrets
```

Config lives at the repo root:

- `.env.workspace`
- `.env.workspace.secret`

The UI includes a first-run wizard that can write those files for you.
