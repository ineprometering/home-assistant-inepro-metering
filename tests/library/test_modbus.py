"""Tests for the standalone Inepro Metering Modbus transport helpers."""

from __future__ import annotations

import asyncio
import json
from types import ModuleType

import pytest

from inepro_metering.ble import (
    FUNCTION_ENCAPSULATED_INTERFACE,
    FUNCTION_READ_HOLDING_REGISTERS,
    build_rtu_frame,
)
from inepro_metering import modbus


class _FakeSerialInstance:
    """Minimal fake serial instance returned by a cached URL handler."""

    def __init__(self, port, *args, **kwargs) -> None:
        """Record constructor arguments the way pyserial transport expects."""
        self.initial_port = port
        self.args = args
        self.kwargs = kwargs
        self.port = port
        self.open_calls = 0

    def open(self) -> None:
        """Track whether the cached dispatcher opened the handler."""
        self.open_calls += 1


class _FakeDeviceIdentificationResponse:
    """Minimal fake pymodbus device-identification response."""

    def __init__(
        self,
        information: dict[int, bytes],
        *,
        conformity: int = 0x81,
        more_follows: int = 0,
        next_object_id: int = 0,
    ) -> None:
        """Store the returned object dictionary."""
        self.information = information
        self.conformity = conformity
        self.more_follows = more_follows
        self.next_object_id = next_object_id

    def isError(self) -> bool:
        """Mimic pymodbus' success response API."""
        return False


class _FakeClientWithDeviceIdentification:
    """Minimal fake client exposing pymodbus-style read_device_information."""

    def __init__(self) -> None:
        """Initialize the fake connected client."""
        self.connected = True
        self.calls: list[tuple[int, int, int]] = []

    async def read_device_information(
        self,
        *,
        read_code: int | None = None,
        object_id: int = 0,
        device_id: int = 1,
        no_response_expected: bool = False,
    ) -> _FakeDeviceIdentificationResponse:
        """Return a deterministic set of device-identification objects."""
        del no_response_expected
        self.calls.append((int(read_code or 0), object_id, device_id))
        return _FakeDeviceIdentificationResponse(
            {
                0x00: b"inepro Metering B.V.\x00",
                0x01: b"879-3120\x00",
                0x02: b"V1.0.2744\x00",
            }
        )


class _FakePagedClientWithDeviceIdentification:
    """Fake client that returns paged 43/14 responses."""

    def __init__(self) -> None:
        """Initialize the fake connected client."""
        self.connected = True
        self.calls: list[tuple[int, int, int]] = []

    async def read_device_information(
        self,
        *,
        read_code: int | None = None,
        object_id: int = 0,
        device_id: int = 1,
        no_response_expected: bool = False,
    ) -> _FakeDeviceIdentificationResponse:
        """Return two response pages for regular or extended reads."""
        del no_response_expected
        self.calls.append((int(read_code or 0), object_id, device_id))

        if object_id == 0x00:
            return _FakeDeviceIdentificationResponse(
                {
                    0x00: b"inepro Metering B.V.\x00",
                    0x01: b"TCP Gateway\x00",
                    0x02: b"V1.0.973\x00",
                    0x04: b"Ambition Modbus TCP Gateway\x00",
                },
                conformity=0x83,
                more_follows=0xFF,
                next_object_id=0x80,
            )

        if object_id == 0x80:
            return _FakeDeviceIdentificationResponse(
                {
                    0x80: b"033023260122\x00",
                    0x81: b"1.0.845\x00",
                },
                conformity=0x83,
                more_follows=0x00,
                next_object_id=0x00,
            )

        raise AssertionError(f"Unexpected object id {object_id:#04x}")


class _FakeRegisterResponse:
    """Minimal fake register response for read/write verification tests."""

    def __init__(self, registers: list[int] | None = None) -> None:
        """Store raw 16-bit register values."""
        self.registers = list(registers or [])

    def isError(self) -> bool:
        """Mimic pymodbus' success response API."""
        return False


