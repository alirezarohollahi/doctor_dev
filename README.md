# Doctor Dev Panel

Clean login foundation for Doctor Dev Panel.

## Install from GitHub

```bash
curl -fsSL https://github.com/alirezarohollahi/doctor_dev/raw/refs/heads/master/scripts/doctor_dev.sh -o /tmp/doctor_dev.sh \
  && sudo bash /tmp/doctor_dev.sh install-panel
```

After the first install, you can update only:

```bash
curl -fsSL https://github.com/alirezarohollahi/doctor_dev/raw/refs/heads/master/scripts/doctor_dev.sh -o /tmp/doctor_dev.sh \
  && sudo bash /tmp/doctor_dev.sh update-panel
```

Or:

```bash
doctor-dev update
```

## CLI

```bash
doctor-dev help
doctor-dev status
doctor-dev logs
doctor-dev health
doctor-dev restart
doctor-dev config edit
```

Admin management:

```bash
doctor-dev admin list
doctor-dev admin add USERNAME
doctor-dev admin passwd USERNAME
doctor-dev admin remove USERNAME
```

## Paths

Default paths on Linux:

```text
App directory:    /opt/doctor-dev-panel
Config directory: /etc/doctor-dev-panel
Env file:         /etc/doctor-dev-panel/panel.env
Admin store:      /etc/doctor-dev-panel/admins.json
Data directory:   /var/lib/doctor-dev-panel
Log directory:    /var/log/doctor-dev-panel
```

## Fonts

Put the font files here inside the project:

```text
doctor_dev_panel/web/assets/fonts/
```

For the current English UI, these files are referenced by CSS:

```text
vazirmatn-latin-400-normal.woff2
vazirmatn-latin-500-normal.woff2
vazirmatn-latin-600-normal.woff2
vazirmatn-latin-700-normal.woff2
```

On a server install, the final path is:

```text
/opt/doctor-dev-panel/doctor_dev_panel/web/assets/fonts/
```

Then restart:

```bash
doctor-dev restart
```
