import importlib.util
import sys
from pathlib import Path


def test_linux_installer_files_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / "scripts" / "install_panel.py").exists()
    assert (root / "scripts" / "install_node.py").exists()
    assert (root / "scripts" / "doctor_dev.sh").exists()


def test_common_installer_importable():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("install_common", root / "scripts" / "install_common.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["install_common"] = module
    spec.loader.exec_module(module)
    assert module.REPO_URL.endswith("doctor_dev")
