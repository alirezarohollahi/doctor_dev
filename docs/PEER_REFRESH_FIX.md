# Peer Refresh Fix

This fix makes remote `Node Inbound` endpoints update themselves from dependency runtime state.

## Problem

A Node B balancer endpoint could reference an inbound on Node A. If Node A changed the inbound listen port from `1211` to `1209`, Node B could keep trying the stale port until a new config was manually applied or peer sync happened successfully.

## Fix

- Runtime now refreshes due peer dependencies before resolving balancer targets.
- If a connection attempt to stale targets fails, runtime forces one immediate peer refresh and retries once.
- Peer sync errors are now visible in `/runtime` under `summary.peer_sync_errors`.
- Peer sync cache node ids are visible under `summary.peer_sync_cache_nodes`.
- Peer sync last-run timestamps are visible under `summary.peer_sync_last`.

## Expected behavior

If `B -> NodeInbound(A/a-direct-9101)` and A changes from `1211` to `1209`, B should update after the dependency interval, or on the next failed/stale connection attempt, without a new B apply.
