from pathlib import Path
import py_compile


def test_deploy_compile_targets_are_valid_python():
    root = Path(__file__).resolve().parents[1]
    py_compile.compile(str(root / "app.py"), doraise=True)
    py_compile.compile(str(root / "abs_service.py"), doraise=True)
