# Phase 7 and 8 final hardening

This phase does not add product features. It finishes the current cleanup plan with performance safeguards and an end-to-end correctness check.

## Phase 7: performance and concurrency

Panel runtime sync is now bounded by `DOCTOR_DEV_PANEL_NODE_SYNC_CONCURRENCY` instead of launching an unbounded number of simultaneous node checks. Duplicate node IDs are ignored during a single sync run, and result ordering remains stable.

Timeouts are explicit and configurable:

```env
DOCTOR_DEV_PANEL_NODE_SYNC_TIMEOUT=3
DOCTOR_DEV_PANEL_NODE_SYNC_CONCURRENCY=16
DOCTOR_DEV_PANEL_NODE_CHECK_TIMEOUT=4
DOCTOR_DEV_PANEL_NODE_API_TIMEOUT=5
DOCTOR_DEV_PANEL_NODE_APPLY_TIMEOUT=8
```

## Phase 8: end-to-end verification

The test suite now includes a full panel-to-node path:

1. Start a real node through `main.py`.
2. Create a panel node record in temporary stores.
3. Create a core with a random inbound.
4. Build the desired node config.
5. Apply the config to the node through the panel node-control service.
6. Sync runtime back into the panel runtime cache.
7. Run drift detection and require `status=ok`.

Run everything with:

```bash
bash scripts/quality_check.sh
```
