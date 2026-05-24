# Running doctor_dev on 3 servers

Topology:

```text
Iran-Node --> Gateway-Node --> Forigen-Node
```

> The user-requested spelling `Forigen` is preserved in config and group names.

## 1. Replace placeholders

Edit these files on the matching servers:

- `configs/forigen-node.json`
- `configs/gateway-node.json`
- `configs/iran-node.json`

Replace:

```text
FORIGEN_NODE_PUBLIC_IP_OR_DNS
GATEWAY_NODE_PUBLIC_IP_OR_DNS
IRAN_NODE_PUBLIC_IP_OR_DNS
CHANGE_ME_SECRET_TOKEN
```

Use the same token wherever one manager calls another manager, or use different tokens and configure them correctly.

## 2. Open firewall ports

Open manager API ports:

```text
Iran-Node:    TCP 7001
Gateway-Node: TCP 7002
Forigen-Node: TCP 7003
```

Also open the random inbound forwarding ports. Because ports are random, the simple test setup needs a wide range open between nodes. For production, use fixed ports or a limited random range feature.

Minimum traffic direction:

```text
Iran clients -> Iran-Node random group ports
Iran-Node    -> Gateway-Node random group ports
Gateway-Node -> Forigen-Node random group ports
Forigen-Node -> 127.0.0.1:10000, 10001, 10002, 9999
```

## 3. Install on each server

```bash
unzip doctor_dev.zip
cd doctor_dev
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## 4. Start Forigen-Node first

On Forigen-Node:

```bash
source .venv/bin/activate
./scripts/run-forigen-node.sh
```

Check:

```bash
doctor-devctl --manager http://127.0.0.1:7003 --token CHANGE_ME_SECRET_TOKEN status
doctor-devctl --manager http://127.0.0.1:7003 --token CHANGE_ME_SECRET_TOKEN inbounds Forigen-Node-Group-1
```

Forigen groups:

```text
Forigen-Node-Group-1   -> 3 processes -> 127.0.0.1:10000
Forigen-Node-Group-2   -> 3 processes -> 127.0.0.1:10001
Forigen-Node-Group-3   -> 3 processes -> 127.0.0.1:10002
Forigen-Node-Group-Sub -> 1 process  -> 127.0.0.1:9999
```

## 5. Start Gateway-Node second

On Gateway-Node:

```bash
source .venv/bin/activate
./scripts/run-gateway-node.sh
```

Force sync once:

```bash
doctor-devctl --manager http://127.0.0.1:7002 --token CHANGE_ME_SECRET_TOKEN sync
```

Check:

```bash
doctor-devctl --manager http://127.0.0.1:7002 --token CHANGE_ME_SECRET_TOKEN status
doctor-devctl --manager http://127.0.0.1:7002 --token CHANGE_ME_SECRET_TOKEN inbounds Gateway-Node-Group-1
```

Gateway groups:

```text
Gateway-Node-Group-1   -> 4 processes -> Forigen-Node-Group-1 inbounds
Gateway-Node-Group-2   -> 3 processes -> Forigen-Node-Group-2 inbounds
Gateway-Node-Group-3   -> 3 processes -> Forigen-Node-Group-3 inbounds
Gateway-Node-Group-Sub -> 1 process  -> Forigen-Node-Group-Sub inbounds
```

## 6. Start Iran-Node third

On Iran-Node:

```bash
source .venv/bin/activate
./scripts/run-iran-node.sh
```

Force sync once:

```bash
doctor-devctl --manager http://127.0.0.1:7001 --token CHANGE_ME_SECRET_TOKEN sync
```

Check:

```bash
doctor-devctl --manager http://127.0.0.1:7001 --token CHANGE_ME_SECRET_TOKEN status
doctor-devctl --manager http://127.0.0.1:7001 --token CHANGE_ME_SECRET_TOKEN inbounds Iran-Node-Group-1
```

Iran groups:

```text
Iran-Node-Group-1   -> 3 processes -> Gateway-Node-Group-1 inbounds
Iran-Node-Group-2   -> 4 processes -> Gateway-Node-Group-2 inbounds
Iran-Node-Group-3   -> 5 processes -> Gateway-Node-Group-3 inbounds
Iran-Node-Group-Sub -> 1 process  -> Gateway-Node-Group-Sub inbounds
```

## 7. What happens after restart?

When a manager starts:

1. It loads JSON config.
2. It loads runtime state.
3. It tries to reuse previous random ports.
4. If a previous port is not free, it allocates a new one.
5. It publishes current inbounds through REST.
6. Upstream managers poll dependencies every 10 seconds.
7. If remote inbounds changed, affected local groups restart and point to the new targets.

Example:

```text
Gateway-Node restarts
Gateway random ports may change
Iran-Node polls Gateway REST API
Iran-Node detects changed Gateway-Node-Group-* inbounds
Iran-Node restarts affected Iran groups automatically
```

## 8. Testing with netcat

On Forigen-Node, start a simple echo-like test service for port 9999:

```bash
while true; do nc -l -p 9999 -c 'cat'; done
```

Then on a client that can reach Iran-Node, get the sub group inbound:

```bash
doctor-devctl --manager http://IRAN_NODE_PUBLIC_IP_OR_DNS:7001 --token CHANGE_ME_SECRET_TOKEN inbounds Iran-Node-Group-Sub
```

Connect to the returned Iran inbound port:

```bash
nc IRAN_NODE_PUBLIC_IP_OR_DNS RETURNED_PORT
```

Anything typed should travel:

```text
client -> Iran-Node-Group-Sub -> Gateway-Node-Group-Sub -> Forigen-Node-Group-Sub -> 127.0.0.1:9999
```

## 9. Production recommendations

- Use real firewall rules.
- Use strong API tokens.
- Put the manager API behind VPN/private networking if possible.
- Consider fixed ports or a limited port range instead of fully random ports.
- Run with systemd or Docker.
- Monitor logs under `./logs/`.
