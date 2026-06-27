# Doctor Dev

Doctor Dev is a local-first control panel for managing node agents, tunnel cores, inbound listeners, routes, balancers, certificates, runtime metrics, config versions, rollback and logs.

The project is split into two runtime parts:

```text
Panel  -> central management UI/API
Agent  -> node-side runtime that receives generated config and runs tunnel listeners
```

## What is ready

```text
- SAP/Fiori-inspired separated work centers
- Nodes page with grid cards
- Click a node card to edit it
- Select multiple nodes, Select All, and bulk delete
- Standalone Certificate Manager with certificate aliases
- Visual Core Builder
- Multiple inbound listeners per inbound
- Static targets with multiple ports
- Local inbound chain targets
- Remote node group targets
- Balancers: round_robin, random, failover, weighted_round_robin
- max_users and max_active_connections policies
- TLS certificate validation
- Real TLS runtime listener for local testing
- Dry Run / Apply
- Config Versioning / Diff / Rollback
- Audit Log
- Runtime metrics
- Node logs
- Local TCP/TLS Test Lab
- Python reset/start script with generated admin credentials
- Python node start script
```

## Install on Windows

Open PowerShell in the project folder:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\pip.exe install -r requirements.txt
.\.venv\Scripts\pip.exe install -e .
.\.venv\Scripts\python.exe -m pytest -q
```

Or use the helper:

```powershell
.\install-windows.ps1
```

## Clean reset and start from zero

This is the recommended way for a full local test. It clears local state, generates random admin credentials, starts two local node agents, then starts the panel.

```powershell
.\.venv\Scripts\python.exe .\scripts\reset_and_start.py
```

The script asks for:

```text
- Panel host
- Panel port
- Node A API port
- Node B API port
- Echo ports for both nodes
- Admin username
- Whether to remove custom certificates
```

At the end it prints:

```text
Panel URL
Admin username
Admin password
Node A / Node B details
State and log paths
```

Open the printed Panel URL. If the browser asks for credentials, use the printed admin username/password.

## Start a single node manually

Use this when you want to bring up a node by itself:

```powershell
.\.venv\Scripts\python.exe .\scripts\start_node.py `
  --name local-node-a `
  --api-port 9101 `
  --api-key local-dev-key-a `
  --echo-ports 3000,3001
```

Another node:

```powershell
.\.venv\Scripts\python.exe .\scripts\start_node.py `
  --name local-node-b `
  --api-port 9102 `
  --api-key local-dev-key-b `
  --echo-ports 3100,3101
```

Then start the panel:

```powershell
$env:DOCTOR_DEV_PANEL_HOST="127.0.0.1"
$env:DOCTOR_DEV_PANEL_PORT="8088"
$env:DOCTOR_DEV_AUTH_REQUIRED="0"
.\.venv\Scripts\python.exe -m doctor_dev_panel
```

## Quick local test inside the UI

After `reset_and_start.py` opens the panel:

### 1. Register local nodes

Open **Nodes**.

Click:

```text
Seed Local Nodes
Refresh
```

You should see two cards:

```text
local-node-a
local-node-b
```

Click **Check** on both cards. Their status should become `online`.

### 2. Test node grid and bulk delete

In **Nodes**:

```text
- Use search to filter nodes
- Click a card to edit node settings
- Tick one or more checkboxes
- Use Select All
- Use Delete Selected only on throwaway nodes
```

Do not delete `local-node-a` or `local-node-b` until you finish the local test.

### 3. Create and apply a TLS runtime core

Open **Local Test Lab**.

Click:

```text
Create TLS Test Core
Apply TLS Test Core
Run TLS Test
```

Expected response contains:

```text
doctor-dev-echo:local-node-a:hello-doctor-dev-tls
```

This validates:

```text
Panel -> Agent
Certificate path validation
TLS listener
TLS test client
Tunnel forwarding to local echo target
Runtime logs
```

### 4. Create and apply a remote route

Open **Local Test Lab**.

Click:

```text
Create Remote Route
Apply Remote Route
```

Then set:

```text
Host: 127.0.0.1
Port: 18090
Payload: hello-remote-route
```

Click:

```text
Run TCP Test
```

Expected response contains:

```text
doctor-dev-echo:local-node-b:hello-remote-route
```

This validates:

```text
Node A inbound
Remote group target resolution
Node B inbound
Node B final static echo targets
Balancer path
Logs on both nodes
```

### 5. Build a custom core manually

Open **Cores**.

Use **Core Builder**:

```text
1. Select Node
2. Set Core Name
3. Set inbound name, listen IP and listen ports CSV
4. Set limits: Max Users / Max Active Connections
5. Choose TLS mode if needed
6. Choose target mode:
   - static IP/ports
   - local inbound chain
   - remote node group
7. Choose balancer
8. Preview Payload
9. Save Core
10. Dry Run
11. Apply
```

Then test the port from **Local Test Lab**.

### 6. Certificate aliases

Open **Certificates**.

Create a certificate alias using the bundled local certificate:

```text
Alias: local-test-cert
Domain: local.test
fullchain path: certs/local.test/fullchain.pem
privkey path: certs/local.test/privkey.pem
```

Click:

```text
Validate Paths
Create Path Certificate
```

Then in **Cores**, set:

```text
TLS Mode: stored certificate alias
Certificate Alias: local-test-cert / local.test
```

### 7. Config versions, diff and rollback

After you run **Dry Run** or **Apply** on a core:

Open **Cores** and click:

```text
Versions
Diff
```

Open **Versions & Audit** to inspect version history. You can restore a version with:

```text
Rollback + Apply
```

### 8. Runtime and logs

Open **Runtime**:

```text
Fetch Runtime From All Nodes
Discover All Nodes
```

Open **Logs**:

```text
Fetch Logs From All Nodes
```

## Useful ports in the default local lab

```text
Panel: 127.0.0.1:8088
Agent local-node-a: 127.0.0.1:9101
Agent local-node-b: 127.0.0.1:9102
Node A echo targets: 3000,3001
Node B echo targets: 3100,3101
TLS test listener: 18443
Remote route entry listener: 18090
Node B remote inbound: 19100
```

## Data locations

```text
data/panel_state.json             Panel state
logs/                             Panel and agent logs
configs/generated/                Generated apply/dry-run configs
certs/local.test/                 Bundled local self-signed certificate
.env.local                        Generated local credentials and API keys
```

## Notes for real deployment later

The local project is ready for full local testing. For real public deployment, use a reverse proxy or firewall, enable authentication, keep API keys secret, use real certificates, and run panel/agents as services instead of interactive terminals.
