"""Tests for the standalone Inepro Metering model library."""

import struct

from inepro_metering.const import MAX_REGISTERS_PER_READ, MeterFamily, TransportType
from inepro_metering.models import (
    RegisterValueType,
    decode_grow_error_code,
    format_grow_error_summary,
    get_profile,
    get_supported_families,
)
from inepro_metering.reading import build_register_blocks, decode_sensor_value


GROW_THREE_PHASE_VARIANTS = ("grow_701", "grow_750")
GROW_SINGLE_PHASE_VARIANTS = ("grow_800", "grow_850")


PRO_VARIANTS = (
    "pro_1",
    "pro_2",
    "pro_380",
    "pro_380ct",
    "pro_1_solare",
    "pro_2_solare",
    "pro_380_solare",
    "pro_380ct_solare",
    "n_1",
    "n_380_40a",
    "n_380ct",
)

PRO_SINGLE_PHASE_VARIANTS = (
    "pro_1",
    "pro_2",
    "pro_1_solare",
    "pro_2_solare",
    "n_1",
)

PRO_THREE_PHASE_VARIANTS = (
    "pro_380",
    "pro_380ct",
    "pro_380_solare",
    "pro_380ct_solare",
    "n_380_40a",
    "n_380ct",
)

PRO_CT_VARIANTS = ("pro_380ct", "pro_380ct_solare", "n_380ct")


def _encode_int32(value: int) -> list[int]:
    """Encode an int32 into two big-endian Modbus registers."""
    packed = struct.pack(">i", value)
    return list(struct.unpack(">HH", packed))


def _encode_uint32(value: int) -> list[int]:
    """Encode a uint32 into two big-endian Modbus registers."""
    packed = struct.pack(">I", value)
    return list(struct.unpack(">HH", packed))


def test_supported_families_only_exposes_families_with_profiles() -> None:
    """Only populated families should appear in the current setup flow."""
    assert get_supported_families() == (MeterFamily.GROW, MeterFamily.PRO)


def test_grow_850_profile_exposes_shared_bus_gateway_transport() -> None:
    """The wired-only GROW 850 profile should expose RTU and gateway bus access."""
    profile = get_profile(MeterFamily.GROW, "grow_850")

    assert profile.model_code == "850"
    assert profile.title == "GROW 1P1U"
    assert profile.supported_transports == (
        TransportType.SERIAL,
        TransportType.TCP_GATEWAY,
    )


def test_only_wireless_grow_profiles_expose_wifi_and_bt_diagnostics() -> None:
    """Only 3P4U, 3P4S, and 1P2U should expose Wi-Fi/Bluetooth capability."""
    wireless_variants = ("grow_701", "grow_750", "grow_800")

    for variant in wireless_variants:
        profile = get_profile(MeterFamily.GROW, variant)
        diagnostic_keys = {sensor.key for sensor in profile.diagnostic_sensors}

        assert TransportType.TCP_GATEWAY in profile.supported_transports
        assert TransportType.TCP_WIFI in profile.supported_transports
        assert TransportType.BLUETOOTH in profile.supported_transports
        assert TransportType.BLUETOOTH_PROXY in profile.supported_transports
        assert "wifi_support" in diagnostic_keys
        assert "bluetooth_mode" in diagnostic_keys

    wired_only_profile = get_profile(MeterFamily.GROW, "grow_850")
    wired_only_diagnostic_keys = {
        sensor.key for sensor in wired_only_profile.diagnostic_sensors
    }

    assert TransportType.TCP_GATEWAY in wired_only_profile.supported_transports
    assert TransportType.TCP_WIFI not in wired_only_profile.supported_transports
    assert TransportType.BLUETOOTH not in wired_only_profile.supported_transports
    assert TransportType.BLUETOOTH_PROXY not in wired_only_profile.supported_transports
    assert "wifi_support" not in wired_only_diagnostic_keys
    assert "bluetooth_mode" not in wired_only_diagnostic_keys


