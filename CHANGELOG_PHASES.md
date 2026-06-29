# Doctor Dev full project zip — phase status

## Completed

### Phase 1 Hotfix
- Fixed Linux dependency set for the current Pydantic v2 code.
- Added compatibility shims for refactored store imports.
- Added node `/runtime` endpoint and kept `/config/export` as alias.
- Improved node export auth errors and peer token target checks.
- Removed fixed data-plane port from node health/status model.
- Enforced one enabled core per node in panel and node validation.
- Panel runtime sync now stores reachable/auth/runtime status.
- Balancer endpoint model is inbound-based, not route-based.

### Phase 2 Single-port + Runtime Drift API
- Removed legacy `SERVICE_PROTOCOL` validation from `main.py`.
- Updated installer script to ignore legacy service/data-plane port flags.
- Installer-generated node env now writes only `API_PORT` for node control.
- Added per-node runtime API on panel.
- Added per-node drift API on panel.
- Added docs for Linux `main.py` execution and runtime contract.
- Added helper scripts for running panel/node and testing node runtime.

### Phase 3 Runtime Consistency + Node UI Runtime Table
- Fixed node self-reporting inconsistency when CLI `--host`/`--port` overrides env values.
- `/health` and `/runtime` now report the actual bound API host/port.
- Added process-level `DOCTOR_DEV_NODE_BOUND_HOST` and `DOCTOR_DEV_NODE_BOUND_API_PORT` consistency markers.
- Panel runtime cache now stores the node API identity returned by runtime export.
- Nodes table now shows runtime API, runtime auth/reachability state, listener count, active connections, and last sync age.
- Added a per-node Runtime Sync action in the Nodes table.
- Core apply and node config apply now refresh runtime cache immediately after successful apply.
- Balancer endpoint labels were simplified to show inbound first, not route-like labels.

## Pending

### Phase 4 Atomic Apply/Rollback
- Preserve previous node runtime when a new config fails.
- Add apply transaction result and immediate post-apply runtime sync result details.

### Phase 5 Token Test Suite
- Add automated peer-token tests for expired, wrong-target, and bad-signature cases.

### Phase 6 Full API Module Split
- Move remaining large route groups out of `doctor_dev_panel/app.py`.
