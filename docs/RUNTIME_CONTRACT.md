# Node runtime contract

The node exposes one management API port: `API_PORT`. Runtime listener ports are created from inbound config.

## Endpoints

- `GET /health`: open health check.
- `GET /status`: requires `Authorization: Bearer <API_KEY>`.
- `GET /runtime`: requires panel API key or peer token.
- `GET /config/export`: backward-compatible alias of `/runtime`.
- `POST /config/apply`: requires panel API key.

## Runtime export must include

- `node_id`
- API host/port/tls info
- active core id/name
- desired inbounds/balancers summary
- actual listeners with real assigned ports
- counters and last error

## Auth

Panel to node uses:

```http
Authorization: Bearer <NODE_API_KEY>
```

Peer runtime sync uses:

```http
X-Doctor-Node-Token: <short-lived-token>
```


## API identity consistency rule

If the node is launched with CLI overrides, for example:

```bash
python main.py --mode node --env node.env --host 127.0.0.1 --port 9098
```

then `/health` and `/runtime` must report `port: 9098` and `api_port: 9098`, even if `node.env` still contains `API_PORT=62051`. The running process sets `DOCTOR_DEV_NODE_BOUND_HOST` and `DOCTOR_DEV_NODE_BOUND_API_PORT` before importing the ASGI app, and those bound values are the source of truth for runtime self-reporting.
