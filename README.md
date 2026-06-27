# Doctor Dev Panel v7

This version refines the core UI flow.

## Core flow

1. Create a core with only:
   - Core name
   - Target node
2. The core appears in the Cores page as a card.
3. Open the core to edit:
   - Inbounds
   - Routing
   - Balancers
   - Dependencies
   - Config preview

## Port roles

- `API_PORT`: control-plane port. The panel uses this port for `/health`, `/status`, `/config`, and future apply/deploy requests.
- `SERVICE_PORT`: data-plane port. This is reserved for high-performance routing/listener traffic.

If `SSL_CERT_FILE` and `SSL_KEY_FILE` are set on the node, the node API runs over HTTPS on `API_PORT`. Paste the matching public certificate/CA PEM into the panel node certificate field so status checks and future config calls can verify the node.

## Update panel

```bash
curl -fsSL https://github.com/alirezarohollahi/doctor_dev/raw/refs/heads/master/scripts/doctor_dev.sh -o /tmp/doctor_dev.sh \
  && sudo bash /tmp/doctor_dev.sh update-panel
```

## Install/update node

```bash
curl -fsSL https://github.com/alirezarohollahi/doctor_dev/raw/refs/heads/master/scripts/doctor_dev.sh -o /tmp/doctor_dev.sh \
  && sudo bash /tmp/doctor_dev.sh install-node
```

```bash
curl -fsSL https://github.com/alirezarohollahi/doctor_dev/raw/refs/heads/master/scripts/doctor_dev.sh -o /tmp/doctor_dev.sh \
  && sudo bash /tmp/doctor_dev.sh update-node
```

Default node CLI:

```bash
doctor-node help
doctor-node health
doctor-node config show
```
