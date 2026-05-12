"""Schema audit for implemented Inepro register definitions."""

from __future__ import annotations

from inepro_metering.const import MeterFamily
from inepro_metering.models import (
    PROFILES_BY_FAMILY,
    MeterSensorDescription,
    RegisterFormatType,
    RegisterValueType,
)


def _implemented_family_sensors_by_address(
    family: MeterFamily,
) -> dict[int, MeterSensorDescription]:
    """Return one unique implemented sensor description per register address."""
    sensors: dict[int, MeterSensorDescription] = {}
    for profile in PROFILES_BY_FAMILY[family].values():
        for sensor in profile.all_sensors:
            sensors.setdefault(sensor.address, sensor)
    return sensors


def test_implemented_grow_register_schema_matches_grow_map() -> None:
    """Implemented GROW registers should keep the agreed raw length/type/format metadata."""
    expected = {
        0x1010: ("billing_session_start_energy", 2, RegisterValueType.INT32, "Wh", RegisterFormatType.DEC),
        0x1012: ("billing_session_accumulated_energy", 2, RegisterValueType.INT32, "Wh", RegisterFormatType.DEC),
        0x1100: ("billing_session_status", 1, RegisterValueType.UINT16, None, RegisterFormatType.DEC),
        0x4000: ("serial_number", 2, RegisterValueType.BCD32, None, RegisterFormatType.HEX),
        0x4002: ("meter_code", 1, RegisterValueType.HEX16, None, RegisterFormatType.HEX),
        0x4005: ("legal_software_version", 2, RegisterValueType.FLOAT32, None, RegisterFormatType.FLOAT),
        0x4007: ("non_legal_software_version", 2, RegisterValueType.FLOAT32, None, RegisterFormatType.FLOAT),
        0x4009: ("hardware_version", 2, RegisterValueType.FLOAT32, None, RegisterFormatType.FLOAT),
        0x4010: ("legal_lcd_cycle_time", 1, RegisterValueType.UINT16, "seconds", RegisterFormatType.DEC),
        0x4015: ("error_code", 1, RegisterValueType.HEX16, None, RegisterFormatType.HEX),
        0x401B: ("legal_software_crc", 2, RegisterValueType.HEX32, None, RegisterFormatType.HEX),
        0x401D: ("active_status_word", 2, RegisterValueType.HEX32, None, RegisterFormatType.HEX),
        0x4023: ("non_legal_software_crc", 2, RegisterValueType.HEX32, None, RegisterFormatType.HEX),
        0x4025: ("product_code", 1, RegisterValueType.BCD16, None, RegisterFormatType.HEX),
        0x4032: ("lcd_orientation", 1, RegisterValueType.UINT16, None, RegisterFormatType.ENUM),
        0x4033: ("non_legal_lcd_obis_codes", 1, RegisterValueType.UINT16, None, RegisterFormatType.ENUM),
        0x4171: ("backlight_level", 1, RegisterValueType.UINT16, "%", RegisterFormatType.DEC),
        0x4C00: ("legal_lcd_obis_codes", 1, RegisterValueType.UINT16, None, RegisterFormatType.ENUM),
        0x4C01: ("legal_lcd_tariff_mode", 1, RegisterValueType.UINT16, None, RegisterFormatType.ENUM),
        0x4C02: ("backlight_mode", 1, RegisterValueType.UINT16, None, RegisterFormatType.ENUM),
        0x4C04: ("backlight_timeout", 1, RegisterValueType.UINT16, "minutes", RegisterFormatType.DEC),
        0x4C05: ("non_legal_lcd_cycle_time", 1, RegisterValueType.UINT16, "seconds", RegisterFormatType.DEC),
        0x4C06: ("wifi_support", 1, RegisterValueType.UINT16, None, RegisterFormatType.ENUM),
        0x4C07: ("bluetooth_mode", 1, RegisterValueType.UINT16, None, RegisterFormatType.ENUM),
        0x4C64: ("ethernet_support", 1, RegisterValueType.UINT16, None, RegisterFormatType.ENUM),
        0x5000: ("average_voltage_ln", 2, RegisterValueType.FLOAT32, "V", RegisterFormatType.FLOAT),
        0x5002: ("voltage_l1", 2, RegisterValueType.FLOAT32, "V", RegisterFormatType.FLOAT),
        0x5004: ("voltage_l2", 2, RegisterValueType.FLOAT32, "V", RegisterFormatType.FLOAT),
        0x5006: ("voltage_l3", 2, RegisterValueType.FLOAT32, "V", RegisterFormatType.FLOAT),
        0x5008: ("grid_frequency", 2, RegisterValueType.FLOAT32, "Hz", RegisterFormatType.FLOAT),
        0x500A: ("total_current", 2, RegisterValueType.FLOAT32, "A", RegisterFormatType.FLOAT),
        0x500C: ("current_l1", 2, RegisterValueType.FLOAT32, "A", RegisterFormatType.FLOAT),
        0x500E: ("current_l2", 2, RegisterValueType.FLOAT32, "A", RegisterFormatType.FLOAT),
        0x5010: ("current_l3", 2, RegisterValueType.FLOAT32, "A", RegisterFormatType.FLOAT),
        0x5012: ("total_active_power", 2, RegisterValueType.FLOAT32, "kW", RegisterFormatType.FLOAT),
        0x5014: ("active_power_l1", 2, RegisterValueType.FLOAT32, "kW", RegisterFormatType.FLOAT),
        0x5016: ("active_power_l2", 2, RegisterValueType.FLOAT32, "kW", RegisterFormatType.FLOAT),
        0x5018: ("active_power_l3", 2, RegisterValueType.FLOAT32, "kW", RegisterFormatType.FLOAT),
        0x501A: ("total_reactive_power", 2, RegisterValueType.FLOAT32, "kvar", RegisterFormatType.FLOAT),
        0x501C: ("reactive_power_l1", 2, RegisterValueType.FLOAT32, "kvar", RegisterFormatType.FLOAT),
        0x501E: ("reactive_power_l2", 2, RegisterValueType.FLOAT32, "kvar", RegisterFormatType.FLOAT),
        0x5020: ("reactive_power_l3", 2, RegisterValueType.FLOAT32, "kvar", RegisterFormatType.FLOAT),
        0x5022: ("total_apparent_power", 2, RegisterValueType.FLOAT32, "kVA", RegisterFormatType.FLOAT),
        0x5024: ("apparent_power_l1", 2, RegisterValueType.FLOAT32, "kVA", RegisterFormatType.FLOAT),
        0x5026: ("apparent_power_l2", 2, RegisterValueType.FLOAT32, "kVA", RegisterFormatType.FLOAT),
        0x5028: ("apparent_power_l3", 2, RegisterValueType.FLOAT32, "kVA", RegisterFormatType.FLOAT),
        0x502A: ("total_power_factor", 2, RegisterValueType.FLOAT32, None, RegisterFormatType.FLOAT),
        0x502C: ("power_factor_l1", 2, RegisterValueType.FLOAT32, None, RegisterFormatType.FLOAT),
        0x502E: ("power_factor_l2", 2, RegisterValueType.FLOAT32, None, RegisterFormatType.FLOAT),
        0x5030: ("power_factor_l3", 2, RegisterValueType.FLOAT32, None, RegisterFormatType.FLOAT),
        0x5032: ("voltage_l1_l2", 2, RegisterValueType.FLOAT32, "V", RegisterFormatType.FLOAT),
        0x5034: ("voltage_l1_l3", 2, RegisterValueType.FLOAT32, "V", RegisterFormatType.FLOAT),
        0x5036: ("voltage_l2_l3", 2, RegisterValueType.FLOAT32, "V", RegisterFormatType.FLOAT),
        0x5038: ("average_voltage_ll", 2, RegisterValueType.FLOAT32, "V", RegisterFormatType.FLOAT),
        0x503A: ("neutral_current", 2, RegisterValueType.FLOAT32, "A", RegisterFormatType.FLOAT),
        0x503C: ("temperature", 2, RegisterValueType.FLOAT32, "°C", RegisterFormatType.FLOAT),
        0x503E: ("voltage_l1_thd", 2, RegisterValueType.FLOAT32, "%", RegisterFormatType.FLOAT),
        0x5040: ("voltage_l2_thd", 2, RegisterValueType.FLOAT32, "%", RegisterFormatType.FLOAT),
        0x5042: ("voltage_l3_thd", 2, RegisterValueType.FLOAT32, "%", RegisterFormatType.FLOAT),
        0x5044: ("current_l1_thd", 2, RegisterValueType.FLOAT32, "%", RegisterFormatType.FLOAT),
        0x5046: ("current_l2_thd", 2, RegisterValueType.FLOAT32, "%", RegisterFormatType.FLOAT),
        0x5048: ("current_l3_thd", 2, RegisterValueType.FLOAT32, "%", RegisterFormatType.FLOAT),
        0x504A: ("average_voltage_thd", 2, RegisterValueType.FLOAT32, "%", RegisterFormatType.FLOAT),
        0x504C: ("average_current_thd", 2, RegisterValueType.FLOAT32, "%", RegisterFormatType.FLOAT),
        0x6000: ("total_active_energy", 2, RegisterValueType.INT32, "Wh", RegisterFormatType.DEC),
        0x600C: ("forward_active_energy", 2, RegisterValueType.UINT32, "Wh", RegisterFormatType.DEC),
        0x6018: ("reverse_active_energy", 2, RegisterValueType.UINT32, "Wh", RegisterFormatType.DEC),
        0x6030: ("forward_reactive_energy", 2, RegisterValueType.UINT32, "varh", RegisterFormatType.DEC),
        0x603C: ("reverse_reactive_energy", 2, RegisterValueType.UINT32, "varh", RegisterFormatType.DEC),
    }

    implemented = _implemented_family_sensors_by_address(MeterFamily.GROW)

    assert set(implemented) == set(expected)

    for address, (
        expected_key,
        expected_count,
        expected_value_type,
        expected_register_unit,
        expected_register_format,
    ) in expected.items():
        sensor = implemented[address]
        assert sensor.key == expected_key
        assert sensor.count == expected_count
        assert sensor.value_type is expected_value_type
        assert sensor.register_unit == expected_register_unit
        assert sensor.register_format is expected_register_format


