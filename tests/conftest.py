"""Pytest shims for local Windows execution."""

from __future__ import annotations

import sys

import pytest
import pytest_socket


@pytest.fixture(autouse=True)
def mock_bluetooth_adapters_dependency(monkeypatch):
    """Avoid starting the host Bluetooth stack while loading test config flows."""

    from homeassistant import setup as ha_setup

    original_async_setup_component = ha_setup.async_setup_component

    async def async_setup_component(hass, domain, config):
        if domain == "bluetooth_adapters":
            hass.config.components.add(domain)
            return True
        return await original_async_setup_component(hass, domain, config)

    monkeypatch.setattr(ha_setup, "async_setup_component", async_setup_component)


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_fixture_setup(fixturedef, request):
    """Allow Windows asyncio loop creation under pytest_socket.

    The Home Assistant pytest plugin disables ``socket.socket`` during test setup.
    On Unix, asyncio can still create its self-pipe via ``AF_UNIX``. On Windows,
    loop creation falls back to regular sockets, so the socket ban crashes the
    event loop before the test body even starts.

    We keep the restriction in place for normal test execution and only re-enable
    sockets while pytest-asyncio is constructing an ``event_loop`` or
    ``_session_event_loop`` fixture.
    """

    needs_socket = sys.platform == "win32" and fixturedef.argname in {
        "event_loop",
        "_session_event_loop",
    }
    if needs_socket:
        pytest_socket.enable_socket()
    outcome = yield
    if needs_socket:
        pytest_socket.socket_allow_hosts(["127.0.0.1"])
        pytest_socket.disable_socket(allow_unix_socket=True)
