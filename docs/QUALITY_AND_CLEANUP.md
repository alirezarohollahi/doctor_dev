# Quality and cleanup checks

This phase focuses on reliability and maintainability without adding product features.

## What is checked

- Python syntax for panel, node, entrypoint, and tests.
- Removed data-dump feature references are absent from code, docs, scripts, env examples, and UI text.
- Node runtime self-reporting uses the actual bound API port from CLI/process state.
- Peer token verification rejects wrong signatures and target mismatches.
- Failed node config apply restores the previous working runtime config when possible.
- Node env examples expose only `API_PORT`; inbound listener ports are runtime config, not fixed node service ports.

## Run all checks

```bash
bash scripts/quality_check.sh
```

## Scope rule

For now the project should only receive fixes and cleanup for the current panel/node/runtime architecture. Do not add new product features unless explicitly requested.
