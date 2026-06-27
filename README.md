# Doctor Dev

Doctor Dev is a Linux-first control center for managing node agents, tunnel cores, inbound listeners, routes, balancers, certificates, runtime metrics, config versions, rollback and logs.

The project has two runtime roles:

```text
Panel  -> central management UI/API
Node   -> node-side agent that receives generated config and runs listeners
```

## Production install with curl

Panel install:

```bash
curl -fsSL https://github.com/PasarGuard/scripts/raw/main/doctor_dev.sh -o /tmp/doctor_dev.sh \
  && sudo bash /tmp/doctor_dev.sh install-panel
```

Node install:

```bash
curl -fsSL https://github.com/PasarGuard/scripts/raw/main/doctor_dev.sh -o /tmp/doctor_dev.sh \
  && sudo bash /tmp/doctor_dev.sh install-node
```

Default `install` is the same as `install-panel`:

```bash
curl -fsSL https://github.com/PasarGuard/scripts/raw/main/doctor_dev.sh -o /tmp/doctor_dev.sh \
  && sudo bash /tmp/doctor_dev.sh install
```

The bootstrap script clones or updates this repository:

```text
https://github.com/alirezarohollahi/doctor_dev
```

## Supported Linux package managers

The installer detects and supports:

```text
apt      Debian / Ubuntu
apk      Alpine
dnf      Fedora / RHEL / Rocky / Alma
yum      older CentOS/RHEL
zypper   openSUSE
pacman   Arch
```

It installs the required system packages such as Python 3, venv/pip, git, curl, certificates, OpenSSL, tar and unzip.

## Panel installer flow

Run:

```bash
sudo python3 scripts/install_panel.py
```

The installer does the following:

```text
1. Checks root/sudo.
2. Detects Linux distribution and package manager.
3. Checks whether a previous Panel installation exists.
4. If it exists, asks whether to remove it and continue.
5. Installs system and Python requirements.
6. Clones or updates the project from GitHub.
7. Creates /opt/doctor_dev/.venv and installs the project.
8. Asks how the Panel should be exposed:
   - IP without certificate
   - Domain with certificate
   - IP with certificate
9. Handles certificate paths, Let's Encrypt issuance, or self-signed certificate generation when explicitly requested.
10. Creates or accepts admin credentials.
11. Writes production config under /etc/doctor_dev/panel.
12. Installs the `doctor-panel` CLI.
13. Optionally creates and starts the systemd service.
14. Prints Panel URL, admin username and admin password.
15. Optionally starts the Node installer on the same machine.
```

At the end you get output similar to:

```text
Panel URL: https://panel.example.com
Admin username: admin_xxxxxx
Admin password: generated-password
Credentials file: /etc/doctor_dev/panel/admin_credentials.txt
Service: doctor-dev-panel.service
```

The credentials file is written with `0600` permissions.

## Panel exposure modes

### IP without certificate

Use this when you want a direct HTTP panel:

```text
http://SERVER_IP:8088
```

### Domain with certificate

Use this when you have a domain:

```text
https://panel.example.com
```

The installer can either use existing certificate files or issue a certificate through Certbot.

### IP with certificate

Use this when you already have certificate files for the IP, or when you intentionally want a self-signed certificate. Self-signed certificates are not trusted by browsers by default.

## Node installer flow

Run:

```bash
sudo python3 scripts/install_node.py
```

The installer does the following:

```text
1. Checks root/sudo.
2. Detects Linux distribution and package manager.
3. Installs required packages.
4. Checks whether a previous Node installation exists.
5. Clones or updates the project.
6. Creates /opt/doctor_dev/.venv and installs the project.
7. Asks for Node name, public address, API bind address and API port.
8. Generates or accepts a UUID API key.
9. Asks for protocol metadata: rest or grpc.
10. Asks for initial ports.
11. Asks for certificate mode:
    - no API certificate
    - existing fullchain/privkey
    - generated self-signed certificate
12. Writes production config under /etc/doctor_dev/nodes/<node-name>.
13. Installs the `doctor-node` CLI.
14. Optionally creates and starts a systemd service.
15. Prints node address, API port, protocol and API key.
```

