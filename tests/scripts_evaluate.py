"""Loads scripts/evaluate.py under another module name, because on some machines another
installed package is called `scripts` (see the Week 4 seed fix)."""
import importlib.util
from pathlib import Path

_path = Path(__file__).resolve().parent.parent / "scripts" / "evaluate.py"
_spec = importlib.util.spec_from_file_location("instakill_evaluate_script", _path)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
main = _module.main
