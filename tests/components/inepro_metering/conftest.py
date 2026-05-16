"""Define fixtures available for inepro Metering tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def mock_bluetooth(enable_bluetooth: None) -> None:
    """Auto mock Bluetooth."""


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integration loading for all inepro Metering tests."""
    del enable_custom_integrations
