# Panel services

Use this folder for business/orchestration code:

- `node_control.py`: talking to nodes, checking status, applying configs.
- `runtime_sync.py`: periodic node runtime cache refresh.
- `topology_validation.py`: validating core/dependency/balancer graphs.

The current large `app.py` is kept working, but new code should be placed here first.


