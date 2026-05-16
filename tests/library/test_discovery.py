"""Tests for Inepro Metering discovery and identity helpers."""

from unittest.mock import AsyncMock, patch

import inepro_metering.discovery as discovery_module

from inepro_metering.discovery import (
    _discover_tcp_gateways,
    _expand_tcp_gateway_scan_target,
    DiscoveredTcpGateway,
    async_discover_grow_serial_bus,
    async_discover_grow_bluetooth_proxy_meters,
    async_read_grow_serial_number,
    async_discover_tcp_gateways,
    build_grow_serial_number,
    infer_grow_variant,
    parse_grow_bluetooth_name,
    parse_grow_serial_number,
)
from inepro_metering.const import MeterFamily
from inepro_metering.modbus import (
    CONF_BAUDRATE,
    CONF_BYTESIZE,
    CONF_PARITY,
    CONF_SERIAL_PORT,
    CONF_STOPBITS,
    CONF_TIMEOUT,
    IneproReadError,
)


def test_parse_grow_serial_number() -> None:
    """GROW serial numbers should expose product and production details."""
    parsed = parse_grow_serial_number("075625480002")

    assert parsed is not None
    assert parsed.serial_number == "075625480002"
    assert parsed.product_code == "0756"
    assert parsed.production_year_code == 25
    assert parsed.production_year == 2025
    assert parsed.production_week == 48
    assert parsed.sequence == 2


def test_parse_grow_serial_number_rejects_invalid_week() -> None:
    """Week 00 should not be accepted as a valid production week."""
    assert parse_grow_serial_number("075625000002") is None


def test_parse_grow_bluetooth_name_uses_full_serial() -> None:
    """Bluetooth names should decode to the same 12-digit GROW serial."""
    parsed = parse_grow_bluetooth_name("IM-070125100001")

    assert parsed is not None
    assert parsed.serial_number == "070125100001"
    assert parsed.product_code == "0701"
    assert parsed.production_year == 2025
    assert parsed.production_week == 10
    assert parsed.sequence == 1


def test_infer_grow_variant_from_product_prefixes() -> None:
    """Known product prefixes should map to the current GROW profiles."""
    assert infer_grow_variant("070125100001") == "grow_701"
    assert infer_grow_variant("075625480002") == "grow_750"
    assert infer_grow_variant("080125100001") == "grow_800"
    assert infer_grow_variant("085125250008") == "grow_850"
    assert infer_grow_variant(None, "0756") == "grow_750"


def test_build_grow_serial_number_requires_valid_product_and_tail() -> None:
    """The shared serial-number builder should validate the resulting GROW serial."""
    assert build_grow_serial_number("0756", "25480002") == "075625480002"
    assert build_grow_serial_number("0756", "00000000") is None


class _FakeIdentityClient:
    """Very small client for shared discovery identity tests."""

    async def async_read_registers(self, register_type, address, count, slave_id):
        del register_type, count
        assert slave_id == 7
        if address == 0x4000:
            return [0x2548, 0x0002]
        if address == 0x4025:
            return [0x0756]
        raise AssertionError(f"Unexpected address {address:#06x}")


class _FakeBusDiscoveryClient:
    """Fake Modbus client for shared-bus discovery tests."""

    _meters = {
        1: {"tail": (0x2548, 0x0001), "meter_code": 0x0101, "amps": 45},
        2: {"tail": (0x2548, 0x0002), "meter_code": 0x0101, "amps": 100},
        3: {"tail": (0x2548, 0x0102), "meter_code": 0x0102, "product_code": 0x0999},
        4: {"tail": (0x2548, 0x0103), "meter_code": 0x0103, "product_code": 0x0998},
        5: {"tail": (0x2548, 0x0009), "meter_code": 0x2009, "product_code": 0x0254},
        6: {"tail": (0x2548, 0x0010), "meter_code": 0x2010, "product_code": 0x0287},
        7: {"tail": (0x2548, 0x0007), "meter_code": 0x2007, "product_code": 0x0257},
        8: {"tail": (0x2548, 0x0008), "meter_code": 0x2008, "product_code": 0x0260},
        9: {"tail": (0x2548, 0x3201), "meter_code": 0x3201, "product_code": 0x0510},
        10: {"tail": (0x2548, 0x3203), "meter_code": 0x3203, "amps": 40},
        11: {"tail": (0x2548, 0x3204), "meter_code": 0x3203, "amps": 5},
    }

    def __init__(self, config):
        self.config = config

    async def async_ping(self) -> None:
        """Match the Modbus client API."""

    async def async_close(self) -> None:
        """Match the Modbus client API."""

    async def async_read_registers(self, register_type, address, count, slave_id):
        del register_type
        meter = self._meters.get(slave_id)
        if meter is None:
            raise IneproReadError(f"Unexpected read {address:#06x} for slave {slave_id}")

        if address == 0x4000 and count == 2:
            return list(meter["tail"])
        if address == 0x4002:
            return [meter["meter_code"]]
        if address == 0x400B and "amps" in meter:
            return [meter["amps"]]
        if address == 0x4025 and "product_code" in meter:
            return [meter["product_code"]]
        raise IneproReadError(f"Unexpected read {address:#06x} for slave {slave_id}")


