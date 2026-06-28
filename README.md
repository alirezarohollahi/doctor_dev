# Doctor Dev Panel v9

This release finishes the current panel/node foundation with UI polish, safer errors, real apply endpoints, and an asyncio node-side TCP forwarding runtime.

## Fixed in v9

- String IDs are handled correctly everywhere. Node/core actions no longer convert `node_xxx` or `core_xxx` IDs with `parseInt`, which was the reason delete/open/apply could call the API with `NaN` and return `Node not found`.
- Core cards were redesigned into a cleaner operational summary with node health, inbound/balancer/dependency counts, updated/applied time, and actions.
- SVG icons are constrained globally and per button size, so raw inline icons cannot become oversized.
- Buttons such as Refresh are vertically centered and aligned.
- Expected node log failures are handled as clean warnings, not full tracebacks. A node without `/logs` now returns a clear `Run update-node` message.
- Panel can apply one core or all node cores to the selected node via the node API port.
- Node now reloads saved routing config on startup and runs an asyncio TCP forwarding runtime for configured inbounds.
- Logs page still supports panel logs and node logs through the node API port.

## Apply flow

- `POST /api/cores/{core_id}/apply` builds the selected node config and POSTs it to the node `/config/apply`.
- `POST /api/nodes/{node_id}/apply-config` applies all cores assigned to that node.
- Node `/config/apply` saves the config and starts/restarts runtime listeners.

## Runtime notes

- `API_PORT` is the control-plane port used by panel for health/status/config/logs/apply.
- `SERVICE_PORT` is data-plane context and default service listener value.
- Core inbounds create actual node-side TCP listeners.
- Direct static targets and balancer targets are supported.
- Balancer strategies supported: `round_robin`, `random`, `failover`, and a round-robin fallback for `least_connections` until per-endpoint connection accounting is expanded.


## Debug logging

Set `DEBUG=true` in `/etc/doctor-dev-panel/panel.env` to make the panel write full diagnostic request, response, node API, apply, validation, and error flow logs into the panel log file.

Set `DEBUG=true` in `/etc/doctor-node/node.env` to make the node write full diagnostic control-plane, config apply, runtime restore, and request logs into the node log file.

Sensitive values such as passwords, API keys, authorization headers, cookies, tokens, and private keys are redacted in debug output.

After changing debug mode, restart the related service:

```bash
sudo systemctl restart doctor-dev-panel
sudo systemctl restart doctor-node
```

## Update

```bash
curl -fsSL https://github.com/alirezarohollahi/doctor_dev/raw/refs/heads/master/scripts/doctor_dev.sh -o /tmp/doctor_dev.sh \
  && sudo bash /tmp/doctor_dev.sh update-panel
```

```bash
curl -fsSL https://github.com/alirezarohollahi/doctor_dev/raw/refs/heads/master/scripts/doctor_dev.sh -o /tmp/doctor_dev.sh \
  && sudo bash /tmp/doctor_dev.sh update-node
```

Hard refresh the browser after update: `Ctrl + F5`.
