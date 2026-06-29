# Consistency audit notes

This project separates three values that used to be mixed together:

1. Desired node API port: what the panel stores for reaching the node.
2. Bound node API port: what the running node process is actually listening on.
3. Inbound listener ports: runtime data-plane ports opened from core inbound config.

Rules:

- A node has only one management API port.
- `SERVICE_PORT` and `SERVICE_PROTOCOL` are legacy and must not be used for runtime decisions.
- `/health`, `/status`, and `/runtime` must report the actual bound API identity.
- Runtime listener ports only come from `runtime.summary().listeners`.
- Panel UI must show desired API port and actual runtime API separately so mismatches are visible.
- After every successful apply, the panel must immediately refresh runtime cache.
