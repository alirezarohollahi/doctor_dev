# Doctor Dev runtime refactor plan

## Completed in this full-project zip

### Phase 1 — hotfix/runtime contract
- Linux requirements updated for the current Pydantic v2 code.
- Store import shims added for refactor compatibility.
- Node `/runtime` endpoint added.
- `/config/export` kept as a backward-compatible alias.
- Node auth errors now return clear 401 codes.
- Panel runtime sync tries `/runtime` first and stores reachable/auth/runtime status.
- One enabled core per node is enforced in panel and node validation.
- Balancer Node Inbound endpoint model is semantic: node + core + inbound.
- Node examples now use one fixed control API port only.

### Phase 2 — single-port cleanup + drift API
- `main.py` no longer validates legacy `SERVICE_PROTOCOL`.
- Installer script ignores legacy `--service-port` and `--service-protocol`.
- Node installer env generation writes only `API_PORT`.
- Panel now exposes per-node runtime APIs:
  - `POST /api/nodes/{node_id}/sync-runtime`
  - `GET /api/nodes/{node_id}/runtime?refresh=true|false`
  - `GET /api/nodes/{node_id}/drift?refresh=true|false`
- Drift detector compares desired config with cached actual runtime.

## Still pending

### Phase 3 — UI runtime/drift cards
- Show runtime cache and drift results directly on node cards.
- Add manual Refresh Runtime button per node.
- Add View Runtime JSON and View Drift actions.

### Phase 4 — atomic apply/rollback
- Node should keep previous runtime if new config fails.
- Panel should show apply transaction id and post-apply runtime sync result.

### Phase 5 — deeper token test suite
- Add automated tests for valid/expired/bad-target/bad-signature peer tokens.

### Phase 6 — service extraction
- Move remaining large endpoint groups out of `app.py` into `api/` modules.
