"""Load the integration's HA-free modules without importing Home Assistant.

``custom_components/winet/__init__.py`` pulls in Home Assistant, so the package cannot
be imported directly in a bare test environment. ``const.py`` and ``model.py``
deliberately have no HA dependencies, so we load just those two under a synthetic
package name.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

SOURCE_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "winet"
PACKAGE = "winet_pure"

_package = types.ModuleType(PACKAGE)
_package.__path__ = [str(SOURCE_DIR)]
sys.modules[PACKAGE] = _package

for _name in ("const", "model"):
    _spec = importlib.util.spec_from_file_location(
        f"{PACKAGE}.{_name}", SOURCE_DIR / f"{_name}.py"
    )
    assert _spec is not None and _spec.loader is not None
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[f"{PACKAGE}.{_name}"] = _module
    _spec.loader.exec_module(_module)
