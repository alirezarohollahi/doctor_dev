import importlib.util
import sys
from pathlib import Path


def load_common():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("install_common", root / "scripts" / "install_common.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["install_common"] = module
    spec.loader.exec_module(module)
    return module


def test_clean_input_removes_quotes_and_trailing_backslash():
    common = load_common()
    assert common.clean_input('  "/root/cert/privkey.pem\\"  ') == "/root/cert/privkey.pem"
    assert common.clean_input("'/root/cert/fullchain.pem'") == "/root/cert/fullchain.pem"


def test_normalize_existing_file_path_accepts_trailing_backslash(tmp_path):
    common = load_common()
    f = tmp_path / "privkey.pem"
    f.write_text("key", encoding="utf-8")
    assert common.normalize_existing_file_path(str(f) + "\\") == f.resolve()
