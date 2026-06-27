# Doctor Dev Panel v8

This version fixes the core creation flow and adds a real Logs page.

## What changed

- Core creation now gives visible errors instead of failing silently.
- The UI refreshes node data before opening the Create Core modal.
- API validation errors are formatted properly instead of showing `[object Object]`.
- Panel writes structured logs to `DOCTOR_DEV_PANEL_LOG_FILE` or `DOCTOR_DEV_LOG_DIR/panel.log`.
- Node writes structured logs to `DOCTOR_DEV_NODE_LOG_FILE` or `DOCTOR_DEV_NODE_LOG_DIR/node.log`.
- Panel has `/api/logs/sources` and `/api/logs`.
- Node has authenticated `/logs`.
- The Logs page can show panel logs or any saved node's logs through the node API Port.

## Update panel

```bash
curl -fsSL https://github.com/alirezarohollahi/doctor_dev/raw/refs/heads/master/scripts/doctor_dev.sh -o /tmp/doctor_dev.sh \
  && sudo bash /tmp/doctor_dev.sh update-panel
```

## Update node

```bash
curl -fsSL https://github.com/alirezarohollahi/doctor_dev/raw/refs/heads/master/scripts/doctor_dev.sh -o /tmp/doctor_dev.sh \
  && sudo bash /tmp/doctor_dev.sh update-node
```

## CLI logs

```bash
doctor-dev logs
# or
doctor-node logs
```

## Web logs

Open the panel, then go to **Logs**. Choose:

- `Panel logs`
- `Node: <node name>`

Node logs are fetched from the node control-plane API using the saved `API Port`, `API Key`, address, and TLS certificate configuration.
