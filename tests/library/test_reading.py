"""Tests for register grouping and decoding helpers."""

from __future__ import annotations

import struct

from inepro_metering.const import MeterFamily
from inepro_metering.models import get_profile
from inepro_metering.reading import build_register_blocks, decode_sensor_value


def _float_registers(value: float) -> list[int]:
    """Encode a float into two big-endian Modbus registers."""
    packed = struct.pack(">f", value)
    return list(struct.unpack(">HH", packed))


def _uint32_registers(value: int) -> list[int]:
    """Encode a uint32 into two big-endian Modbus registers."""
    packed = struct.pack(">I", value)
    return list(struct.unpack(">HH", packed))


def test_build_register_blocks_preserves_sensor_coverage() -> None:
    """Register grouping should cover all defined sensors."""
    profile = get_profile(MeterFamily.GROW, "grow_850")
    blocks = build_register_blocks(profile.measurement_sensors)

    covered_keys = {
        sensor.key
        for block in blocks
        for sensor in block.sensors
    }

    assert covered_keys == {sensor.key for sensor in profile.measurement_sensors}


def test_decode_float_sensor_value() -> None:
    """Float register values should decode with rounding."""
    profile = get_profile(MeterFamily.GROW, "grow_850")
    sensor = next(
        description
        for description in profile.measurement_sensors
        if description.key == "total_active_power"
    )

    assert decode_sensor_value(sensor, _float_registers(3.2461)) == 3.246


def test_decode_scaled_energy_sensor_value() -> None:
    """Raw Wh register values should scale to kWh."""
    profile = get_profile(MeterFamily.GROW, "grow_850")
    sensor = next(
        description
        for description in profile.measurement_sensors
        if description.key == "forward_active_energy"
    )

    assert decode_sensor_value(sensor, _uint32_registers(12345)) == 12.345


def test_decode_bcd_diagnostic_value() -> None:
    """BCD-backed diagnostic values should preserve leading zeroes."""
    profile = get_profile(MeterFamily.GROW, "grow_850")
    sensor = next(
        description
        for description in profile.diagnostic_sensors
        if description.key == "product_code"
    )

    assert decode_sensor_value(sensor, [0x0701]) == "0701"


def test_decode_option_mapped_diagnostic_value() -> None:
    """Enum-like diagnostics should map raw values to human-readable states."""
    profile = get_profile(MeterFamily.GROW, "grow_701")
    sensor = next(
        description
        for description in profile.diagnostic_sensors
        if description.key == "wifi_support"
    )

    assert decode_sensor_value(sensor, [1]) == "enabled"


def test_decode_pro_float_energy_sensor_value() -> None:
    """PRO energy registers should decode directly from Float ABCD kWh values."""
    profile = get_profile(MeterFamily.PRO, "pro_380")
    sensor = next(
        description
        for description in profile.measurement_sensors
        if description.key == "forward_active_energy"
    )

    assert decode_sensor_value(sensor, _float_registers(1234.567)) == 1234.567


def test_decode_pro_hex_serial_value() -> None:
    """PRO serial numbers should preserve the raw HEX32 register payload."""
    profile = get_profile(MeterFamily.PRO, "pro_380")
    sensor = next(
        description
        for description in profile.diagnostic_sensors
        if description.key == "serial_number"
    )

    assert decode_sensor_value(sensor, [0x1234, 0x5678]) == "12345678"
