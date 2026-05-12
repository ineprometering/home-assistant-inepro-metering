"""Tests for shared TCP gateway configuration definitions."""

from __future__ import annotations

import ipaddress

import pytest

from inepro_metering.const import TransportType
from inepro_metering.gateway_settings import (
    CONFIG_HOSTNAME_START,
    SETTINGS_APPLY,
    SETTINGS_REVERT,
    SETTINGS_STORE,
    build_gateway_setting_states,
    get_gateway_action,
    get_gateway_settings,
    supports_gateway_management,
)


def _encode_ipv4_words(value: str) -> tuple[int, int]:
    """Encode one IPv4 address into the vendor high/low word layout."""
    address = int(ipaddress.IPv4Address(value))
    return ((address >> 16) & 0xFFFF, address & 0xFFFF)


def test_gateway_settings_expose_confirmed_platforms_only() -> None:
    """Only confirmed gateway settings should be exposed through the shared model."""
    assert [setting.key for setting in get_gateway_settings(entity_platform="switch")] == [
        "dhcp_enabled",
        "ntp_enabled",
    ]
    assert [setting.key for setting in get_gateway_settings(entity_platform="select")] == [
        "modbus_port",
        "baudrate",
        "parity",
    ]
    assert [setting.key for setting in get_gateway_settings(entity_platform="number")] == [
        "timeout_ms",
    ]
    assert [setting.key for setting in get_gateway_settings(entity_platform="text")] == [
        "ip_address",
        "netmask",
        "default_gateway",
        "dns_server_1",
        "dns_server_2",
        "ntp_server_1",
        "ntp_server_2",
        "host_name",
    ]
    assert "frame_delay" not in [setting.key for setting in get_gateway_settings()]


def test_gateway_text_settings_validate_ipv4_and_hostname_before_write() -> None:
    """Gateway text writes should reject invalid IPv4 and conservative hostnames."""
    ip_setting = next(
        setting for setting in get_gateway_settings(entity_platform="text") if setting.key == "ip_address"
    )
    host_name_setting = next(
        setting for setting in get_gateway_settings(entity_platform="text") if setting.key == "host_name"
    )

    ip_write = ip_setting.build_writes("192.0.2.44")[0]
    assert ip_write.values == _encode_ipv4_words("192.0.2.44")

    with pytest.raises(ValueError, match="IP address must be a valid IPv4 address"):
        ip_setting.build_writes("999.0.2.44")

    host_name_write = host_name_setting.build_writes("GATEWAY-01")[0]
    assert host_name_write.address == CONFIG_HOSTNAME_START

    with pytest.raises(ValueError, match="Host name must not be empty"):
        host_name_setting.build_writes("")

    with pytest.raises(
        ValueError,
        match="Host name may only contain ASCII letters, numbers, or hyphens",
    ):
        host_name_setting.build_writes("gateway.local")


def test_gateway_action_write_plans_keep_confirmed_sequence() -> None:
    """Gateway actions should preserve the confirmed apply, store, and revert order."""
    revert = get_gateway_action("revert")
    apply = get_gateway_action("apply")
    apply_and_store = get_gateway_action("apply_and_store")

    assert [write.address for write in revert.build_writes()] == [SETTINGS_REVERT]
    assert [write.address for write in apply.build_writes()] == [SETTINGS_APPLY]
    assert [write.address for write in apply_and_store.build_writes()] == [
        SETTINGS_STORE,
        SETTINGS_APPLY,
    ]


def test_gateway_runtime_state_builder_uses_decoded_gateway_readings() -> None:
    """Gateway runtime states should decode shared readings into logical values."""
    states = build_gateway_setting_states(
        {
            "tcp_gateway_dhcp_enabled": True,
            "tcp_gateway_ip_address": "192.0.2.10",
            "tcp_gateway_modbus_port": "RS485",
            "tcp_gateway_baudrate": "9600",
            "tcp_gateway_parity": "EVEN",
            "tcp_gateway_timeout_ms": 500,
            "tcp_gateway_host_name": "GATEWAY-01",
        }
    )

    assert states["dhcp_enabled"].value is True
    assert states["ip_address"].value == "192.0.2.10"
    assert states["modbus_port"].value == "RS485"
    assert states["baudrate"].value == "9600"
    assert states["parity"].value == "EVEN"
    assert states["timeout_ms"].value == 500.0
    assert states["host_name"].value == "GATEWAY-01"


def test_gateway_support_check_only_matches_gateway_routes() -> None:
    """Only Modbus TCP gateway routes should expose gateway management features."""
    assert supports_gateway_management(TransportType.TCP_GATEWAY) is True
    assert supports_gateway_management(TransportType.SERIAL) is False
    assert supports_gateway_management(TransportType.TCP_WIFI) is False
