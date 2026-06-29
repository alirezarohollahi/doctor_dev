# Doctor Dev changelog by phases

## Phase 1

Hotfix/runtime/auth/single-core/inbound endpoint stabilization.

## Phase 2

Single-port node cleanup and runtime drift API.

## Phase 3

Runtime consistency and node runtime UI table.

## Phase 4

Quality tests, cleanup, and safe apply rollback.

## Phase 5

HTTP auth/token integration and node-control cleanup.

## Phase 6

Panel API module split and app composition-root cleanup.

## Phase 7

Performance and concurrency hardening for panel runtime sync:

- Bounded runtime-sync concurrency through `DOCTOR_DEV_PANEL_NODE_SYNC_CONCURRENCY`.
- Duplicate node IDs skipped during one sync pass.
- Stable result ordering preserved.
- Explicit timeout knobs for node check, sync, read, and apply paths.
- Cleaner node HTTP error details when a node returns structured auth/runtime errors.

## Phase 8

End-to-end panel-to-node verification:

- Starts a real node with `main.py` in tests.
- Creates temporary panel stores.
- Creates a node and one core with a random inbound.
- Applies desired config to the node over HTTP.
- Syncs runtime into the panel runtime cache.
- Verifies drift detection returns `ok`.

## Plan status

The original cleanup plan is complete through Phase 8. Future work should only happen if a new concrete bug or requested change appears.

## Phase 9 - Browser static asset fix

- Mounted `/assets` with `StaticFiles` before the SPA fallback.
- Added `/favicon.ico` route with `response_model=None` and no invalid union response annotation.
- Prevented API/static paths from falling through to `index.html`.
- Added a minimal local Font Awesome compatibility stylesheet for dev/lab builds.
- Included lab env/scripts for panel + two-node routing tests.

## Lab fix: dynamic Node Inbound endpoint resolution

- Fixed Node Inbound balancer endpoints so they resolve all live ports for the selected remote inbound instead of only the first port.
- Endpoint weight now applies to the selected inbound as a whole; if that inbound has multiple fixed/random live ports, traffic is split across those ports within the endpoint's share.
- Fixed stale peer-cache behavior: when the panel applies newer live-port data, the node prefers it over older peer-sync cache until peer sync catches up.
- Remote Node Inbound endpoints still keep themselves updated via peer runtime sync and peer tokens.
- UI endpoint inbound dropdown no longer appends a transient runtime port such as `. 1209`; it shows only the inbound name.
- Added tests for multi-port Node Inbound endpoint resolution, stale peer-cache behavior, and UI label cleanup.

## Dependency-scoped peer runtime sync fix

- Removed node-level runtime update interval from the Node UI/API model.
- Added dependency-level `sync_interval` for node dependencies.
- Node-to-node runtime refresh now uses the interval configured on the dependency entry.
- Node dependencies are enriched with peer token URL, sync URLs, target core id, peer host, and token refresh policy.
- Node-inbound balancer endpoints inherit their peer sync interval from the matching node dependency.
- Fixed dynamic node-inbound routing so fixed multi-port and random-port remote inbounds can update without a manual B-side port edit.
- Node Inbound endpoint dropdown labels show only the inbound name, not the current live port.
- Added quality tests for dependency-scoped sync interval, node-level interval removal, and token/sync enrichment.


## Peer Refresh Fix

- Fixed remote Node Inbound endpoints staying on stale live ports after the dependency node changed ports.
- Node runtime now refreshes due peer runtime before target resolution and force-refreshes once after stale target failures.
- Added peer sync diagnostics to `/runtime`: `peer_sync_errors`, `peer_sync_cache_nodes`, and `peer_sync_last`.
- Quality suite passes: `bash scripts/quality_check.sh`.
