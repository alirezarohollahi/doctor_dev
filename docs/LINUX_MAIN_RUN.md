
# Run Doctor Dev with main.py on Linux

## Install

```bash
cd /home/TestDocDev
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install --no-cache-dir --only-binary=:all: -r requirements.txt
python -m compileall doctor_dev_panel doctor_dev_node main.py
```

## Create admin

```bash
DOCTOR_DEV_ENV=env.examples/panel.env python -m doctor_dev_panel.admin_cli add admin --password 'admin12345'
```

## Run panel

```bash
python main.py --mode panel --env env.examples/panel.env --host 0.0.0.0 --port 8080
```

## Run node

```bash
python main.py --mode node --env env.examples/node.env --host 0.0.0.0 --port 62051
```

## Test node

```bash
curl http://127.0.0.1:62051/health
curl -H 'Authorization: Bearer 11111111-1111-1111-1111-111111111111' http://127.0.0.1:62051/runtime
```