class _FakeWritableClient:
    """Minimal fake client that supports write verification retries."""

    def __init__(self) -> None:
        """Initialize a connected fake client with one writable register."""
        self.connected = True
        self.read_values: list[int] = [0]
        self.write_calls: list[tuple[str, int, list[int], int]] = []
        self.read_calls: list[tuple[int, int, int]] = []

    async def write_register(self, address: int, value: int, *, device_id: int):
        """Record a single-register write."""
        self.write_calls.append(("single", address, [value], device_id))
        return _FakeRegisterResponse()

    async def write_registers(self, address: int, values: list[int], *, device_id: int):
        """Record a multi-register write."""
        self.write_calls.append(("multiple", address, list(values), device_id))
        return _FakeRegisterResponse()

    async def read_holding_registers(self, address: int, *, count: int, device_id: int):
        """Return the next queued verification value."""
        self.read_calls.append((address, count, device_id))
        values = self.read_values[:count]
        if len(values) < count:
            values.extend([0] * (count - len(values)))
        return _FakeRegisterResponse(values)


class _FakeGatewayRegisterClient:
    """Fake client that exposes the gateway metadata register block."""

    def __init__(self) -> None:
        """Initialize the fake connected client."""
        self.connected = True
        self.read_calls: list[tuple[int, int, int]] = []

    async def read_holding_registers(self, address: int, *, count: int, device_id: int):
        """Return the vendor-specific gateway identification block."""
        self.read_calls.append((address, count, device_id))
        if (address, count, device_id) != (1024, 13, 255):
            raise AssertionError(f"Unexpected gateway read {(address, count, device_id)}")
        return _FakeRegisterResponse(
            [
                330,  # device type
                1,  # hardware version
                5,  # firmware type
                1,
                0,
                973,
                845,
                0,
                0x0330,
                0x2326,
                0x0122,
                1,
                0,
            ]
        )


class _FakeProxyReader:
    """Minimal line-based reader for BLE proxy responses."""

    def __init__(self, payloads: list[dict[str, object]]) -> None:
        """Initialize the fake reader with a queue of JSON payloads."""
        self._payloads = [
            json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"
            for payload in payloads
        ]

    async def readline(self) -> bytes:
        """Return one queued JSON line."""
        if not self._payloads:
            return b""
        return self._payloads.pop(0)


class _FakeProxyWriter:
    """Minimal writer that captures one JSON request per call."""

    def __init__(self, requests: list[dict[str, object]]) -> None:
        """Store requests into the provided list."""
        self._requests = requests

    def write(self, data: bytes) -> None:
        """Record one JSON request payload."""
        self._requests.append(json.loads(data.decode("utf-8")))

    async def drain(self) -> None:
        """Match the asyncio StreamWriter API."""

    def close(self) -> None:
        """Match the asyncio StreamWriter API."""

    async def wait_closed(self) -> None:
        """Match the asyncio StreamWriter API."""


@pytest.fixture
def restore_serial_dispatch(monkeypatch: pytest.MonkeyPatch):
    """Restore pyserial's URL dispatcher after each cached-dispatch test."""
    import serial

    original = serial.serial_for_url
    marker = getattr(serial, "_inepro_cached_serial_for_url_installed", False)
    monkeypatch.setattr(serial, "serial_for_url", original)
    monkeypatch.setattr(
        serial,
        "_inepro_cached_serial_for_url_installed",
        marker,
        raising=False,
    )
    yield serial
    monkeypatch.setattr(serial, "serial_for_url", original)
    monkeypatch.setattr(
        serial,
        "_inepro_cached_serial_for_url_installed",
        marker,
        raising=False,
    )


def test_cached_serial_url_dispatch_uses_preloaded_handler_modules(
    monkeypatch: pytest.MonkeyPatch,
    restore_serial_dispatch,
) -> None:
    """Cached URL dispatch should avoid the original pyserial import path."""
    serial = restore_serial_dispatch
    fallback_calls: list[tuple[str, tuple, dict]] = []

    def _unexpected_fallback(url, *args, **kwargs):
        fallback_calls.append((url, args, kwargs))
        raise AssertionError("serial.serial_for_url fallback should not be used")

    monkeypatch.setattr(serial, "serial_for_url", _unexpected_fallback)
    monkeypatch.setattr(
        serial,
        "_inepro_cached_serial_for_url_installed",
        False,
        raising=False,
    )

    package_module = ModuleType("serial.urlhandler")
    handler_module = ModuleType("serial.urlhandler.protocol_socket")

    def _serial_class_for_url(url: str):
        return url, _FakeSerialInstance

    handler_module.serial_class_for_url = _serial_class_for_url
    monkeypatch.setitem(modbus.sys.modules, "serial.urlhandler", package_module)
    monkeypatch.setitem(
        modbus.sys.modules,
        "serial.urlhandler.protocol_socket",
        handler_module,
    )

    modbus._install_cached_serial_url_dispatch()

    instance = serial.serial_for_url("socket://127.0.0.1:15025", baudrate=9600)

    assert isinstance(instance, _FakeSerialInstance)
    assert instance.initial_port is None
    assert instance.port == "socket://127.0.0.1:15025"
    assert instance.kwargs["baudrate"] == 9600
    assert instance.open_calls == 1
    assert fallback_calls == []


