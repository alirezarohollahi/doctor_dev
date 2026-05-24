# doctor_dev

`doctor_dev` is an async TCP forwarding-group manager.

It can run many forwarding groups. Each group owns one or more local inbound ports. Each inbound process forwards TCP traffic to static targets or to the currently published inbounds of another manager.

## Main ideas

- One manager process per server.
- Many asyncio tunnel tasks inside that manager.
- REST API for status, group inbounds, config reload, and sync.
- JSON config loaded from `.env`.
- Random ports are allocated and persisted in runtime state.
- Remote dependencies are polled and hot-reloaded.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Run

```bash
doctor-dev --env .env
```

Or:

```bash
python -m doctor_dev.main --env .env
```

## CLI examples

```bash
doctor-devctl --manager http://127.0.0.1:7001 status
doctor-devctl --manager http://127.0.0.1:7001 groups
doctor-devctl --manager http://127.0.0.1:7001 inbounds Iran-Node-Group-1
doctor-devctl --manager http://127.0.0.1:7001 sync
```

For token-protected managers:

```bash
doctor-devctl --manager http://127.0.0.1:7001 --token CHANGE_ME status
```

## Important

This is a TCP forwarding tool. Exposing manager APIs or inbound ports on public networks should be done only with firewall rules and API tokens.
