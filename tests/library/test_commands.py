"""Tests for shared Inepro Metering write commands."""

from inepro_metering.commands import (
    WIFI_APPLY_ADDRESS,
    WIFI_ENABLE_ADDRESS,
    WIFI_PASSWORD_ADDRESS,
    WIFI_SSID_ADDRESS,
    build_wifi_credential_writes,
    encode_ascii_registers,
)


def test_build_wifi_credential_writes_preserves_confirmed_write_order() -> None:
    """Wi-Fi credential writes should keep the confirmed device write sequence."""
    writes = build_wifi_credential_writes("OfficeNet", "s3cret", apply=True)

    assert [write.address for write in writes] == [
        WIFI_ENABLE_ADDRESS,
        WIFI_SSID_ADDRESS,
        WIFI_PASSWORD_ADDRESS,
        WIFI_APPLY_ADDRESS,
    ]
    assert writes[0].multiple is False
    assert writes[0].values == (1,)
    assert writes[1].values[:5] == encode_ascii_registers(
        "OfficeNet",
        register_count=16,
        field_name="SSID",
        allow_empty=False,
    )[:5]


def test_encode_ascii_registers_validates_ascii_and_length() -> None:
    """ASCII write fields should reject unsupported characters and oversize inputs."""
    assert encode_ascii_registers(
        "AB",
        register_count=2,
        field_name="Test",
    ) == (0x4142, 0x0000)

    try:
        encode_ascii_registers("naive-ä", register_count=8, field_name="SSID")
    except ValueError as err:
        assert str(err) == "SSID must contain ASCII characters only"
    else:
        raise AssertionError("Expected non-ASCII SSID to be rejected")

    try:
        encode_ascii_registers("toolong", register_count=2, field_name="SSID")
    except ValueError as err:
        assert str(err) == "SSID must be 4 ASCII characters or fewer"
    else:
        raise AssertionError("Expected oversize SSID to be rejected")
