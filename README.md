# Forge-AI

Standalone Forge workspace product.

## Main entrypoint

Use the root launcher:

```bash
cd /Users/briansifrar/Forge-AI
./workspace.sh start
```

Explicit integration-mode commands:

```bash
./workspace.sh start-external
./workspace.sh status-external
./workspace.sh smoke-external
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
