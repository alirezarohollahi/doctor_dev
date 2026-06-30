
# Phase 6 — API module split and composition-root cleanup

This phase does not add product features. It only makes the existing panel code easier to change and test.

## What changed

- `doctor_dev_panel/app.py` is now small and only owns:
  - app creation
  - security/debug middleware
  - router registration
  - `/` and `/admin` SPA entrypoints
  - SPA fallback
- Route groups moved to:
  - `api/auth.py`
  - `api/system.py`
  - `api/nodes.py`
  - `api/cores.py`
  - `api/logs.py`
- Shared helper code moved to `deps.py`.
- Runtime sync moved to `services/runtime_sync.py`.

## Fixed during cleanup

The previous phase had route handlers calling `_sync_node_runtime_once`, but no implementation existed in `app.py`. The new `runtime_sync` service provides:

```python
sync_node_runtime_once(node)
sync_all_node_runtime(nodes)
```

The route handlers now call this service directly.

## Quality check

Run:

```bash
bash scripts/quality_check.sh
```

The quality suite imports the panel app and checks that key routes are still registered.



