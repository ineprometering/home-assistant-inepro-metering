"""Diagnostics tests for the Inepro Metering integration."""

from __future__ import annotations

from datetime import UTC, datetime

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components.diagnostics import REDACTED

from custom_components.inepro_metering.const import (
    CONF_ACTIVE_ROUTE,
    CONF_BAUDRATE,
    CONF_BLUETOOTH_ADDRESS,
    CONF_BLUETOOTH_NAME,
    CONF_BYTESIZE,
    CONF_FAMILY,
    CONF_METERS,
    CONF_PARITY,
    CONF_ROUTES,
    CONF_ROUTE_PURPOSE,
    CONF_SERIAL_NUMBER,
    CONF_SERIAL_PORT,
    CONF_SLAVE_ID,
    CONF_STOPBITS,
    CONF_TIMEOUT,
    CONF_TRANSPORT,
    CONF_VARIANT,
    DEFAULT_BAUDRATE,
    DEFAULT_BYTESIZE,
    DEFAULT_PARITY,
    DEFAULT_STOPBITS,
    DOMAIN,
    ROUTE_PURPOSE_ACTIVE,
    ROUTE_PURPOSE_ONBOARDING,
)
from custom_components.inepro_metering.coordinator import (
    CoordinatorData,
    MeterCoordinatorData,
    SerialBusCoordinatorData,
)
from custom_components.inepro_metering.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.inepro_metering.models import get_profile
from inepro_metering.runtime import MeterRoute, build_meter_runtime_data
from inepro_metering.const import MeterFamily, TransportType


class _FakeSingleCoordinator:
    """Small diagnostics stub for one single-meter entry."""

    def __init__(self, data: CoordinatorData) -> None:
        self.data = data
        self.last_update_success = True
        self.last_exception = None


class _FakeBusCoordinator:
    """Small diagnostics stub for one shared-bus entry."""

    def __init__(self, data: SerialBusCoordinatorData) -> None:
        self.data = data
        self.last_update_success = True
        self.last_exception = None


async def test_config_entry_diagnostics_redact_secrets_and_summarize_runtime(
    hass,
    enable_custom_integrations,
) -> None:
    """Diagnostics should redact secrets and expose only summary runtime data."""
    del enable_custom_integrations
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="075625100001",
        unique_id="075625100001",
        data={
            CONF_FAMILY: MeterFamily.GROW.value,
            CONF_VARIANT: "grow_750",
            CONF_TRANSPORT: TransportType.TCP_ETHERNET.value,
            CONF_SLAVE_ID: 1,
            "scan_interval": 15,
            "host": "192.0.2.15",
            "port": 502,
            CONF_TIMEOUT: 3,
            CONF_SERIAL_NUMBER: "075625100001",
            CONF_ROUTES: [
                {
                    CONF_TRANSPORT: TransportType.TCP_ETHERNET.value,
                    CONF_SLAVE_ID: 1,
                    CONF_TIMEOUT: 3,
                    CONF_ROUTE_PURPOSE: ROUTE_PURPOSE_ACTIVE,
                    "host": "192.0.2.15",
                    "port": 502,
                }
            ],
            CONF_ACTIVE_ROUTE: "tcp_ethernet:192.0.2.15:502:1",
        },
        options={
            "ssid": "OfficeWiFi",
            "password": "super-secret",
            "pairing_code": "123456",
        },
        version=5,
    )
    entry.add_to_hass(hass)

    runtime = build_meter_runtime_data(
        profile=get_profile(MeterFamily.GROW.value, "grow_750"),
        route=MeterRoute(
            transport=TransportType.TCP_ETHERNET,
            slave_id=1,
        ),
        readings={
            "serial_number": "075625100001",
            "product_code": "0756",
            "meter_code": "0756",
            "software_version": 1.2,
            "modbus_product_name": "GROW 3P4S",
            "modbus_device_version": "1.2.0",
        },
        available=True,
        last_successful_update=datetime(2026, 4, 23, 11, 0, tzinfo=UTC),
    )
    entry.runtime_data = _FakeSingleCoordinator(CoordinatorData(meter=runtime))

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["entry"]["options"]["ssid"] == REDACTED
    assert result["entry"]["options"]["password"] == REDACTED
    assert result["entry"]["options"]["pairing_code"] == REDACTED
    assert result["transport"]["active_route_key"] == "tcp_ethernet:192.0.2.15:502:1"
    assert result["runtime"]["meters"][0]["identity"]["serial_number"] == "075625100001"
    assert result["runtime"]["meters"][0]["firmware"]["software_version"] == "1.2.0"
    assert result["runtime"]["meters"][0]["readings"]["count"] == 6
    assert result["coordinator"]["snapshot"]["reading_count"] == 6


