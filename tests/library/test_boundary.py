"""Boundary guards for the shared Inepro library."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LIBRARY_ROOT = ROOT / "src" / "inepro_metering"


def test_shared_library_has_no_homeassistant_imports() -> None:
    """The reusable library layer must stay independent from Home Assistant."""
    violations: list[str] = []

    for path in sorted(LIBRARY_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        relative_path = path.relative_to(ROOT)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "homeassistant" or alias.name.startswith(
                        "homeassistant."
                    ):
                        violations.append(f"{relative_path}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module
                if module == "homeassistant" or (
                    module is not None and module.startswith("homeassistant.")
                ):
                    violations.append(f"{relative_path}: from {module} import ...")

    assert violations == []
