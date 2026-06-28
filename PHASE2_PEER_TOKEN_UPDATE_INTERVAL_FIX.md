# Phase 2 — Peer Token + Update Interval Dependency Sync

## What changed

- Added `Peer Token` support for nodes through `secret_token` / `NODE_SECRET_TOKEN`.
- Added node `Update Interval` in the Add/Edit Node UI.
- The panel stores `update_interval` per node and sends it into node-side configs.
- When a core depends on another node, the panel enriches the applied config with that peer node's:
  - `sync_urls`
  - `secret_token`
  - `update_interval`
  - certificate/public host metadata
- Node runtime now pulls dependency/peer runtime state periodically by using `X-Doctor-Node-Token`.
- Peer sync is per peer and interval-aware. Different dependency nodes can have different update intervals.
- Node runtime also reads peer sync credentials from `node_inbound` balancer endpoints, so remote random inbound ports can update without manual re-apply.
- Added `/config/export` on nodes for safe runtime/listener export.

## Node env

The token configured in the panel for a node must match the node's env:

```env
NODE_SECRET_TOKEN=your-peer-token
# or
DOCTOR_DEV_NODE_SECRET_TOKEN=your-peer-token
```

Fallback global interval if an old panel does not send `update_interval`:

```env
DOCTOR_DEV_NODE_PEER_SYNC_INTERVAL=10
DOCTOR_DEV_NODE_PEER_SYNC_TIMEOUT=3
```

## Panel env

Panel runtime cache sync can stay enabled:

```env
DOCTOR_DEV_PANEL_NODE_SYNC=true
DOCTOR_DEV_PANEL_NODE_SYNC_INTERVAL=10
DOCTOR_DEV_PANEL_NODE_SYNC_TIMEOUT=3
DOCTOR_DEV_NODE_RUNTIME_CACHE_PATH=/var/lib/doctor-dev-panel/node-runtime-cache.json
```

## Flow

1. Add Node B in the panel.
2. Generate/set Peer Token and Update Interval for Node B.
3. Set the same token in Node B env as `NODE_SECRET_TOKEN`.
4. Add Node B as a dependency or as a Node Inbound endpoint in a core running on Node A.
5. Apply the core to Node A.
6. Node A receives Node B's peer token and pulls Node B runtime state automatically on the configured interval.