async def test_config_entry_diagnostics_include_bus_routes_and_snapshot(
    hass,
    enable_custom_integrations,
) -> None:
    """Diagnostics should describe shared-bus routes without dumping raw values."""
    del enable_custom_integrations
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Main RS485 Bus",
        unique_id="COM5",
        data={
            CONF_FAMILY: MeterFamily.GROW.value,
            CONF_TRANSPORT: TransportType.SERIAL.value,
            "scan_interval": 15,
            CONF_SERIAL_PORT: "COM5",
            CONF_BAUDRATE: DEFAULT_BAUDRATE,
            CONF_BYTESIZE: DEFAULT_BYTESIZE,
            CONF_PARITY: DEFAULT_PARITY,
            CONF_STOPBITS: DEFAULT_STOPBITS,
            CONF_TIMEOUT: 3,
            CONF_METERS: [
                {
                    CONF_FAMILY: MeterFamily.GROW.value,
                    "name": "075625100001",
                    CONF_VARIANT: "grow_750",
                    CONF_SLAVE_ID: 1,
                    CONF_SERIAL_NUMBER: "075625100001",
                    "product_code": "0756",
                    CONF_ROUTES: [
                        {
                            CONF_TRANSPORT: TransportType.SERIAL.value,
                            CONF_SLAVE_ID: 1,
                            CONF_TIMEOUT: 3,
                            CONF_ROUTE_PURPOSE: ROUTE_PURPOSE_ACTIVE,
                            CONF_SERIAL_PORT: "COM5",
                            CONF_BAUDRATE: DEFAULT_BAUDRATE,
                            CONF_BYTESIZE: DEFAULT_BYTESIZE,
                            CONF_PARITY: DEFAULT_PARITY,
                            CONF_STOPBITS: DEFAULT_STOPBITS,
                        },
                        {
                            CONF_TRANSPORT: TransportType.BLUETOOTH_PROXY.value,
                            CONF_SLAVE_ID: 1,
                            CONF_TIMEOUT: 5,
                            CONF_ROUTE_PURPOSE: ROUTE_PURPOSE_ONBOARDING,
                            "host": "127.0.0.1",
                            "port": 16026,
                            CONF_BLUETOOTH_ADDRESS: "11:22:33:44:55:66",
                            CONF_BLUETOOTH_NAME: "IM-075625100001",
                        },
                    ],
                    CONF_ACTIVE_ROUTE: "bluetooth_proxy:127.0.0.1:16026:11:22:33:44:55:66:1",
                }
            ],
        },
        version=5,
    )
    entry.add_to_hass(hass)

    runtime = build_meter_runtime_data(
        profile=get_profile(MeterFamily.GROW.value, "grow_750"),
        route=MeterRoute(
            transport=TransportType.BLUETOOTH_PROXY,
            slave_id=1,
        ),
        readings={
            "serial_number": "075625100001",
            "product_code": "0756",
            "meter_code": "0756",
        },
        available=True,
        last_successful_update=datetime(2026, 4, 23, 11, 30, tzinfo=UTC),
    )
    entry.runtime_data = _FakeBusCoordinator(
        SerialBusCoordinatorData(
            meters={
                "075625100001": MeterCoordinatorData(meter=runtime),
            }
        )
    )

    result = await async_get_config_entry_diagnostics(hass, entry)

    meter_transport = result["transport"]["meters"][0]
    assert meter_transport["meter_key"] == "075625100001"
    assert meter_transport["active_route_key"].startswith("bluetooth_proxy:")
    assert len(meter_transport["available_routes"]) == 2
    assert result["runtime"]["meters"][0]["route"]["transport"] == "bluetooth_proxy"
    assert result["coordinator"]["snapshot"]["meter_count"] == 1
    assert result["coordinator"]["snapshot"]["available_meters"] == ["075625100001"]
