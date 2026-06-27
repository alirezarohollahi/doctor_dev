# Doctor Dev Panel

Clean Doctor Dev foundation with:

- Secure English admin login
- Multi-admin CLI management
- Nodes page and node inventory JSON store
- Create/Edit/Delete Node modal
- Generate API Key button
- Panel installer/update flow
- Node installer/update flow with default CLI name `docter-node`

This version is still a foundation step. It stores node definitions and prepares the UI/API shape, but runtime forwarding, core linking, health checks, log streaming, and real node actions are intentionally not attached yet.

## Node fields in this phase

When adding a node, the panel stores these fields:

| Field | Meaning |
|---|---|
| Node Name | Friendly panel name for the node |
| Node Address | Domain or IP of the installed node |
| Node Port | Main node service port. This maps to `SERVICE_PORT` in the node env. Default: `62050` |
| API Key | Must match `API_KEY` in the node env. Use the generate button if needed |
| TLS Certificate | Optional public certificate PEM. Leave it empty for now unless the node is configured with TLS |
| Enabled | Marks the node as enabled in the panel. Until real health checks are added, enabled nodes show `Pending Check` |
| API Port | Reserved for future management/API separation. Default: `62051` |
| Connection Type | `grpc` or `rest`; stored for upcoming node logic |
| Keep Alive / Unit | Stored for upcoming node logic |
| Data Limit | Optional GB limit metadata |
| Default Timeout | Stored for upcoming node logic |
| Internal Timeout | Stored for upcoming node logic |
| Proxy URL | Optional proxy metadata |

`Core Configuration` is no longer collected while creating a node. Cores will be managed in their own phase/page.

## Install panel

```bash
curl -fsSL https://github.com/alirezarohollahi/doctor_dev/raw/refs/heads/master/scripts/doctor_dev.sh -o /tmp/doctor_dev.sh \
  && sudo bash /tmp/doctor_dev.sh install-panel
```

## Update panel

```bash
curl -fsSL https://github.com/alirezarohollahi/doctor_dev/raw/refs/heads/master/scripts/doctor_dev.sh -o /tmp/doctor_dev.sh \
  && sudo bash /tmp/doctor_dev.sh update-panel
```

## Install node

```bash
curl -fsSL https://github.com/alirezarohollahi/doctor_dev/raw/refs/heads/master/scripts/doctor_dev.sh -o /tmp/doctor_dev.sh \
  && sudo bash /tmp/doctor_dev.sh install-node
```

Default node CLI name: `docter-node`.

To install/update with a custom node CLI name:

```bash
curl -fsSL https://github.com/alirezarohollahi/doctor_dev/raw/refs/heads/master/scripts/doctor_dev.sh -o /tmp/doctor_dev.sh \
  && sudo DOCTOR_DEV_NODE_CLI_NAME=my-node-cli bash /tmp/doctor_dev.sh install-node
```

If the requested node CLI/service/app path already exists, installer cleans/backups the old installation and recreates it.

## Update node

```bash
curl -fsSL https://github.com/alirezarohollahi/doctor_dev/raw/refs/heads/master/scripts/doctor_dev.sh -o /tmp/doctor_dev.sh \
  && sudo bash /tmp/doctor_dev.sh update-node
```

## Panel CLI

```bash
doctor-dev help
doctor-dev health
doctor-dev status
doctor-dev logs
doctor-dev restart
doctor-dev config edit
doctor-dev admin list
doctor-dev admin add USERNAME
doctor-dev admin passwd USERNAME
doctor-dev admin remove USERNAME
```

## Node CLI

```bash
docter-node help
docter-node health
docter-node status
docter-node logs
docter-node restart
docter-node config edit
docter-node update
```

## Fonts

Put UI fonts here:

```text
doctor_dev_panel/web/assets/fonts/
```

On server:

```text
/opt/doctor-dev-panel/doctor_dev_panel/web/assets/fonts/
```
