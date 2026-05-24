# Python 3.9 compatibility notes

This version supports Python 3.9.

Changes from the previous zip:

- Replaced Python 3.10 `A | B` union types with `typing.Union` and `typing.Optional`.
- Changed `requires-python` from `>=3.10` to `>=3.9`.
- Added upper bounds to dependencies so pip does not install future versions that may drop Python 3.9 support.
- Kept the same run command:

```bash
doctor-dev --env ./configs/gateway-node.env
```

If your virtualenv already installed the old package, reinstall with:

```bash
pip uninstall -y doctor-dev
pip install -e .
```

Or just run:

```bash
pip install -e . --force-reinstall
```
