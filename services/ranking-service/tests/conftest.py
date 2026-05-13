"""pytest needs the shared/ package on sys.path; in docker it's /app/shared/,
locally we add ../../_shared so `from shared.X import ...` works."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))  # services/, so `_shared` is importable
sys.path.insert(0, str(ROOT.parent / "_shared"))

# Re-export under the alias used in production: `shared`
import importlib

if "shared" not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        "shared", str(ROOT.parent / "_shared" / "__init__.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules["shared"] = module
    # Submodules
    for sub in ("logging", "events", "metrics", "settings", "rabbitmq"):
        sub_spec = importlib.util.spec_from_file_location(
            f"shared.{sub}", str(ROOT.parent / "_shared" / f"{sub}.py")
        )
        sub_mod = importlib.util.module_from_spec(sub_spec)
        sys.modules[f"shared.{sub}"] = sub_mod
        sub_spec.loader.exec_module(sub_mod)