async def test_async_read_grow_serial_number_reads_live_identity() -> None:
    """The shared discovery helper should own the live GROW serial-number read."""
    assert await async_read_grow_serial_number(_FakeIdentityClient(), slave_id=7) == (
        "075625480002"
    )


async def test_serial_bus_discovery_identifies_supported_pro_meters() -> None:
    """Bus scans should identify supported PRO meters without manual entry."""
    with patch.object(
        discovery_module,
        "IneproModbusClient",
        _FakeBusDiscoveryClient,
    ):
        meters = await async_discover_grow_serial_bus(
            {
                CONF_SERIAL_PORT: "COM1",
                CONF_BAUDRATE: 9600,
                CONF_BYTESIZE: 8,
                CONF_PARITY: "N",
                CONF_STOPBITS: 1,
                CONF_TIMEOUT: 1,
            },
            slave_id_start=1,
            slave_id_end=11,
        )

    assert [(meter.family, meter.variant, meter.serial_number) for meter in meters] == [
        (MeterFamily.PRO, "pro_1", "025425480001"),
        (MeterFamily.PRO, "pro_2", "028725480002"),
        (MeterFamily.PRO, "pro_380", "025725480102"),
        (MeterFamily.PRO, "pro_380ct", "026025480103"),
        (MeterFamily.PRO, "pro_1_solare", "025425480009"),
        (MeterFamily.PRO, "pro_2_solare", "028725480010"),
        (MeterFamily.PRO, "pro_380_solare", "025725480007"),
        (MeterFamily.PRO, "pro_380ct_solare", "026025480008"),
        (MeterFamily.PRO, "n_1", "051025483201"),
        (MeterFamily.PRO, "n_380_40a", "051425483203"),
        (MeterFamily.PRO, "n_380ct", "051625483204"),
    ]
    assert [meter.model_title for meter in meters] == [
        "PRO1",
        "PRO2",
        "PRO380",
        "PRO380CT",
        "PRO1 Solare",
        "PRO2 Solare",
        "PRO380 Solare",
        "PRO380CT Solare",
        "N1",
        "N380 40A",
        "N380 CT",
    ]


class _FailingGatewaySocket:
    """Socket double that fails when gateway broadcast discovery sends."""

    def setsockopt(self, *args, **kwargs):
        del args, kwargs

    def bind(self, *args, **kwargs):
        del args, kwargs

    def setblocking(self, *args, **kwargs):
        del args, kwargs

    def sendto(self, *args, **kwargs):
        del args, kwargs
        raise OSError("broadcast unavailable")

    def close(self):
        """Match the socket API used by discovery."""


def test_discover_tcp_gateways_returns_empty_when_socket_errors() -> None:
    """Gateway discovery should fail closed instead of raising from socket errors."""
    with patch.object(
        discovery_module.socket,
        "socket",
        return_value=_FailingGatewaySocket(),
    ):
        assert _discover_tcp_gateways(timeout=0.01) == ()


def test_tcp_gateway_udp_response_rejects_grow_meter_serial() -> None:
    """Ethernet-capable GROW meters must not be listed as TCP gateways."""
    message = bytearray(57)
    message[:6] = bytes.fromhex("00134D800085")
    message[17:29] = b"075625480002"

    assert (
        discovery_module._parse_tcp_gateway_discovery_response(
            bytes(message),
            host="192.168.68.76",
        )
        is None
    )


