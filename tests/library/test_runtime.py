"""Tests for shared Inepro Metering runtime models."""

from datetime import UTC, datetime

from inepro_metering.const import MeterFamily, TransportType
from inepro_metering.models import get_profile
from inepro_metering.runtime import MeterRoute, build_meter_runtime_data


def test_build_meter_runtime_data_extracts_identity_versions_and_settings() -> None:
    """One decoded runtime model should capture identity, firmware, route, and settings."""
    last_success = datetime(2026, 4, 22, 12, 30, tzinfo=UTC)
    meter = build_meter_runtime_data(
        profile=get_profile(MeterFamily.GROW, "grow_750"),
        route=MeterRoute(transport=TransportType.SERIAL, slave_id=157),
        readings={
            "serial_number": "25100001",
            "product_code": "0756",
            "legal_software_version": 1.0,
            "legal_software_crc": "B478FEE9",
            "non_legal_software_version": 1.0,
            "non_legal_software_crc": "B999F660",
            "hardware_version": 2.03,
            "wifi_support": "supported",
        },
        available=True,
        last_successful_update=last_success,
    )

    assert meter.identity.device_serial == "075625100001"
    assert meter.firmware.formatted_version("legal_software_version") == "1.0 (B478FEE9)"
    assert meter.firmware.software_version == "legal 1.0 (B478FEE9) / non-legal 1.0 (B999F660)"
    assert meter.firmware.hardware_version == "2.03"
    assert meter.route.transport is TransportType.SERIAL
    assert meter.route.slave_id == 157
    assert meter.connection.available is True
    assert meter.connection.last_successful_update == last_success
    assert meter.writable_settings["wifi_support"].value is True


def test_build_meter_runtime_data_maps_known_crc_versions() -> None:
    """Known firmware CRCs should resolve to the existing configurator-style label."""
    meter = build_meter_runtime_data(
        profile=get_profile(MeterFamily.GROW, "grow_850"),
        route=MeterRoute(transport=TransportType.SERIAL, slave_id=1),
        readings={
            "serial_number": "25150002",
            "product_code": "0851",
            "legal_software_version": 1.0,
            "legal_software_crc": "6A479857",
            "non_legal_software_version": 1.0,
            "non_legal_software_crc": "6A479857",
        },
        available=True,
        last_successful_update=None,
    )

    assert meter.firmware.formatted_version("legal_software_version") == "1.0.2536"
    assert meter.firmware.formatted_version("non_legal_software_version") == "1.0.2536"
    assert meter.firmware.software_version == "1.0.2536"


def test_build_meter_runtime_data_keeps_device_identification_and_pro_versions() -> None:
    """Runtime data should keep device-identification details and generic versions."""
    meter = build_meter_runtime_data(
        profile=get_profile(MeterFamily.PRO, "pro_380"),
        route=MeterRoute(transport=TransportType.TCP_ETHERNET, slave_id=1),
        readings={
            "serial_number": "12345678",
            "protocol_version": 2.18,
            "software_version": 2.18,
            "hardware_version": 1.02,
            "modbus_manufacturer_name": "inepro Metering B.V.",
            "modbus_product_name": "PRO380",
            "modbus_device_version": "V2.18",
        },
        available=True,
        last_successful_update=None,
    )

    assert meter.device_identification.manufacturer_name == "inepro Metering B.V."
    assert meter.device_identification.product_name == "PRO380"
    assert meter.device_identification.device_version == "V2.18"
    assert meter.firmware.formatted_version("protocol_version") == "2.18"
    assert meter.firmware.formatted_version("software_version") == "2.18"
    assert meter.firmware.software_version == "V2.18"


def test_build_meter_runtime_data_keeps_tcp_gateway_metadata() -> None:
    """Runtime data should retain parsed TCP gateway metadata when present."""
    meter = build_meter_runtime_data(
        profile=get_profile(MeterFamily.PRO, "pro_380"),
        route=MeterRoute(transport=TransportType.TCP_GATEWAY, slave_id=7),
        readings={
            "serial_number": "12345678",
            "tcp_gateway_device_type": "TCP Gateway",
            "tcp_gateway_hardware_version": "1",
            "tcp_gateway_serial_number": "033023260122",
            "tcp_gateway_firmware_version": "1.0.973",
            "tcp_gateway_bootloader_version": "1.0.845",
        },
        available=True,
        last_successful_update=None,
    )

    assert meter.gateway.device_type == "TCP Gateway"
    assert meter.gateway.hardware_version == "1"
    assert meter.gateway.serial_number == "033023260122"
    assert meter.gateway.firmware_version == "1.0.973"
    assert meter.gateway.bootloader_version == "1.0.845"