Node information is saved to:

```text
/etc/doctor_dev/nodes/<node-name>/node_credentials.txt
```

## CLI commands

### Panel CLI

```bash
doctor-panel status
doctor-panel start
doctor-panel stop
doctor-panel restart
doctor-panel logs -f
doctor-panel config show
doctor-panel admin show
doctor-panel nodes list
doctor-panel cert list
doctor-panel backup create
```

### Node CLI

```bash
doctor-node status
doctor-node start
doctor-node stop
doctor-node restart
doctor-node logs -f
doctor-node config show
doctor-node runtime
doctor-node health
```

For multiple nodes on one host, pass the node name:

```bash
doctor-node --name edge-node-1 status
```

## systemd services

Panel service:

```bash
sudo systemctl status doctor-dev-panel
sudo systemctl restart doctor-dev-panel
sudo journalctl -u doctor-dev-panel -f
```

Node service:

```bash
sudo systemctl status doctor-dev-node-edge-node-1
sudo systemctl restart doctor-dev-node-edge-node-1
sudo journalctl -u doctor-dev-node-edge-node-1 -f
```

If systemd is not available, the installer prints a manual command using the generated environment file.

## Production paths

```text
/opt/doctor_dev                 source and virtualenv
/etc/doctor_dev                 configuration
/etc/doctor_dev/panel           panel config
/etc/doctor_dev/nodes           node config
/etc/doctor_dev/certs           certificate aliases
/var/lib/doctor_dev             runtime state
/var/log/doctor_dev             logs
/var/backups/doctor_dev         backups
```

## Panel UI workflow

1. Open the Panel URL printed by the installer.
2. Enter the admin username and password.
3. Open **Nodes**.
4. Add nodes as cards.
5. Click a node card to edit it.
6. Use multi-select, Select All and Delete Selected for bulk operations.
7. Open **Certificates** to create reusable certificate aliases.
8. Open **Cores** to build inbound listeners, routes, targets, balancers and policies.
9. Use **Dry Run** before applying a core.
10. Use **Apply** to push generated config to the selected node.
11. Use **Runtime**, **Logs**, **Versions** and **Audit** for operation and troubleshooting.

## Uninstall

Using the bootstrap script:

```bash
sudo bash /tmp/doctor_dev.sh uninstall
```

Or from the project:

```bash
sudo python3 scripts/uninstall.py
```

The uninstaller asks whether to remove only services/CLI wrappers or also source, config, data, logs and backups.

## Development install on Linux

```bash
git clone https://github.com/alirezarohollahi/doctor_dev
cd doctor_dev
python3 -m venv .venv
. .venv/bin/activate
pip install -U pip setuptools wheel
pip install -r requirements.txt
pip install -e .
pytest -q
```

Manual Panel start:

```bash
DOCTOR_DEV_AUTH_REQUIRED=1 \
DOCTOR_DEV_ADMIN_USERNAME=admin \
DOCTOR_DEV_ADMIN_PASSWORD='change-me' \
DOCTOR_DEV_PANEL_HOST=0.0.0.0 \
DOCTOR_DEV_PANEL_PORT=8088 \
python -m doctor_dev_panel
```

Manual Node start:

```bash
DOCTOR_DEV_NODE_NAME=edge-node-1 \
DOCTOR_DEV_AGENT_HOST=0.0.0.0 \
DOCTOR_DEV_AGENT_PORT=9101 \
DOCTOR_DEV_AGENT_API_KEY='replace-with-uuid' \
python -m doctor_dev_agent
```

## Installer safety notes

The Linux installers are defensive against bad interactive input. File paths are normalized before use: surrounding quotes, pasted whitespace, environment variables, `~`, and accidental trailing backslashes are handled. If a certificate path is wrong, the installer will ask again instead of crashing.

Panel installation completes and prints the Panel URL/admin credentials before the optional local Node installation is started. If the optional Node installer is cancelled or fails, the Panel remains installed and can be used normally.

When the bootstrap installer detects an existing Panel or Node installation, it warns at the beginning and the Python installer asks whether to remove the old installation and continue from a clean state.
