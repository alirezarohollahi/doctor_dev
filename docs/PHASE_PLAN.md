# Doctor Dev cleanup plan

The current stabilization plan is complete.

## Done

1. Phase 1: Hotfix/runtime/auth/single-core/inbound endpoint stabilization.
2. Phase 2: Single-port node cleanup and runtime drift API.
3. Phase 3: Runtime consistency and node runtime UI table.
4. Phase 4: Quality tests, cleanup, and safe apply rollback.
5. Phase 5: HTTP auth/token integration and node-control cleanup.
6. Phase 6: Panel API module split and app composition-root cleanup.
7. Phase 7: Performance/concurrency hardening for runtime sync.
8. Phase 8: End-to-end panel-to-node runtime/drift verification.

## Current rule

Do not add new features unless explicitly requested. Use the current codebase for bug fixes, runtime consistency fixes, and deployment hardening only.