def test_cached_serial_url_dispatch_falls_back_for_unknown_scheme(
    monkeypatch: pytest.MonkeyPatch,
    restore_serial_dispatch,
) -> None:
    """Unknown schemes should continue through pyserial's original dispatcher."""
    serial = restore_serial_dispatch
    fallback_calls: list[tuple[str, tuple, dict]] = []

    def _fallback(url, *args, **kwargs):
        fallback_calls.append((url, args, kwargs))
        return "fallback-result"

    monkeypatch.setattr(serial, "serial_for_url", _fallback)
    monkeypatch.setattr(
        serial,
        "_inepro_cached_serial_for_url_installed",
        False,
        raising=False,
    )

    modbus._install_cached_serial_url_dispatch()

    result = serial.serial_for_url("loop://", timeout=3, do_not_open=True)

    assert result == "fallback-result"
    assert fallback_calls == [("loop://", (), {"timeout": 3, "do_not_open": True})]


async def test_async_read_device_identification_decodes_basic_objects() -> None:
    """The shared Modbus wrapper should decode Modbus 43/14 object strings."""
    fake_client = _FakeClientWithDeviceIdentification()
    client = modbus.IneproModbusClient(
        {
            modbus.CONF_TRANSPORT: modbus.TransportType.TCP_ETHERNET.value,
            modbus.CONF_HOST: "192.0.2.10",
            modbus.CONF_PORT: 502,
            modbus.CONF_TIMEOUT: 3,
        }
    )
    client._client = fake_client

    identification = await client.async_read_device_identification(157)

    assert fake_client.calls == [(modbus.DEVICE_INFORMATION_BASIC, 0, 157)]
    assert identification.manufacturer_name == "inepro Metering B.V."
    assert identification.product_name == "879-3120"
    assert identification.version == "V1.0.2744"
    assert identification.as_readings() == {
        "modbus_manufacturer_name": "inepro Metering B.V.",
        "modbus_product_name": "879-3120",
        "modbus_device_version": "V1.0.2744",
    }


async def test_async_read_device_identification_objects_collects_paged_extended_data() -> None:
    """The shared Modbus wrapper should follow paged 43/14 responses."""
    fake_client = _FakePagedClientWithDeviceIdentification()
    client = modbus.IneproModbusClient(
        {
            modbus.CONF_TRANSPORT: modbus.TransportType.TCP_GATEWAY.value,
            modbus.CONF_HOST: "192.0.2.20",
            modbus.CONF_PORT: 502,
            modbus.CONF_TIMEOUT: 3,
        }
    )
    client._client = fake_client

    result = await client.async_read_device_identification_objects(
        255,
        read_code=modbus.DEVICE_INFORMATION_EXTENDED,
    )

    assert fake_client.calls == [
        (modbus.DEVICE_INFORMATION_EXTENDED, 0x00, 255),
        (modbus.DEVICE_INFORMATION_EXTENDED, 0x80, 255),
    ]
    assert result.conformity_level == 0x83
    assert result.objects == {
        0x00: "inepro Metering B.V.",
        0x01: "TCP Gateway",
        0x02: "V1.0.973",
        0x04: "Ambition Modbus TCP Gateway",
        0x80: "033023260122",
        0x81: "1.0.845",
    }


