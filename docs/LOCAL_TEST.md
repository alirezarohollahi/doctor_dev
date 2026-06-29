# Local test

```powershell
Remove-Item -Recurse -Force .venv -ErrorAction SilentlyContinue
py -3.12 -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip wheel setuptools
pip install -r requirements.txt
python -m compileall doctor_dev_panel doctor_dev_node
python -m doctor_dev_panel.admin_cli add admin --password admin12345
python main.py --mode panel --env .env
```

For node tests, start two terminals with different `node-a.env` / `node-b.env`
and then add both nodes from the panel UI.