def test_tcp_gateway_udp_response_accepts_gateway_serial() -> None:
    """Real gateway serials from the UDP browse response should still be accepted."""
    message = bytearray(57)
    message[:6] = bytes.fromhex("00134D70010C")
    message[17:29] = b"033023260133"

    gateway = discovery_module._parse_tcp_gateway_discovery_response(
        bytes(message),
        host="192.168.68.85",
    )

    assert gateway == DiscoveredTcpGateway(
        host="192.168.68.85",
        mac_address="00:13:4D:70:01:0C",
        serial_number="033023260133",
    )


def test_expand_tcp_gateway_scan_target_accepts_ipv4_subnets() -> None:
    """Explicit IPv4 CIDR targets should expand to concrete host probes."""
    assert _expand_tcp_gateway_scan_target("10.5.2.0/30") == (
        "10.5.2.1",
        "10.5.2.2",
    )


async def test_async_discover_tcp_gateways_uses_explicit_probe_targets() -> None:
    """Explicit discovery targets should bypass UDP browse and probe the requested hosts."""
    expected = (
        DiscoveredTcpGateway(
            host="10.5.2.1",
            serial_number="033023260122",
        ),
    )

    with patch.object(
        discovery_module,
        "_async_probe_tcp_gateway_hosts",
        new=AsyncMock(return_value=expected),
    ) as probe_hosts:
        result = await async_discover_tcp_gateways(scan_target="10.5.2.0/30")

    assert result == expected
    probe_hosts.assert_awaited_once_with(
        ("10.5.2.1", "10.5.2.2"),
        timeout=discovery_module.TCP_GATEWAY_DISCOVERY_TIMEOUT,
    )


def test_candidate_ble_proxy_hosts_includes_resolver_nameserver() -> None:
    """Proxy host candidates should include the resolver nameserver."""
    with patch.object(
        discovery_module,
        "_read_default_route_gateway_host",
        return_value="172.28.224.1",
    ), patch.object(
        discovery_module,
        "_read_resolver_nameserver_host",
        return_value="10.255.255.254",
    ):
        hosts = discovery_module._candidate_ble_proxy_hosts(
            discovery_module.DEFAULT_BLUETOOTH_PROXY_HOST
        )

    assert hosts == ("localhost", "172.28.224.1", "10.255.255.254")


async def test_proxy_discovery_falls_back_to_gateway_host() -> None:
    """Proxy discovery should retry through the gateway host when localhost fails."""
    request_mock = AsyncMock(
        side_effect=[
            None,
            {
                "ok": True,
                "devices": [
                    {
                        "address": "80:F1:B2:58:DD:5A",
                        "name": "IM-075625480002",
                        "rssi": -88,
                    }
                ],
            },
        ]
    )

    with patch.object(
        discovery_module,
        "_read_default_route_gateway_host",
        return_value="172.28.224.1",
    ), patch.object(
        discovery_module,
        "_read_resolver_nameserver_host",
        return_value="10.255.255.254",
    ), patch.object(
        discovery_module,
        "_async_request_ble_proxy_scan",
        new=request_mock,
    ):
        meters = await async_discover_grow_bluetooth_proxy_meters(
            host=discovery_module.DEFAULT_BLUETOOTH_PROXY_HOST,
            port=discovery_module.DEFAULT_BLUETOOTH_PROXY_PORT,
            timeout=5.0,
        )

    assert len(meters) == 1
    meter = meters[0]
    assert meter.serial_number == "075625480002"
    assert meter.address == "80:F1:B2:58:DD:5A"
    assert meter.transport is discovery_module.TransportType.BLUETOOTH_PROXY
    assert meter.proxy_host == "172.28.224.1"
    assert meter.proxy_port == discovery_module.DEFAULT_BLUETOOTH_PROXY_PORT
    assert request_mock.await_args_list[0].kwargs == {
        "host": "localhost",
        "port": discovery_module.DEFAULT_BLUETOOTH_PROXY_PORT,
        "timeout": 5.0,
    }
    assert request_mock.await_args_list[1].kwargs == {
        "host": "172.28.224.1",
        "port": discovery_module.DEFAULT_BLUETOOTH_PROXY_PORT,
        "timeout": 5.0,
    }
