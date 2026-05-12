"""Tests for packaging and dependency consistency."""

from __future__ import annotations

import json
from pathlib import Path
import re
import tomllib


ROOT = Path(__file__).resolve().parents[2]


def test_manifest_version_matches_pyproject() -> None:
    """The custom component and shared library should ship the same version."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    manifest = json.loads(
        (ROOT / "custom_components/inepro_metering/manifest.json").read_text(
            encoding="utf-8"
        )
    )
    init_py = (ROOT / "src/inepro_metering/__init__.py").read_text(encoding="utf-8")
    fallback_version = re.search(r'__version__ = "([^"]+)"', init_py)

    assert fallback_version is not None
    # The custom integration version is intentionally aligned while this repo is
    # shipped as a custom distribution package stack.
    assert (
        pyproject["project"]["version"]
        == manifest["version"]
        == fallback_version.group(1)
    )


def test_manifest_requirements_match_shared_library_dependencies() -> None:
    """Documented runtime dependencies should stay aligned between package layers."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    manifest = json.loads(
        (ROOT / "custom_components/inepro_metering/manifest.json").read_text(
            encoding="utf-8"
        )
    )

    package_requirement = (
        f"{pyproject['project']['name']}=={pyproject['project']['version']}"
    )
    expected_requirements = {
        package_requirement,
        *pyproject["project"]["dependencies"],
    }

    assert pyproject["project"]["name"] == "inepro-metering"
    assert set(manifest["requirements"]) == expected_requirements


def test_manifest_metadata_matches_current_custom_submission_path() -> None:
    """Submission-facing manifest metadata should be explicit and self-consistent."""
    manifest = json.loads(
        (ROOT / "custom_components/inepro_metering/manifest.json").read_text(
            encoding="utf-8"
        )
    )

    assert manifest["domain"] == "inepro_metering"
    assert manifest["name"] == "inepro Metering"
    assert manifest["config_flow"] is True
    assert manifest["integration_type"] == "hub"
    assert manifest["iot_class"] == "local_polling"
    assert manifest["codeowners"] == ["@ineprometering"]
    assert (
        manifest["documentation"]
        == "https://github.com/ineprometering/home-assistant-inepro-metering#readme"
    )
    assert (
        manifest["issue_tracker"]
        == "https://github.com/ineprometering/home-assistant-inepro-metering/issues"
    )
    assert manifest["dependencies"] == ["bluetooth_adapters"]


def test_test_extra_includes_pytest_socket() -> None:
    """The canonical test extra should install pytest-socket for conftest imports."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    test_dependencies = pyproject["project"]["optional-dependencies"]["test"]

    assert any(
        dependency.startswith("pytest-socket") for dependency in test_dependencies
    )
