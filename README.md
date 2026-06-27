# Doctor Dev Panel v6

This version adds the node control-plane/data-plane split and the first routing core foundation.

## Port roles

- `API_PORT`: control-plane port. The panel uses this port for `/health`, `/status`, `/config`, and future apply/deploy requests.
- `SERVICE_PORT`: data-plane port. This is reserved for high-performance routing/listener traffic.

If `SSL_CERT_FILE` and `SSL_KEY_FILE` are set on the node, the node API runs over HTTPS on `API_PORT`. Paste the matching **public certificate PEM** into the panel node certificate field so status checks and future config calls can verify the node.

## Panel

```bash
curl -fsSL https://github.com/alirezarohollahi/doctor_dev/raw/refs/heads/master/scripts/doctor_dev.sh -o /tmp/doctor_dev.sh \
  && sudo bash /tmp/doctor_dev.sh update-panel
```

## Node

```bash
curl -fsSL https://github.com/alirezarohollahi/doctor_dev/raw/refs/heads/master/scripts/doctor_dev.sh -o /tmp/doctor_dev.sh \
  && sudo bash /tmp/doctor_dev.sh install-node
```

Default node CLI:

```bash
docter-node help
docter-node health
docter-node config show
```

## Cores

A core belongs to one node. It can contain:

- Inbounds: bind IP, fixed or random ports, direct static target or balancer target, optional inbound certificate.
- Balancers: alias, strategy, endpoints. Endpoints can be static IP:port or an inbound selected from saved nodes/cores.

This release stores normalized configs and provides config previews. The actual high-performance forwarding runtime is the next step.
