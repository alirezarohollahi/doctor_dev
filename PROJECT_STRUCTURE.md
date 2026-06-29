# Doctor Dev clean architecture

## Goal

The project is now organized around clear boundaries instead of placing UI, API,
node networking, persistence, and validation in a few very large files.

## Top-level layout

```text
doctor_dev_panel/
  api/               # feature-based API route modules
  services/          # business logic and node orchestration
  stores/            # JSON/file persistence layer
  web/               # frontend assets
  app.py             # compatibility composition root

doctor_dev_node/
  api/               # node HTTP endpoints
  config/            # routing config persistence
  security/          # API key/token checks
  services/          # runtime/peer-sync orchestration
  runtime.py         # TCP data-plane runtime
  server.py          # compatibility composition root
```

## Rules for future code

1. Route handlers should be thin and live under `doctor_dev_panel/api/`.
2. Node communication should go under `doctor_dev_panel/services/`.
3. File-backed data access should go under `doctor_dev_panel/stores/`.
4. Node auth/config helpers should live under `doctor_dev_node/security/` and
   `doctor_dev_node/config/`.
5. Root-level modules that still exist are compatibility shims. Do not add new
   logic to them.

## Migration status

This patch creates the clean structure and moves the persistence layer under
`stores/` while keeping old imports working. The next safe step is moving the
large endpoint groups from `app.py` into `api/nodes.py`, `api/cores.py`,
`api/logs.py`, and `api/system.py`.