async def test_async_read_tcp_gateway_info_decodes_vendor_registers() -> None:
    """The shared Modbus wrapper should decode the vendor gateway info block."""
    fake_client = _FakeGatewayRegisterClient()
    client = modbus.IneproModbusClient(
        {
            modbus.CONF_TRANSPORT: modbus.TransportType.TCP_GATEWAY.value,
            modbus.CONF_HOST: "192.0.2.20",
            modbus.CONF_PORT: 502,
            modbus.CONF_TIMEOUT: 3,
        }
    )
    client._client = fake_client

    result = await client.async_read_tcp_gateway_info()

    assert fake_client.read_calls == [(1024, 13, 255)]
    assert result.device_type_code == 330
    assert result.device_type == "TCP Gateway"
    assert result.hardware_version == "1"
    assert result.serial_number == "033023260122"
    assert result.firmware_type == 5
    assert result.firmware_version == "1.0.973"
    assert result.bootloader_version == "1.0.845"
    assert result.as_readings() == {
        "tcp_gateway_device_type_code": 330,
        "tcp_gateway_device_type": "TCP Gateway",
        "tcp_gateway_hardware_version": "1",
        "tcp_gateway_serial_number": "033023260122",
        "tcp_gateway_firmware_type": 5,
        "tcp_gateway_firmware_version": "1.0.973",
        "tcp_gateway_bootloader_version": "1.0.845",
    }


async def test_bluetooth_proxy_transport_reads_registers_through_tcp_bridge() -> None:
    """The Windows BLE proxy transport should round-trip one Modbus read."""
    requests: list[dict[str, object]] = []
    response_payloads = [
        {"ok": True},
        {
            "ok": True,
            "response": build_rtu_frame(
                1,
                FUNCTION_READ_HOLDING_REGISTERS,
                bytes([4, 0x25, 0x10, 0x00, 0x01]),
            ).hex(),
        },
    ]

    async def _open_connection(_host: str, _port: int):
        return _FakeProxyReader([response_payloads.pop(0)]), _FakeProxyWriter(requests)

    client = modbus.IneproModbusClient(
        {
            modbus.CONF_TRANSPORT: modbus.TransportType.BLUETOOTH_PROXY.value,
            modbus.CONF_HOST: "127.0.0.1",
            modbus.CONF_PORT: 15026,
            modbus.CONF_BLUETOOTH_ADDRESS: "AA:BB:CC:DD:EE:FF",
            modbus.CONF_BLUETOOTH_NAME: "IM-075625100001",
            modbus.CONF_TIMEOUT: 3,
        }
    )
    original_open_connection = asyncio.open_connection
    asyncio.open_connection = _open_connection

    try:
        registers = await client.async_read_registers(
            modbus.RegisterType.HOLDING,
            0x4000,
            2,
            1,
        )
    finally:
        asyncio.open_connection = original_open_connection
        await client.async_close()

    assert registers == [0x2510, 0x0001]
    assert requests == [
        {"action": "ping"},
        {
            "action": "transceive",
            "address": "AA:BB:CC:DD:EE:FF",
            "name": "IM-075625100001",
            "timeout": 3.0,
            "frame": "010340000002d1cb",
        },
    ]


async def test_bluetooth_proxy_transport_reads_device_identification() -> None:
    """The Windows BLE proxy transport should support Modbus 43/14."""
    requests: list[dict[str, object]] = []
    response_payloads = [
        {"ok": True},
        {
            "ok": True,
            "response": build_rtu_frame(
                157,
                FUNCTION_ENCAPSULATED_INTERFACE,
                (
                    bytes([0x0E, 0x01, 0x01, 0x00, 0x00, 0x03])
                    + bytes([0x00, 0x14])
                    + b"inepro Metering B.V."
                    + bytes([0x01, 0x08])
                    + b"879-3120"
                    + bytes([0x02, 0x09])
                    + b"V1.0.2744"
                ),
            ).hex(),
        },
    ]

    async def _open_connection(_host: str, _port: int):
        return _FakeProxyReader([response_payloads.pop(0)]), _FakeProxyWriter(requests)

    client = modbus.IneproModbusClient(
        {
            modbus.CONF_TRANSPORT: modbus.TransportType.BLUETOOTH_PROXY.value,
            modbus.CONF_HOST: "127.0.0.1",
            modbus.CONF_PORT: 15026,
            modbus.CONF_BLUETOOTH_ADDRESS: "11:22:33:44:55:66",
            modbus.CONF_BLUETOOTH_NAME: "IM-075625100001",
            modbus.CONF_TIMEOUT: 3,
        }
    )
    original_open_connection = asyncio.open_connection
    asyncio.open_connection = _open_connection

    try:
        identification = await client.async_read_device_identification(157)
    finally:
        asyncio.open_connection = original_open_connection
        await client.async_close()

    assert identification.manufacturer_name == "inepro Metering B.V."
    assert identification.product_name == "879-3120"
    assert identification.version == "V1.0.2744"
    assert requests[0] == {"action": "ping"}
    assert requests[1]["action"] == "transceive"
    assert requests[1]["address"] == "11:22:33:44:55:66"