def test_grow_701_profile_contains_ocmf_diagnostics() -> None:
    """OCMF session fields should live in diagnostics for OCMF-capable GROW models."""
    profile = get_profile(MeterFamily.GROW, "grow_701")

    measurement_keys = {sensor.key for sensor in profile.measurement_sensors}
    diagnostic_keys = {sensor.key for sensor in profile.diagnostic_sensors}

    assert "billing_session_start_energy" not in measurement_keys
    assert "billing_session_status" not in measurement_keys
    assert "billing_session_start_energy" in diagnostic_keys
    assert "billing_session_status" in diagnostic_keys


def test_grow_850_profile_contains_identity_diagnostics() -> None:
    """The GROW profile should expose the new identity and firmware diagnostics."""
    profile = get_profile(MeterFamily.GROW, "grow_850")

    diagnostic_keys = {sensor.key for sensor in profile.diagnostic_sensors}

    assert "serial_number" in diagnostic_keys
    assert "product_code" in diagnostic_keys
    assert "legal_software_version" in diagnostic_keys
    assert "error_code" in diagnostic_keys


def test_grow_profile_titles_use_product_names() -> None:
    """The user-facing GROW titles should use product names instead of numeric codes."""
    assert get_profile(MeterFamily.GROW, "grow_701").title == "GROW 3P4U"
    assert get_profile(MeterFamily.GROW, "grow_750").title == "GROW 3P4S"
    assert get_profile(MeterFamily.GROW, "grow_800").title == "GROW 1P2U"
    assert get_profile(MeterFamily.GROW, "grow_850").title == "GROW 1P1U"


def test_grow_active_energy_metadata_converts_wh_registers_to_kwh() -> None:
    """GROW active energy definitions should expose HA-friendly kWh values."""
    profile = get_profile(MeterFamily.GROW, "grow_850")
    sensors = {sensor.key: sensor for sensor in profile.measurement_sensors}

    expected_state_classes = {
        "total_active_energy": "total",
        "forward_active_energy": "total_increasing",
        "reverse_active_energy": "total_increasing",
    }

    for key, state_class in expected_state_classes.items():
        sensor = sensors[key]
        assert sensor.device_class == "energy"
        assert sensor.state_class == state_class
        assert sensor.native_unit_of_measurement == "kWh"
        assert sensor.register_unit == "Wh"
        assert sensor.scale == 0.001


def test_grow_three_phase_profiles_expose_import_export_energy_metadata() -> None:
    """Three-phase GROW profiles should expose the PR energy register set."""
    for variant in GROW_THREE_PHASE_VARIANTS:
        profile = get_profile(MeterFamily.GROW, variant)
        sensors = {sensor.key: sensor for sensor in profile.measurement_sensors}
        diagnostics = {sensor.key: sensor for sensor in profile.diagnostic_sensors}

        default_energy_keys = (
            "active_energy_import_total",
            "active_energy_import_l1",
            "active_energy_import_l2",
            "active_energy_import_l3",
            "active_energy_export_total",
            "active_energy_export_l1",
            "active_energy_export_l2",
            "active_energy_export_l3",
        )
        for key in default_energy_keys:
            sensor = sensors[key]
            assert sensor.device_class == "energy"
            assert sensor.state_class == "total_increasing"
            assert sensor.native_unit_of_measurement == "kWh"
            assert sensor.register_unit == "Wh"
            assert sensor.scale == 0.001
            assert sensor.entity_registry_enabled_default is True

        assert (
            sensors["forward_active_energy"].address
            == sensors["active_energy_import_total"].address
        )
        assert (
            sensors["reverse_active_energy"].address
            == sensors["active_energy_export_total"].address
        )
        assert sensors["active_energy_total"].value_type is RegisterValueType.INT32
        assert sensors["active_energy_total"].state_class == "total"
        assert sensors["reactive_energy_q1_l1"].native_unit_of_measurement == "kvarh"
        assert sensors["reactive_energy_q1_l1"].device_class is None
        assert sensors["reactive_energy_q1_l1"].entity_registry_enabled_default is False
        assert sensors["apparent_energy_l1"].native_unit_of_measurement == "kVAh"
        assert sensors["apparent_energy_l1"].device_class is None
        assert sensors["apparent_energy_l1"].entity_registry_enabled_default is False
        assert sensors["resettable_day_counter_l1"].entity_category == "diagnostic"
        assert (
            sensors["resettable_day_counter_l1"].entity_registry_enabled_default
            is False
        )
        assert diagnostics["active_tariff"].entity_category == "diagnostic"
        assert diagnostics["active_tariff"].options == {
            1: "T1",
            2: "T2",
            3: "T3",
            4: "T4",
        }


