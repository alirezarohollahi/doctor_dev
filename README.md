# Doctor Dev Panel

Clean rebuild foundation for Doctor Dev.

Current phase:

- Secure English admin login
- Multi-admin CLI
- Panel systemd install/update
- Node inventory page
- Create/Edit/Delete Node modal
- API key generation button
- Node install/update script and default `docter-node` CLI
- Node base service with `/health` and `/status`

No forwarding/runtime node logic is attached yet.

## Remote install

```bash
curl -fsSL https://github.com/alirezarohollahi/doctor_dev/raw/refs/heads/master/scripts/doctor_dev.sh -o /tmp/doctor_dev.sh \
  && sudo bash /tmp/doctor_dev.sh install-panel
```

## Remote update

```bash
curl -fsSL https://github.com/alirezarohollahi/doctor_dev/raw/refs/heads/master/scripts/doctor_dev.sh -o /tmp/doctor_dev.sh \
  && sudo bash /tmp/doctor_dev.sh update-panel
```

## Node install

```bash
curl -fsSL https://github.com/alirezarohollahi/doctor_dev/raw/refs/heads/master/scripts/doctor_dev.sh -o /tmp/doctor_dev.sh \
  && sudo bash /tmp/doctor_dev.sh install-node
```

Default node CLI name is `docter-node`. You can choose a different name during install.
If that CLI/service/app name already exists, install-node cleans it by stopping the service, removing the CLI, backing up the app/config directories and creating a fresh installation.

## Node update

```bash
curl -fsSL https://github.com/alirezarohollahi/doctor_dev/raw/refs/heads/master/scripts/doctor_dev.sh -o /tmp/doctor_dev.sh \
  && sudo bash /tmp/doctor_dev.sh update-node
```

To update a custom node CLI name non-interactively:

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
doctor-dev update

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

## Font path

The UI references Vazirmatn files from:

```text
doctor_dev_panel/web/assets/fonts/
```

After install:

```text
/opt/doctor-dev-panel/doctor_dev_panel/web/assets/fonts/
```