async def test_async_write_register_verifies_by_reading_back_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Writes should read the same holding register back before succeeding."""
    fake_client = _FakeWritableClient()
    fake_client.read_values = [1]
    client = modbus.IneproModbusClient(
        {
            modbus.CONF_TRANSPORT: modbus.TransportType.TCP_ETHERNET.value,
            modbus.CONF_HOST: "192.0.2.10",
            modbus.CONF_PORT: 502,
            modbus.CONF_TIMEOUT: 3,
        }
    )

    async def _ensure_connected():
        return fake_client

    async def _reset_client():
        return None

    monkeypatch.setattr(client, "_async_ensure_connected", _ensure_connected)
    monkeypatch.setattr(client, "_async_reset_client", _reset_client)

    await client.async_write_register(0x4C06, 1, 157)

    assert fake_client.write_calls == [("single", 0x4C06, [1], 157)]
    assert fake_client.read_calls == [(0x4C06, 1, 157)]


async def test_async_write_register_retries_until_verification_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A write should retry when the immediate read-back value is stale."""
    clients = [_FakeWritableClient(), _FakeWritableClient()]
    clients[0].read_values = [0]
    clients[1].read_values = [1]
    client = modbus.IneproModbusClient(
        {
            modbus.CONF_TRANSPORT: modbus.TransportType.TCP_ETHERNET.value,
            modbus.CONF_HOST: "192.0.2.10",
            modbus.CONF_PORT: 502,
            modbus.CONF_TIMEOUT: 3,
        }
    )
    ensure_calls = {"count": 0}
    reset_calls = {"count": 0}

    async def _ensure_connected():
        index = min(ensure_calls["count"], len(clients) - 1)
        ensure_calls["count"] += 1
        return clients[index]

    async def _reset_client():
        reset_calls["count"] += 1
        return None

    monkeypatch.setattr(client, "_async_ensure_connected", _ensure_connected)
    monkeypatch.setattr(client, "_async_reset_client", _reset_client)
    original_sleep = asyncio.sleep
    monkeypatch.setattr(modbus.asyncio, "sleep", lambda _: original_sleep(0))

    await client.async_write_register(0x4C06, 1, 157)

    assert clients[0].write_calls == [("single", 0x4C06, [1], 157)]
    assert clients[0].read_calls == [(0x4C06, 1, 157)]
    assert clients[1].write_calls == [("single", 0x4C06, [1], 157)]
    assert clients[1].read_calls == [(0x4C06, 1, 157)]
    assert reset_calls["count"] == 1


async def test_async_write_registers_verifies_full_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Multi-register writes should verify the full written block."""
    fake_client = _FakeWritableClient()
    fake_client.read_values = [0x496E, 0x6570, 0x726F]
    client = modbus.IneproModbusClient(
        {
            modbus.CONF_TRANSPORT: modbus.TransportType.TCP_ETHERNET.value,
            modbus.CONF_HOST: "192.0.2.10",
            modbus.CONF_PORT: 502,
            modbus.CONF_TIMEOUT: 3,
        }
    )

    async def _ensure_connected():
        return fake_client

    async def _reset_client():
        return None

    monkeypatch.setattr(client, "_async_ensure_connected", _ensure_connected)
    monkeypatch.setattr(client, "_async_reset_client", _reset_client)

    await client.async_write_registers(0x4C32, [0x496E, 0x6570, 0x726F], 157)

    assert fake_client.write_calls == [
        ("multiple", 0x4C32, [0x496E, 0x6570, 0x726F], 157)
    ]
    assert fake_client.read_calls == [(0x4C32, 3, 157)]