def test_grow_single_phase_profiles_skip_three_phase_energy_entities() -> None:
    """Single-phase GROW profiles should not expose unsupported L1/L2/L3 energy."""
    unsupported_keys = {
        "active_energy_import_l1",
        "active_energy_import_l2",
        "active_energy_import_l3",
        "active_energy_export_l1",
        "active_energy_export_l2",
        "active_energy_export_l3",
        "reactive_energy_q1_l1",
        "apparent_energy_l1",
        "resettable_day_counter_l1",
    }

    for variant in GROW_SINGLE_PHASE_VARIANTS:
        profile = get_profile(MeterFamily.GROW, variant)
        measurement_keys = {sensor.key for sensor in profile.measurement_sensors}

        assert "active_energy_import_total" in measurement_keys
        assert "active_energy_export_total" in measurement_keys
        assert measurement_keys.isdisjoint(unsupported_keys)


def test_grow_energy_registers_decode_signed_and_unsigned_values() -> None:
    """GROW energy register definitions should decode INT32 and UINT32 correctly."""
    profile = get_profile(MeterFamily.GROW, "grow_750")
    sensors = {sensor.key: sensor for sensor in profile.measurement_sensors}

    assert (
        decode_sensor_value(sensors["active_energy_total"], _encode_int32(-1234))
        == -1.234
    )
    assert decode_sensor_value(sensors["active_energy_l1"], _encode_int32(-100)) == -0.1
    assert (
        decode_sensor_value(sensors["active_energy_import_l1"], _encode_uint32(1111))
        == 1.111
    )
    assert (
        decode_sensor_value(sensors["active_energy_export_l3"], _encode_uint32(6666))
        == 6.666
    )


def test_grow_energy_register_blocks_stay_within_read_limit() -> None:
    """The full GROW energy block should be split into valid Modbus reads."""
    profile = get_profile(MeterFamily.GROW, "grow_750")
    blocks = build_register_blocks(profile.all_sensors)
    energy_blocks = [
        block for block in blocks if 0x6000 <= block.start_address <= 0x6200
    ]

    assert all(block.count <= MAX_REGISTERS_PER_READ for block in energy_blocks)
    assert (energy_blocks[0].start_address, energy_blocks[0].count) == (0x6000, 119)
    assert any(
        block.start_address == 0x6200 and block.count == 2 for block in energy_blocks
    )


def test_pro_profiles_support_serial_and_gateway_bus_access() -> None:
    """All supported PRO profiles should expose RTU plus TCP gateway bus access."""
    for variant in PRO_VARIANTS:
        profile = get_profile(MeterFamily.PRO, variant)
        assert profile.supported_transports == (
            TransportType.SERIAL,
            TransportType.TCP_GATEWAY,
        )