def test_implemented_pro_register_schema_matches_pro_map() -> None:
    """Implemented PRO registers should keep the agreed raw length/type/format metadata."""
    expected = {
        0x4000: ("serial_number", 2, RegisterValueType.HEX32, None, RegisterFormatType.HEX),
        0x4002: ("meter_code", 1, RegisterValueType.HEX16, None, RegisterFormatType.HEX),
        0x4003: ("modbus_id", 1, RegisterValueType.INT16, None, RegisterFormatType.DEC),
        0x4004: ("baud_rate", 1, RegisterValueType.INT16, "bps", RegisterFormatType.DEC),
        0x4005: ("protocol_version", 2, RegisterValueType.FLOAT32, None, RegisterFormatType.FLOAT),
        0x4007: ("software_version", 2, RegisterValueType.FLOAT32, None, RegisterFormatType.FLOAT),
        0x4009: ("hardware_version", 2, RegisterValueType.FLOAT32, None, RegisterFormatType.FLOAT),
        0x400B: ("meter_amps", 1, RegisterValueType.INT16, "A", RegisterFormatType.DEC),
        0x400D: ("s0_output_rate", 2, RegisterValueType.FLOAT32, "imp/kWh", RegisterFormatType.FLOAT),
        0x4011: ("parity_setting", 1, RegisterValueType.INT16, None, RegisterFormatType.ENUM),
        0x4015: ("error_code", 1, RegisterValueType.INT16, None, RegisterFormatType.DEC),
        0x4016: ("power_down_counter", 1, RegisterValueType.INT16, None, RegisterFormatType.DEC),
        0x4017: ("present_quadrant", 1, RegisterValueType.INT16, None, RegisterFormatType.DEC),
        0x401B: ("checksum", 2, RegisterValueType.HEX32, None, RegisterFormatType.HEX),
        0x401D: ("active_status_word", 2, RegisterValueType.HEX32, None, RegisterFormatType.HEX),
        0x401F: ("ct_mode", 1, RegisterValueType.INT16, None, RegisterFormatType.DEC),
        0x5000: ("voltage", 2, RegisterValueType.FLOAT32, "V", RegisterFormatType.FLOAT),
        0x5002: ("voltage_l1", 2, RegisterValueType.FLOAT32, "V", RegisterFormatType.FLOAT),
        0x5004: ("voltage_l2", 2, RegisterValueType.FLOAT32, "V", RegisterFormatType.FLOAT),
        0x5006: ("voltage_l3", 2, RegisterValueType.FLOAT32, "V", RegisterFormatType.FLOAT),
        0x5008: ("grid_frequency", 2, RegisterValueType.FLOAT32, "Hz", RegisterFormatType.FLOAT),
        0x500A: ("current", 2, RegisterValueType.FLOAT32, "A", RegisterFormatType.FLOAT),
        0x500C: ("current_l1", 2, RegisterValueType.FLOAT32, "A", RegisterFormatType.FLOAT),
        0x500E: ("current_l2", 2, RegisterValueType.FLOAT32, "A", RegisterFormatType.FLOAT),
        0x5010: ("current_l3", 2, RegisterValueType.FLOAT32, "A", RegisterFormatType.FLOAT),
        0x5012: ("total_active_power", 2, RegisterValueType.FLOAT32, "kW", RegisterFormatType.FLOAT),
        0x5014: ("active_power_l1", 2, RegisterValueType.FLOAT32, "kW", RegisterFormatType.FLOAT),
        0x5016: ("active_power_l2", 2, RegisterValueType.FLOAT32, "kW", RegisterFormatType.FLOAT),
        0x5018: ("active_power_l3", 2, RegisterValueType.FLOAT32, "kW", RegisterFormatType.FLOAT),
        0x501A: ("total_reactive_power", 2, RegisterValueType.FLOAT32, "kvar", RegisterFormatType.FLOAT),
        0x501C: ("reactive_power_l1", 2, RegisterValueType.FLOAT32, "kvar", RegisterFormatType.FLOAT),
        0x501E: ("reactive_power_l2", 2, RegisterValueType.FLOAT32, "kvar", RegisterFormatType.FLOAT),
        0x5020: ("reactive_power_l3", 2, RegisterValueType.FLOAT32, "kvar", RegisterFormatType.FLOAT),
        0x5022: ("total_apparent_power", 2, RegisterValueType.FLOAT32, "kVA", RegisterFormatType.FLOAT),
        0x5024: ("apparent_power_l1", 2, RegisterValueType.FLOAT32, "kVA", RegisterFormatType.FLOAT),
        0x5026: ("apparent_power_l2", 2, RegisterValueType.FLOAT32, "kVA", RegisterFormatType.FLOAT),
        0x5028: ("apparent_power_l3", 2, RegisterValueType.FLOAT32, "kVA", RegisterFormatType.FLOAT),
        0x502A: ("power_factor", 2, RegisterValueType.FLOAT32, None, RegisterFormatType.FLOAT),
        0x502C: ("power_factor_l1", 2, RegisterValueType.FLOAT32, None, RegisterFormatType.FLOAT),
        0x502E: ("power_factor_l2", 2, RegisterValueType.FLOAT32, None, RegisterFormatType.FLOAT),
        0x5030: ("power_factor_l3", 2, RegisterValueType.FLOAT32, None, RegisterFormatType.FLOAT),
        0x6000: ("total_active_energy", 2, RegisterValueType.FLOAT32, "kWh", RegisterFormatType.FLOAT),
        0x600C: ("forward_active_energy", 2, RegisterValueType.FLOAT32, "kWh", RegisterFormatType.FLOAT),
        0x6018: ("reverse_active_energy", 2, RegisterValueType.FLOAT32, "kWh", RegisterFormatType.FLOAT),
        0x6024: ("total_reactive_energy", 2, RegisterValueType.FLOAT32, "kvarh", RegisterFormatType.FLOAT),
        0x6030: ("forward_reactive_energy", 2, RegisterValueType.FLOAT32, "kvarh", RegisterFormatType.FLOAT),
        0x603C: ("reverse_reactive_energy", 2, RegisterValueType.FLOAT32, "kvarh", RegisterFormatType.FLOAT),
        0x6048: ("tariff", 1, RegisterValueType.INT16, None, RegisterFormatType.ENUM),
    }

    implemented = _implemented_family_sensors_by_address(MeterFamily.PRO)

    assert set(implemented) == set(expected)

    for address, (
        expected_key,
        expected_count,
        expected_value_type,
        expected_register_unit,
        expected_register_format,
    ) in expected.items():
        sensor = implemented[address]
        assert sensor.key == expected_key
        assert sensor.count == expected_count
        assert sensor.value_type is expected_value_type
        assert sensor.register_unit == expected_register_unit
        assert sensor.register_format is expected_register_format
