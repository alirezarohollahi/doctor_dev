# Doctor Dev local routing lab

This lab runs one panel and two nodes on one Linux server:

- Panel: `http://SERVER_IP:9000`
- Node A API: `http://127.0.0.1:9001`
- Node B API: `http://127.0.0.1:9002`
- Test TCP listeners: `127.0.0.1:9101`, `9102`, `9103`, `9104`

No backup feature is required or used.

## 1) Copy files

Copy these files into the project root, preserving paths:

```text
env.examples/lab-panel.env
env.examples/lab-node-a.env
env.examples/lab-node-b.env
scripts/lab_make_admin.sh
scripts/lab_run_stack.sh
scripts/lab_stop_stack.sh
scripts/lab_check_stack.sh
tests/lab_multi_listener.py
tests/lab_sender.py
```

## 2) Install dependencies

```bash
cd /path/to/doctor_dev
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install --no-cache-dir --only-binary=:all: -r requirements.txt
python -m compileall doctor_dev_panel doctor_dev_node main.py
```

## 3) Create admin

```bash
bash scripts/lab_make_admin.sh admin admin12345
```

## 4) Start listener terminal

Open a terminal:

```bash
source .venv/bin/activate
python tests/lab_multi_listener.py --host 127.0.0.1 --ports 9101,9102,9103,9104
```

The listener prints each received payload with a different color per port.

## 5) Start panel + nodes

Open another terminal:

```bash
source .venv/bin/activate
bash scripts/lab_run_stack.sh
```

Check:

```bash
bash scripts/lab_check_stack.sh
```

## 6) Add nodes in panel

Open:

```text
http://SERVER_IP:9000
```

Login:

```text
username: admin
password: admin12345
```

Add Node A:

```text
Name: Lab Node A
Address: 127.0.0.1
API Port: 9001
API Key: lab-node-a-key-11111111-1111-1111-1111-111111111111
Update Interval: 3
Peer Token Refresh: 30
Peer Token TTL: 120
Enabled: ON
```

Add Node B:

```text
Name: Lab Node B
Address: 127.0.0.1
API Port: 9002
API Key: lab-node-b-key-22222222-2222-2222-2222-222222222222
Update Interval: 3
Peer Token Refresh: 30
Peer Token TTL: 120
Enabled: ON
```

After saving each node, click/check:

```text
Check Status
Sync Runtime / Refresh Runtime
```

Expected state:

```text
reachable=true
auth_ok=true
runtime_ok=true
API port actual = 9001 for A, 9002 for B
```

## 7) Sender command

Send test payloads to any node inbound/listener port:

```bash
python tests/lab_sender.py --host 127.0.0.1 --port PORT --message "scenario-x" --count 5 --interval 0.5
```

Examples:

```bash
python tests/lab_sender.py --host 127.0.0.1 --port 9101 --message direct-listener --count 2
python tests/lab_sender.py --host 127.0.0.1 --port 12001 --message through-node-a --count 5
```

## 8) Scenario templates

Use these later, one by one.

### Scenario 1: Direct forward from A to one listener port

On Node A create one core, then one inbound:

```text
Core name: A Core
Node: Lab Node A
Inbound name: a-direct-9101
Bind IP: 127.0.0.1 or 0.0.0.0
Port mode: fixed
Fixed port: 12001
Target type: static
Target host: 127.0.0.1
Target port: 9101
Enabled: ON
```

Apply/restart node config from panel. Test:

```bash
python tests/lab_sender.py --host 127.0.0.1 --port 12001 --message "A direct to 9101" --count 5
```

Expected listener output: only colored logs for `listener_port=9101`.

### Scenario 2: A balancer to all four direct listener ports

On Node A add balancer:

```text
Alias: a-direct-four
Strategy: round_robin / random / failover / least_connections
Endpoints:
  static 127.0.0.1:9101 enabled
  static 127.0.0.1:9102 enabled
  static 127.0.0.1:9103 enabled
  static 127.0.0.1:9104 enabled
```

Add inbound:

```text
Inbound name: a-balance-four
Fixed port: 12002
Target type: balancer
Target balancer: a-direct-four
Enabled: ON
```

Test:

```bash
python tests/lab_sender.py --host 127.0.0.1 --port 12002 --message "A balancer four" --count 12 --interval 0.2
```

Change balancer strategy and apply again for each strategy.

### Scenario 3: B forwards to A, and A forwards direct to four ports without balancer

On A create four static inbounds:

```text
a-to-9101 fixed 12101 -> 127.0.0.1:9101
a-to-9102 fixed 12102 -> 127.0.0.1:9102
a-to-9103 fixed 12103 -> 127.0.0.1:9103
a-to-9104 fixed 12104 -> 127.0.0.1:9104
```

On B create one inbound at a time targeting one A inbound fixed port directly:

```text
b-to-a-12101 fixed 12201 -> 127.0.0.1:12101
```

Test:

```bash
python tests/lab_sender.py --host 127.0.0.1 --port 12201 --message "B -> A -> 9101" --count 5
```

### Scenario 4: B forwards to A and uses balancer for another endpoint

On A keep `a-balance-four` fixed `12002`. On B create:

```text
b-to-a-balancer fixed 12202 -> 127.0.0.1:12002
```

Test:

```bash
python tests/lab_sender.py --host 127.0.0.1 --port 12202 --message "B -> A balancer" --count 12
```

Expected: listener output across multiple `910x` ports depending on strategy.

### Scenario 5: B forwards to an A inbound that is disabled

Disable an A inbound such as `a-to-9102`, apply A, sync runtime. Then on B try targeting that disabled inbound by direct port or node-inbound endpoint.

Expected: connection should fail or endpoint should not resolve. If it succeeds, disabled inbound filtering is broken.

### Scenario 6: B forwards to two endpoints, two inbounds in A

On A enable two inbounds:

```text
a-to-9101 fixed 12101 -> 9101
a-to-9102 fixed 12102 -> 9102
```

On B create balancer:

```text
Alias: b-two-a-inbounds
Strategy: round_robin
Endpoints:
  node_inbound -> Lab Node A / A Core / a-to-9101
  node_inbound -> Lab Node A / A Core / a-to-9102
```

On B create inbound:

```text
b-balance-two-a fixed 12203 -> balancer b-two-a-inbounds
```

Test:

```bash
python tests/lab_sender.py --host 127.0.0.1 --port 12203 --message "B -> two A inbounds" --count 10
```

Expected: colored output on `9101` and `9102`.

### Scenario 7: B forwards to A while one A inbound is disabled

Disable `a-to-9102`, apply A, sync runtime, then test B balancer again.

Expected: disabled endpoint should fail cleanly or be skipped. The panel runtime/drift should show the disabled/stale state clearly.

### Scenario 8: Change A inbound port or random/fixed mode after B points to it

Start with A inbound fixed or random, then B points to it via `node_inbound`. Test once. Then change A inbound:

```text
fixed 12101 -> fixed 12111
or
random -> fixed 12111
or
fixed -> random count=1
```

Apply A, sync runtime, then test B again.

Expected: B should use updated A runtime after sync. Old port should not be used after refresh.

## Stop everything

```bash
bash scripts/lab_stop_stack.sh
```