def test_pro_profile_titles_match_product_names() -> None:
    """The user-facing PRO titles should use product names."""
    expected_titles = {
        "pro_1": "PRO1",
        "pro_2": "PRO2",
        "pro_380": "PRO380",
        "pro_380ct": "PRO380CT",
        "pro_1_solare": "PRO1 Solare",
        "pro_2_solare": "PRO2 Solare",
        "pro_380_solare": "PRO380 Solare",
        "pro_380ct_solare": "PRO380CT Solare",
        "n_1": "N1",
        "n_380_40a": "N380 40A",
        "n_380ct": "N380 CT",
    }

    assert {
        variant: get_profile(MeterFamily.PRO, variant).title for variant in PRO_VARIANTS
    } == expected_titles


def test_pro_active_energy_metadata_uses_pro_kwh_registers_directly() -> None:
    """PRO active energy definitions should not inherit GROW Wh scaling."""
    profile = get_profile(MeterFamily.PRO, "pro_380")
    sensors = {sensor.key: sensor for sensor in profile.measurement_sensors}

    expected_state_classes = {
        "total_active_energy": "total",
        "forward_active_energy": "total_increasing",
        "reverse_active_energy": "total_increasing",
    }

    for key, state_class in expected_state_classes.items():
        sensor = sensors[key]
        assert sensor.device_class == "energy"
        assert sensor.state_class == state_class
        assert sensor.native_unit_of_measurement == "kWh"
        assert sensor.register_unit == "kWh"
        assert sensor.scale == 1.0


def test_pro_single_phase_profiles_expose_single_phase_measurements() -> None:
    """Single-phase PRO-family variants should expose the 1P register subset."""
    for variant in PRO_SINGLE_PHASE_VARIANTS:
        profile = get_profile(MeterFamily.PRO, variant)
        measurement_keys = {sensor.key for sensor in profile.measurement_sensors}
        diagnostic_keys = {sensor.key for sensor in profile.diagnostic_sensors}

        assert "voltage" in measurement_keys
        assert "current" in measurement_keys
        assert "voltage_l2" not in measurement_keys
        assert "current_l3" not in measurement_keys
        assert "software_version" in diagnostic_keys
        assert "ct_mode" not in diagnostic_keys


def test_pro_three_phase_profiles_expose_per_phase_measurements() -> None:
    """Three-phase PRO-family variants should expose the per-phase subset."""
    for variant in PRO_THREE_PHASE_VARIANTS:
        profile = get_profile(MeterFamily.PRO, variant)
        measurement_keys = {sensor.key for sensor in profile.measurement_sensors}

        assert "voltage" not in measurement_keys
        assert "current" not in measurement_keys
        assert "voltage_l1" in measurement_keys
        assert "voltage_l2" in measurement_keys
        assert "current_l3" in measurement_keys
        assert "active_power_l1" in measurement_keys


def test_pro_380ct_exposes_ct_specific_diagnostics() -> None:
    """Only CT variants should expose CT-specific diagnostics."""
    for variant in PRO_CT_VARIANTS:
        ct_profile = get_profile(MeterFamily.PRO, variant)
        assert "ct_mode" in {sensor.key for sensor in ct_profile.diagnostic_sensors}

    for variant in set(PRO_VARIANTS) - set(PRO_CT_VARIANTS):
        direct_profile = get_profile(MeterFamily.PRO, variant)
        assert "ct_mode" not in {
            sensor.key for sensor in direct_profile.diagnostic_sensors
        }


def test_grow_error_code_decoder_handles_bitfields() -> None:
    """GROW error codes should decode as combinable bitfields."""
    assert decode_grow_error_code("00C4") == (
        "calibration data corruption",
        "counter journal corruption",
        "provisioning data invalid",
    )
    assert format_grow_error_summary("00C4") == (
        "calibration data corruption, counter journal corruption, provisioning data invalid"
    )


def test_grow_error_code_decoder_handles_clean_and_unknown_values() -> None:
    """Zero and unknown bits should be handled predictably."""
    assert decode_grow_error_code("0000") == ()
    assert format_grow_error_summary("0000") == "No critical errors"
    assert decode_grow_error_code("8000") == ("unknown error bits 8000",)
