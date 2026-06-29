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
