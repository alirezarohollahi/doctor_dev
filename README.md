# Doctor Dev Panel v5 — Node Status + Service CLI

This version includes:

- English UI only
- Secure admin login
- Nodes page
- Create/Edit/Delete nodes
- Real node status check button
- API key generator
- Advanced node settings saved for future phases
- Panel CLI service management
- Node CLI service management
- Cleaner update behavior: update-panel/update-node rewrites and enables systemd services instead of warning incorrectly

## Panel update

```bash
curl -fsSL https://github.com/alirezarohollahi/doctor_dev/raw/refs/heads/master/scripts/doctor_dev.sh -o /tmp/doctor_dev.sh \
  && sudo bash /tmp/doctor_dev.sh update-panel
```

## Node update

```bash
curl -fsSL https://github.com/alirezarohollahi/doctor_dev/raw/refs/heads/master/scripts/doctor_dev.sh -o /tmp/doctor_dev.sh \
  && sudo bash /tmp/doctor_dev.sh update-node
```

For a custom node CLI name:

```bash
curl -fsSL https://github.com/alirezarohollahi/doctor_dev/raw/refs/heads/master/scripts/doctor_dev.sh -o /tmp/doctor_dev.sh \
  && sudo DOCTOR_DEV_NODE_CLI_NAME=my-node bash /tmp/doctor_dev.sh update-node
```

## Panel CLI

```bash
doctor-dev help
doctor-dev health
doctor-dev status
doctor-dev logs
doctor-dev restart
doctor-dev config edit
doctor-dev service install
doctor-dev service remove
doctor-dev service enable
doctor-dev service disable
doctor-dev admin list
doctor-dev admin add USERNAME
doctor-dev admin passwd USERNAME
doctor-dev admin remove USERNAME
```

## Node CLI

Default node CLI name is `docter-node` unless changed during install.

```bash
docter-node help
docter-node health
docter-node status
docter-node logs
docter-node restart
docter-node config edit
docter-node service install
docter-node service remove
docter-node service enable
docter-node service disable
```

## Node form notes

- New nodes are enabled by default.
- Disabled means the node is saved but intentionally not active in the panel.
- Pending Check means the node is enabled but not checked yet.
- Running means the panel could reach `/status` or `/health` on the node.
- Error means the panel could not reach the node.
- Certificate is optional for now. Leave it empty for non-TLS nodes. Only public certificate PEM goes there; private keys stay on the node server.
