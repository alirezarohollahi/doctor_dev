
# Phase 5 — security/auth tests and structure cleanup

This phase intentionally does not add product features. It validates and cleans the existing node/panel architecture.

## What changed

### Node auth/token testing

The project now has a real HTTP integration test for the node runtime API:

```bash
python3 -W ignore::DeprecationWarning -m unittest tests.test_node_http_auth
```

The test starts a real local node process through `main.py`, writes an isolated routing config, and verifies:

- `/health` is open and reports the actual bound API port.
- `/runtime` accepts a valid panel API key.
- `/runtime` rejects missing auth with `MISSING_NODE_EXPORT_AUTH`.
- `/runtime` rejects a wrong API key with `INVALID_NODE_API_KEY`.
- `/runtime` accepts a valid peer token.
- `/runtime` rejects a peer token with wrong target node/core.
- `/runtime` rejects an expired peer token.

### Panel node-control cleanup

Low-level panel-to-node HTTP code moved from:

```text
doctor_dev_panel/app.py
```

to:

```text
doctor_dev_panel/services/node_control.py
```

The panel API/UI behavior is unchanged. The goal is only to keep `app.py` thinner and make node-control behavior separately testable.

## Quality gate

Run:

```bash
bash scripts/quality_check.sh
```

This now covers:

1. Compile check.
2. Removed data-dump feature scan.
3. Runtime/API contract tests.
4. Apply rollback test.
5. HTTP auth/token integration tests.
6. Full test suite.

## Current architectural status

Done:

- Single node API port.
- Runtime self-reporting consistency.
- Runtime cache and drift API.
- Safer apply rollback.
- Real HTTP auth/token tests.
- Node-control service extraction.

Still remaining:

- Split the large panel `app.py` into feature route modules.
- Add concurrency/performance tuning for runtime sync.
- Add more end-to-end tests for panel apply -> node runtime sync -> drift result.



