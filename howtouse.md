mkdir -p logs run
source .venv/bin/activate

nohup .venv/bin/python main.py \
  --env DocNodes/freedom-000-node/configs/freedom-000-node.env \
  > logs/freedom-000-node.out 2>&1 &

echo $! > run/freedom-000-node.pid


tail -f logs/freedom-000-node.out

kill "$(cat run/freedom-000-node.pid)"
rm -f run/freedom-000-node.pid


++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

mkdir -p logs run
source .venv/bin/activate

nohup .venv/bin/python main.py \
  --env DocNodes/freedom-001-node/configs/freedom-001-node.env \
  > logs/freedom-001-node.out 2>&1 &

echo $! > run/freedom-001-node.pid


tail -f logs/freedom-001-node.out

kill "$(cat run/freedom-001-node.pid)"
rm -f run/freedom-001-node.pid