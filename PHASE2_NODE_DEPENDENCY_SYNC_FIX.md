# Phase 2 — Node Dependency Runtime Sync Fix

## What changed

- Added a per-node `secret_token` separate from the panel `api_key`.
- Added node runtime export endpoint: `GET /config/export`.
- Peer nodes can fetch live listener state with `X-Doctor-Node-Token`.
- Panel periodically syncs live node runtime/listener state into `node-runtime-cache.json`.
- Node-inbound balancer endpoints are enriched with live random ports when available.
- Remote random inbounds can now be resolved by node-side peer sync instead of stale stored ports.
- Random inbound mode was rechecked with a runtime smoke test: `random_count=3` produced three real OS-assigned listening ports.

## New env

Panel:

- `DOCTOR_DEV_PANEL_NODE_SYNC=true`
- `DOCTOR_DEV_PANEL_NODE_SYNC_INTERVAL=10`
- `DOCTOR_DEV_PANEL_NODE_SYNC_TIMEOUT=3`
- `DOCTOR_DEV_NODE_RUNTIME_CACHE_PATH=/var/lib/doctor-dev-panel/node-runtime-cache.json`

Node:

- `NODE_SECRET_TOKEN=...`
- `DOCTOR_DEV_NODE_PEER_SYNC_INTERVAL=10`
- `DOCTOR_DEV_NODE_PEER_SYNC_TIMEOUT=3`

## Important

For a remote node-inbound dependency to work, the target node entry in the panel must have the same `secret_token` that is configured in that node env as `NODE_SECRET_TOKEN`.
