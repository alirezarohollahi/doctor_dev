
# Doctor Dev Lab Routing Test Guide

This guide is for manual routing tests with:

- Panel: `9000`
- Node A: `9001`
- Node B: `9002`
- Lab listeners: `9101`, `9102`, `9103`, `9104`

## Important TCP-balancer rule

Doctor Dev chooses the balancer target **per TCP connection**, not per individual payload inside the same connection.

So if you use one persistent TCP connection and send 20 messages, all 20 messages are expected to reach the same backend port.

Use the lab sender default mode, which opens one connection per message:

```bash
python tests/lab_sender.py --host 127.0.0.1 --port 1201 --message "round-robin" --count 12
```

For a single persistent connection test:

```bash
python tests/lab_sender.py --host 127.0.0.1 --port 1201 --message "persistent" --count 12 --mode persistent
```

For `least_connections`, use concurrent mode:

```bash
python tests/lab_sender.py --host 127.0.0.1 --port 1201 --message "least" --count 12 --mode concurrent --hold 5
```

## Listener

```bash
python tests/lab_multi_listener.py --host 127.0.0.1 --ports 9101,9102,9103,9104
```

## Scenario 1: A direct to one listener

Example:

- Node A inbound fixed port: `1201`
- Target type: `static`
- Target host: `127.0.0.1`
- Target port: `9101`

Send:

```bash
python tests/lab_sender.py --host 127.0.0.1 --port 1201 --message "scenario-1 direct" --count 5
```

Expected: only listener `9101` receives data.

## Scenario 2: A to four listeners through balancer

Keep the same inbound port if you want, for example `1201`, but change the inbound target to balancer.

Balancer:

- Alias: `a-lab-4-static`
- Endpoints:
  - static `127.0.0.1:9101`
  - static `127.0.0.1:9102`
  - static `127.0.0.1:9103`
  - static `127.0.0.1:9104`

Inbound:

- Fixed port: `1201`
- Target type: `balancer`
- Target balancer: `a-lab-4-static`

### round_robin

Set strategy to `round_robin`, apply config, sync runtime, then:

```bash
python tests/lab_sender.py --host 127.0.0.1 --port 1201 --message "scenario-2 round-robin" --count 12 --interval 0.15
```

Expected: connections rotate across `9101`, `9102`, `9103`, `9104` according to the endpoint order stored in runtime.

### random

Set strategy to `random`, apply config, sync runtime, then:

```bash
python tests/lab_sender.py --host 127.0.0.1 --port 1201 --message "scenario-2 random" --count 20 --interval 0.1
```

Expected: multiple listener ports receive data in non-deterministic order.

### failover

Set strategy to `failover`, apply config, sync runtime, then:

```bash
python tests/lab_sender.py --host 127.0.0.1 --port 1201 --message "scenario-2 failover" --count 8 --interval 0.15
```

Expected: all connections go to the first enabled reachable endpoint in the runtime endpoint order. If the first endpoint in your stored order is `9102`, then `9102` is the correct failover target.

Check endpoint order from runtime:

```bash
curl -s -H "Authorization: Bearer lab-node-a-key-11111111-1111-1111-1111-111111111111" \
  http://127.0.0.1:9001/runtime | python -m json.tool
```

### least_connections

Set strategy to `least_connections`, apply config, sync runtime, then:

```bash
python tests/lab_sender.py --host 127.0.0.1 --port 1201 --message "scenario-2 least" --count 12 --mode concurrent --hold 5
```

Expected: concurrent connections should spread across endpoints.

## Diagnostics

Check Node A runtime:

```bash
curl -s -H "Authorization: Bearer lab-node-a-key-11111111-1111-1111-1111-111111111111" \
  http://127.0.0.1:9001/runtime | python -m json.tool
```

Check listener port:

```bash
ss -lntp | egrep '1201|9101|9102|9103|9104'
```



