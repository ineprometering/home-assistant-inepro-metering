"""Tests for GROW Wi-Fi provisioning helpers."""

from __future__ import annotations

import pytest

from inepro_metering.wifi import (
    WIFI_APPLY_ADDRESS,
    WIFI_APPLY_VALUE,
    WIFI_ENABLE_ADDRESS,
    WIFI_ENABLE_VALUE,
    WIFI_PASSWORD_ADDRESS,
    WIFI_PASSWORD_REGISTER_COUNT,
    WIFI_SSID_ADDRESS,
    WIFI_SSID_REGISTER_COUNT,
    build_wifi_credential_writes,
    encode_ascii_registers,
)


def test_encode_ascii_registers_pads_big_endian_words() -> None:
    """ASCII text should be packed into big-endian 16-bit Modbus registers."""
    registers = encode_ascii_registers(
        "Inepro",
        register_count=4,
        field_name="SSID",
    )

    assert registers == (0x496E, 0x6570, 0x726F, 0x0000)


def test_encode_ascii_registers_rejects_non_ascii() -> None:
    """The GROW Wi-Fi fields are ASCII binary fields."""
    with pytest.raises(ValueError, match="ASCII"):
        encode_ascii_registers("caf\u00e9", register_count=4, field_name="SSID")


def test_encode_ascii_registers_rejects_overlength_value() -> None:
    """Values must fit into the fixed register block."""
    with pytest.raises(ValueError, match="4 ASCII characters or fewer"):
        encode_ascii_registers("ABCDE", register_count=2, field_name="SSID")


def test_build_wifi_credential_writes_uses_confirmed_grow_registers() -> None:
    """Credential writes should follow the confirmed GROW register map."""
    writes = build_wifi_credential_writes("Inepro", "secret")

    assert writes[0].address == WIFI_ENABLE_ADDRESS
    assert writes[0].values == (WIFI_ENABLE_VALUE,)
    assert writes[0].multiple is False
    assert writes[1].address == WIFI_SSID_ADDRESS
    assert len(writes[1].values) == WIFI_SSID_REGISTER_COUNT
    assert writes[1].values[:3] == (0x496E, 0x6570, 0x726F)
    assert writes[1].multiple is True
    assert writes[2].address == WIFI_PASSWORD_ADDRESS
    assert len(writes[2].values) == WIFI_PASSWORD_REGISTER_COUNT
    assert writes[2].values[:3] == (0x7365, 0x6372, 0x6574)
    assert writes[2].multiple is True
    assert writes[3].address == WIFI_APPLY_ADDRESS
    assert writes[3].values == (WIFI_APPLY_VALUE,)
    assert writes[3].multiple is True


def test_build_wifi_credential_writes_can_skip_apply_command() -> None:
    """The apply command can be skipped when staging credentials."""
    writes = build_wifi_credential_writes("Inepro", "secret", apply=False)

    assert [write.address for write in writes] == [
        WIFI_ENABLE_ADDRESS,
        WIFI_SSID_ADDRESS,
        WIFI_PASSWORD_ADDRESS,
    ]
