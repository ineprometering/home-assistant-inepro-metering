"""Tests for the GROW BLE Modbus RTU proxy transport."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from inepro_metering.ble import (
    DEVICE_INFORMATION_BLE_FIRMWARE_CHARACTERISTIC_UUID,
    DEVICE_INFORMATION_FIRMWARE_CHARACTERISTIC_UUID,
    DEVICE_INFORMATION_MANUFACTURER_CHARACTERISTIC_UUID,
    DEVICE_INFORMATION_MODEL_CHARACTERISTIC_UUID,
    DEVICE_INFORMATION_SERIAL_CHARACTERISTIC_UUID,
    FUNCTION_ENCAPSULATED_INTERFACE,
    FUNCTION_READ_HOLDING_REGISTERS,
    FUNCTION_WRITE_MULTIPLE_REGISTERS,
    FUNCTION_WRITE_SINGLE_REGISTER,
    IneproBlePairingFailedError,
    IneproBlePairingUnsupportedError,
    MODBUS_NOTIFY_CHARACTERISTIC_UUID,
    MODBUS_WRITE_CHARACTERISTIC_UUID,
    WINDOWS_WINRT_ARGS,
    async_read_ble_device_information_only,
    build_rtu_frame,
    is_ble_pairing_trigger_error,
)
from inepro_metering.const import TransportType
from inepro_metering.modbus import (
    BLUETOOTH_PAIRING_MODE_AUTO,
    BLUETOOTH_PAIRING_MODE_NEVER,
    BLUETOOTH_PAIRING_MODE_REQUIRED,
    CONF_BLE_CLIENT_FACTORY,
    CONF_BLUETOOTH_ADDRESS,
    CONF_BLUETOOTH_DEVICE_RESOLVER,
    CONF_BLUETOOTH_FORCE_REPAIR,
    CONF_BLUETOOTH_PAIRING_MODE,
    CONF_BLUETOOTH_PAIRING_PIN,
    CONF_BLUETOOTH_PAIRING_TIMEOUT,
    CONF_TIMEOUT,
    CONF_TRANSPORT,
    IneproBluetoothNotPairedError,
    IneproConnectionError,
    IneproModbusClient,
    IneproReadError,
    IneproWriteError,
)
from inepro_metering.models import RegisterType


class FakeServices:
    """Small service collection exposing selected characteristic UUIDs."""

    def __init__(self, *uuids: str, max_write_size: int = 20) -> None:
        self._characteristics = {
            uuid: SimpleNamespace(
                uuid=uuid,
                max_write_without_response_size=max_write_size,
            )
            for uuid in uuids
        }

    def get_characteristic(self, uuid: str):
        """Return a fake characteristic by UUID."""
        return self._characteristics.get(uuid)


class FakeBleakClient:
    """Fake Bleak client that answers Modbus RTU requests through notifications."""

    instances: list["FakeBleakClient"] = []

    def __init__(self, target, *, timeout, pair, winrt=None):
        self.target = target
        self.timeout = timeout
        self.pair_arg = pair
        self.winrt_arg = winrt
        self.services = FakeServices(
            MODBUS_NOTIFY_CHARACTERISTIC_UUID,
            MODBUS_WRITE_CHARACTERISTIC_UUID,
            DEVICE_INFORMATION_MODEL_CHARACTERISTIC_UUID,
            DEVICE_INFORMATION_SERIAL_CHARACTERISTIC_UUID,
            DEVICE_INFORMATION_FIRMWARE_CHARACTERISTIC_UUID,
            DEVICE_INFORMATION_BLE_FIRMWARE_CHARACTERISTIC_UUID,
            DEVICE_INFORMATION_MANUFACTURER_CHARACTERISTIC_UUID,
        )
        self.pair_calls = 0
        self.unpair_calls = 0
        self.start_notify_calls = 0
        self.stop_notify_calls = 0
        self.is_connected = False
        self.notify_callback = None
        self.write_attempts = 0
        self.writes: list[tuple[str, bytes, bool]] = []
        self.registers: dict[int, int] = {
            0x4000: 0x2510,
            0x4001: 0x0001,
            0x4C06: 0x0000,
        }
        self.instances.append(self)

    async def connect(self):
        """Pretend to connect successfully."""
        self.is_connected = True
        return True

    async def start_notify(self, uuid, callback):
        """Store the notification callback."""
        assert uuid == MODBUS_NOTIFY_CHARACTERISTIC_UUID
        self.start_notify_calls += 1
        self.notify_callback = callback

    async def stop_notify(self, uuid):
        """Pretend to unsubscribe."""
        assert uuid == MODBUS_NOTIFY_CHARACTERISTIC_UUID
        self.stop_notify_calls += 1

    async def disconnect(self):
        """Pretend to disconnect."""
        self.is_connected = False

    async def pair(self):
        """Pretend to pair successfully."""
        self.pair_calls += 1

    async def unpair(self):
        """Pretend to clear an existing bond."""
        self.unpair_calls += 1

    async def read_gatt_char(self, uuid):
        """Return fake BLE Device Information values."""
        values = {
            DEVICE_INFORMATION_MODEL_CHARACTERISTIC_UUID: b"879-3120",
            DEVICE_INFORMATION_SERIAL_CHARACTERISTIC_UUID: b"075625100001",
            DEVICE_INFORMATION_FIRMWARE_CHARACTERISTIC_UUID: b"V1.0.2744",
            DEVICE_INFORMATION_BLE_FIRMWARE_CHARACTERISTIC_UUID: b"V0.4.1",
            DEVICE_INFORMATION_MANUFACTURER_CHARACTERISTIC_UUID: b"inepro Metering B.V.",
        }
        return values[uuid]

    async def write_gatt_char(self, uuid, data, *, response):
        """Record the request and publish the matching Modbus response."""
        assert uuid == MODBUS_WRITE_CHARACTERISTIC_UUID
        self.write_attempts += 1
        self.writes.append((uuid, bytes(data), response))
        self._publish_modbus_response(bytes(data))

    def _publish_modbus_response(self, request: bytes) -> None:
        """Publish the matching Modbus response for one fake request."""
        slave_id = request[0]
        function = request[1]
        if function == FUNCTION_READ_HOLDING_REGISTERS:
            address = int.from_bytes(request[2:4], "big")
            count = int.from_bytes(request[4:6], "big")
            register_bytes = b"".join(
                int(self.registers.get(address + offset, 0)).to_bytes(2, "big")
                for offset in range(count)
            )
            payload = bytes([len(register_bytes)]) + register_bytes
            reply = build_rtu_frame(slave_id, function, payload)
        elif function == FUNCTION_ENCAPSULATED_INTERFACE:
            payload = (
                bytes([0x0E, 0x01, 0x01, 0x00, 0x00, 0x03])
                + bytes([0x00, 0x14])
                + b"inepro Metering B.V."
                + bytes([0x01, 0x08])
                + b"879-3120"
                + bytes([0x02, 0x09])
                + b"V1.0.2744"
            )
            reply = build_rtu_frame(slave_id, function, payload)
        elif function == FUNCTION_WRITE_SINGLE_REGISTER:
            address = int.from_bytes(request[2:4], "big")
            value = int.from_bytes(request[4:6], "big")
            self.registers[address] = value
            reply = build_rtu_frame(slave_id, function, request[2:6])
        elif function == FUNCTION_WRITE_MULTIPLE_REGISTERS:
            address = int.from_bytes(request[2:4], "big")
            count = int.from_bytes(request[4:6], "big")
            byte_count = request[6]
            payload = request[7 : 7 + byte_count]
            for offset in range(count):
                start = offset * 2
                self.registers[address + offset] = int.from_bytes(
                    payload[start : start + 2],
                    "big",
                )
            reply = build_rtu_frame(slave_id, function, request[2:6])
        else:
            raise AssertionError(f"Unexpected function: {function}")

        self.notify_callback(MODBUS_NOTIFY_CHARACTERISTIC_UUID, reply)


class EncryptionRequiredFakeBleakClient(FakeBleakClient):
    """Fake client that requires pairing before the first write succeeds."""

    bonded_targets: set[object] = set()

    async def pair(self):
        """Pretend to pair successfully and remember the OS bond."""
        await super().pair()
        self.bonded_targets.add(self.target)

    async def unpair(self):
        """Pretend to clear an existing bond."""
        await super().unpair()
        self.bonded_targets.discard(self.target)

    async def write_gatt_char(self, uuid, data, *, response):
        """Fail the first write until the client pairs, then answer normally."""
        assert uuid == MODBUS_WRITE_CHARACTERISTIC_UUID
        self.write_attempts += 1
        if (
            not self.pair_arg
            and self.pair_calls == 0
            and self.target not in self.bonded_targets
        ):
            raise RuntimeError("GATT Protocol Error: Insufficient Encryption")

        self.write_attempts -= 1
        await super().write_gatt_char(uuid, data, response=response)


class TimeoutUntilPairFakeBleakClient(FakeBleakClient):
    """Fake client that accepts the first write but only answers after pairing."""

    bonded_targets: set[object] = set()

    async def pair(self):
        """Pretend to pair successfully and remember the OS bond."""
        await super().pair()
        self.bonded_targets.add(self.target)

    async def write_gatt_char(self, uuid, data, *, response):
        """Drop notifications until the client has paired."""
        assert uuid == MODBUS_WRITE_CHARACTERISTIC_UUID
        self.write_attempts += 1
        self.writes.append((uuid, bytes(data), response))
        if self.pair_calls == 0 and self.target not in self.bonded_targets:
            return

        self._publish_modbus_response(bytes(data))


class NotConnectedFirstWriteFakeBleakClient(EncryptionRequiredFakeBleakClient):
    """Fake client that drops connection on first encrypted write."""

    async def write_gatt_char(self, uuid, data, *, response):
        """Fail like a backend that reports disconnection instead of auth."""
        assert uuid == MODBUS_WRITE_CHARACTERISTIC_UUID
        self.write_attempts += 1
        if (
            not self.pair_arg
            and self.pair_calls == 0
            and self.target not in self.bonded_targets
        ):
            self.is_connected = False
            raise RuntimeError("Cancel send, because not connected!")

        self.write_attempts -= 1
        await FakeBleakClient.write_gatt_char(self, uuid, data, response=response)


class MissingWriteCharacteristicFakeBleakClient(FakeBleakClient):
    """Fake client with incomplete GATT services."""

    def __init__(self, target, *, timeout, pair, winrt=None):
        super().__init__(target, timeout=timeout, pair=pair, winrt=winrt)
        self.services = FakeServices(MODBUS_NOTIFY_CHARACTERISTIC_UUID)


class MissingNotifyCharacteristicFakeBleakClient(FakeBleakClient):
    """Fake client without the notification characteristic."""

    def __init__(self, target, *, timeout, pair, winrt=None):
        super().__init__(target, timeout=timeout, pair=pair, winrt=winrt)
        self.services = FakeServices(MODBUS_WRITE_CHARACTERISTIC_UUID)


class PairingUnsupportedFakeBleakClient(EncryptionRequiredFakeBleakClient):
    """Fake backend that cannot accept explicit pair=True."""

    def __init__(self, target, *, timeout, pair, winrt=None):
        if pair:
            raise TypeError("unexpected keyword argument 'pair'")
        super().__init__(target, timeout=timeout, pair=pair, winrt=winrt)

    async def pair(self):
        """Report that the active backend cannot pair."""
        raise RuntimeError("pairing not supported")


class PairingFailsFakeBleakClient(EncryptionRequiredFakeBleakClient):
    """Fake meter/backend where pairing still fails to unlock encrypted writes."""

    async def write_gatt_char(self, uuid, data, *, response):
        """Keep failing encrypted writes even when pair=True was used."""
        assert uuid == MODBUS_WRITE_CHARACTERISTIC_UUID
        self.write_attempts += 1
        raise RuntimeError("GATT Protocol Error: Insufficient Encryption")


class FailsFirstConnectFakeBleakClient(FakeBleakClient):
    """Fake client that fails the first connect and succeeds on retry."""

    async def connect(self):
        """Fail the first instance, then connect normally."""
        if len(self.instances) == 1:
            self.is_connected = False
            return False
        return await super().connect()


def test_build_rtu_frame_uses_confirmed_modbus_crc() -> None:
    """BLE requests should wrap the same RTU frame shown in the Inepro deck."""
    assert (
        build_rtu_frame(1, FUNCTION_READ_HOLDING_REGISTERS, bytes.fromhex("40000002"))
        == bytes.fromhex("010340000002D1CB")
    )


def test_ble_pairing_trigger_error_accepts_bluez_att_security_codes() -> None:
    """BlueZ may report encrypted writes as numeric ATT security errors."""
    assert is_ble_pairing_trigger_error(
        RuntimeError("org.bluez.Error.Failed: Operation failed with ATT error: 0x05")
    )
    assert is_ble_pairing_trigger_error(
        RuntimeError("org.bluez.Error.Failed: Operation failed with ATT error: 0x0c")
    )
    assert is_ble_pairing_trigger_error(
        RuntimeError("org.bluez.Error.NotPermitted: Attribute requires security")
    )
    assert not is_ble_pairing_trigger_error(
        TimeoutError("Timed out waiting for BLE Modbus response from IM-075625100001")
    )


async def test_ble_modbus_client_reads_registers_from_notification() -> None:
    """The BLE transport should decode Modbus read replies from FFE4."""
    FakeBleakClient.instances.clear()
    client = IneproModbusClient(
        {
            CONF_TRANSPORT: TransportType.BLUETOOTH.value,
            CONF_BLUETOOTH_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_TIMEOUT: 3,
            CONF_BLE_CLIENT_FACTORY: FakeBleakClient,
        }
    )

    try:
        registers = await client.async_read_registers(
            RegisterType.HOLDING,
            0x4000,
            2,
            1,
        )
    finally:
        await client.async_close()

    fake_client = FakeBleakClient.instances[0]
    assert fake_client.target == "AA:BB:CC:DD:EE:FF"
    assert fake_client.pair_arg is False
    assert fake_client.pair_calls == 0
    assert registers == [0x2510, 0x0001]
    assert fake_client.writes == [
        (
            MODBUS_WRITE_CHARACTERISTIC_UUID,
            bytes.fromhex("010340000002D1CB"),
            True,
        )
    ]


async def test_ble_modbus_client_reads_gatt_device_information_before_modbus() -> None:
    """GROW setup can read GATT Device Information before any FFE9 write."""
    FakeBleakClient.instances.clear()
    client = IneproModbusClient(
        {
            CONF_TRANSPORT: TransportType.BLUETOOTH.value,
            CONF_BLUETOOTH_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_TIMEOUT: 3,
            CONF_BLE_CLIENT_FACTORY: FakeBleakClient,
        }
    )

    try:
        info = await client.async_read_bluetooth_device_information()
    finally:
        await client.async_close()

    fake_client = FakeBleakClient.instances[0]
    assert info.model == "879-3120"
    assert info.serial_number == "075625100001"
    assert info.firmware_version == "V1.0.2744"
    assert info.ble_firmware_version == "V0.4.1"
    assert info.manufacturer == "inepro Metering B.V."
    assert fake_client.writes == []


async def test_ble_device_information_only_does_not_touch_modbus_service() -> None:
    """The GATT-only precheck should not pair, subscribe, or write FFE9."""
    FakeBleakClient.instances.clear()

    info = await async_read_ble_device_information_only(
        address="AA:BB:CC:DD:EE:FF",
        name="IM-075625100001",
        timeout=10,
        client_factory=FakeBleakClient,
    )

    fake_client = FakeBleakClient.instances[0]
    assert info.serial_number == "075625100001"
    assert fake_client.pair_arg is False
    assert fake_client.pair_calls == 0
    assert fake_client.notify_callback is None
    assert fake_client.writes == []
    assert fake_client.is_connected is False


async def test_ble_modbus_client_uses_uncached_services_on_windows() -> None:
    """Windows BLE sessions should force uncached service discovery."""
    FakeBleakClient.instances.clear()
    client = IneproModbusClient(
        {
            CONF_TRANSPORT: TransportType.BLUETOOTH.value,
            CONF_BLUETOOTH_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_TIMEOUT: 3,
            CONF_BLE_CLIENT_FACTORY: FakeBleakClient,
        }
    )

    try:
        with patch("inepro_metering.ble.platform.system", return_value="Windows"):
            registers = await client.async_read_registers(
                RegisterType.HOLDING,
                0x4000,
                2,
                1,
            )
    finally:
        await client.async_close()

    fake_client = FakeBleakClient.instances[0]
    assert registers == [0x2510, 0x0001]
    assert fake_client.winrt_arg == WINDOWS_WINRT_ARGS


async def test_ble_modbus_client_pairs_after_insufficient_encryption() -> None:
    """The BLE transport should pair and retry when FFE9 requires encryption."""
    EncryptionRequiredFakeBleakClient.instances.clear()
    EncryptionRequiredFakeBleakClient.bonded_targets.clear()
    client = IneproModbusClient(
        {
            CONF_TRANSPORT: TransportType.BLUETOOTH.value,
            CONF_BLUETOOTH_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_TIMEOUT: 3,
            CONF_BLE_CLIENT_FACTORY: EncryptionRequiredFakeBleakClient,
        }
    )

    try:
        registers = await client.async_read_registers(
            RegisterType.HOLDING,
            0x4000,
            2,
            1,
        )
    finally:
        await client.async_close()

    first_client = EncryptionRequiredFakeBleakClient.instances[0]
    assert len(EncryptionRequiredFakeBleakClient.instances) == 1
    assert first_client.pair_arg is False
    assert first_client.pair_calls == 1
    assert first_client.write_attempts == 2
    assert registers == [0x2510, 0x0001]
    assert first_client.writes == [
        (
            MODBUS_WRITE_CHARACTERISTIC_UUID,
            bytes.fromhex("010340000002D1CB"),
            True,
        )
    ]


async def test_ble_modbus_client_registers_bluez_agent_with_pairing_pin() -> None:
    """HA OS setup can answer the GROW LCD PIN through a temporary BlueZ agent."""
    EncryptionRequiredFakeBleakClient.instances.clear()
    EncryptionRequiredFakeBleakClient.bonded_targets.clear()
    agent_calls = []

    @asynccontextmanager
    async def fake_bluez_agent(**kwargs):
        agent_calls.append(kwargs)
        yield

    client = IneproModbusClient(
        {
            CONF_TRANSPORT: TransportType.BLUETOOTH.value,
            CONF_BLUETOOTH_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_TIMEOUT: 3,
            CONF_BLE_CLIENT_FACTORY: EncryptionRequiredFakeBleakClient,
            CONF_BLUETOOTH_PAIRING_PIN: "662535",
        }
    )

    with patch("inepro_metering.ble.platform.system", return_value="Linux"), patch(
        "inepro_metering.ble._bluez_pairing_agent",
        new=fake_bluez_agent,
    ):
        try:
            registers = await client.async_read_registers(
                RegisterType.HOLDING,
                0x4000,
                2,
                1,
            )
        finally:
            await client.async_close()

    assert registers == [0x2510, 0x0001]
    assert agent_calls
    assert agent_calls[0]["pairing_pin"] == "662535"
    assert EncryptionRequiredFakeBleakClient.instances[0].pair_calls == 1


async def test_ble_modbus_client_registers_bluez_agent_around_first_write() -> None:
    """The PIN agent must be active when FFE9 itself triggers pairing."""
    FakeBleakClient.instances.clear()
    agent_calls = []

    @asynccontextmanager
    async def fake_bluez_agent(**kwargs):
        agent_calls.append(kwargs)
        yield

    client = IneproModbusClient(
        {
            CONF_TRANSPORT: TransportType.BLUETOOTH.value,
            CONF_BLUETOOTH_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_TIMEOUT: 3,
            CONF_BLE_CLIENT_FACTORY: FakeBleakClient,
            CONF_BLUETOOTH_PAIRING_PIN: "662535",
        }
    )

    with patch("inepro_metering.ble.platform.system", return_value="Linux"), patch(
        "inepro_metering.ble._bluez_pairing_agent",
        new=fake_bluez_agent,
    ):
        try:
            registers = await client.async_read_registers(
                RegisterType.HOLDING,
                0x4000,
                2,
                1,
            )
        finally:
            await client.async_close()

    assert registers == [0x2510, 0x0001]
    assert len(agent_calls) == 1
    assert agent_calls[0]["pairing_pin"] == "662535"
    assert FakeBleakClient.instances[0].pair_calls == 0


async def test_ble_modbus_client_pairing_required_uses_pairing_timeout() -> None:
    """The required pairing mode should create BleakClient with pair=True."""
    FakeBleakClient.instances.clear()
    client = IneproModbusClient(
        {
            CONF_TRANSPORT: TransportType.BLUETOOTH.value,
            CONF_BLUETOOTH_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_TIMEOUT: 3,
            CONF_BLE_CLIENT_FACTORY: FakeBleakClient,
            CONF_BLUETOOTH_PAIRING_MODE: BLUETOOTH_PAIRING_MODE_REQUIRED,
            CONF_BLUETOOTH_PAIRING_TIMEOUT: 30,
            CONF_BLUETOOTH_FORCE_REPAIR: True,
        }
    )

    try:
        registers = await client.async_read_registers(
            RegisterType.HOLDING,
            0x4000,
            2,
            1,
        )
    finally:
        await client.async_close()

    fake_client = FakeBleakClient.instances[0]
    assert registers == [0x2510, 0x0001]
    assert fake_client.pair_arg is True
    assert fake_client.pair_calls == 0
    assert fake_client.unpair_calls == 1
    assert fake_client.timeout == 30


async def test_ble_modbus_client_force_repair_unpairs_before_auto_connect() -> None:
    """Setup validation should clear stale bonds, then use write-triggered pairing."""
    FakeBleakClient.instances.clear()
    client = IneproModbusClient(
        {
            CONF_TRANSPORT: TransportType.BLUETOOTH.value,
            CONF_BLUETOOTH_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_TIMEOUT: 3,
            CONF_BLE_CLIENT_FACTORY: FakeBleakClient,
            CONF_BLUETOOTH_PAIRING_MODE: BLUETOOTH_PAIRING_MODE_AUTO,
            CONF_BLUETOOTH_FORCE_REPAIR: True,
        }
    )

    try:
        registers = await client.async_read_registers(
            RegisterType.HOLDING,
            0x4000,
            2,
            1,
        )
    finally:
        await client.async_close()

    fake_client = FakeBleakClient.instances[0]
    assert registers == [0x2510, 0x0001]
    assert fake_client.pair_arg is False
    assert fake_client.unpair_calls == 1
    assert fake_client.pair_calls == 0


async def test_ble_modbus_client_pairs_after_auth_write_timeout() -> None:
    """A silent encrypted-write timeout should trigger one setup pairing attempt."""
    TimeoutUntilPairFakeBleakClient.instances.clear()
    TimeoutUntilPairFakeBleakClient.bonded_targets.clear()
    client = IneproModbusClient(
        {
            CONF_TRANSPORT: TransportType.BLUETOOTH.value,
            CONF_BLUETOOTH_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_TIMEOUT: 0.01,
            CONF_BLE_CLIENT_FACTORY: TimeoutUntilPairFakeBleakClient,
        }
    )

    try:
        registers = await client.async_read_registers(
            RegisterType.HOLDING,
            0x4000,
            2,
            1,
        )
    finally:
        await client.async_close()

    first_client = TimeoutUntilPairFakeBleakClient.instances[0]
    assert registers == [0x2510, 0x0001]
    assert len(TimeoutUntilPairFakeBleakClient.instances) == 1
    assert first_client.pair_arg is False
    assert first_client.pair_calls == 1
    assert first_client.start_notify_calls == 2
    assert first_client.stop_notify_calls == 2
    assert first_client.write_attempts == 2


async def test_ble_modbus_client_pairs_after_not_connected_first_write() -> None:
    """Setup pairing should handle backends that report disconnection on FFE9."""
    NotConnectedFirstWriteFakeBleakClient.instances.clear()
    NotConnectedFirstWriteFakeBleakClient.bonded_targets.clear()
    client = IneproModbusClient(
        {
            CONF_TRANSPORT: TransportType.BLUETOOTH.value,
            CONF_BLUETOOTH_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_TIMEOUT: 3,
            CONF_BLE_CLIENT_FACTORY: NotConnectedFirstWriteFakeBleakClient,
        }
    )

    try:
        registers = await client.async_read_registers(
            RegisterType.HOLDING,
            0x4000,
            2,
            1,
        )
    finally:
        await client.async_close()

    first_client = NotConnectedFirstWriteFakeBleakClient.instances[0]
    retry_client = NotConnectedFirstWriteFakeBleakClient.instances[1]
    assert registers == [0x2510, 0x0001]
    assert first_client.pair_calls == 0
    assert first_client.write_attempts == 1
    assert retry_client.pair_arg is True
    assert retry_client.write_attempts == 1


async def test_ble_modbus_client_pairing_never_does_not_pair() -> None:
    """Runtime polling should fail cleanly instead of starting pairing."""
    EncryptionRequiredFakeBleakClient.instances.clear()
    EncryptionRequiredFakeBleakClient.bonded_targets.clear()
    client = IneproModbusClient(
        {
            CONF_TRANSPORT: TransportType.BLUETOOTH.value,
            CONF_BLUETOOTH_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_TIMEOUT: 3,
            CONF_BLE_CLIENT_FACTORY: EncryptionRequiredFakeBleakClient,
            CONF_BLUETOOTH_PAIRING_MODE: BLUETOOTH_PAIRING_MODE_NEVER,
        }
    )

    with pytest.raises(IneproBluetoothNotPairedError):
        await client.async_read_registers(RegisterType.HOLDING, 0x4000, 2, 1)

    fake_client = EncryptionRequiredFakeBleakClient.instances[0]
    assert fake_client.pair_calls == 0
    assert len(EncryptionRequiredFakeBleakClient.instances) == 1


async def test_ble_modbus_client_uses_bleak_retry_connector_for_ble_device() -> None:
    """HA-provided BLEDevice targets should connect through establish_connection."""
    FakeBleakClient.instances.clear()
    ble_device = SimpleNamespace(name="IM-075625100001", address="AA:BB:CC:DD:EE:FF")

    async def fake_establish(client_class, device, name, **kwargs):
        fake_client = client_class(
            device,
            timeout=kwargs["timeout"],
            pair=kwargs["pair"],
            winrt=kwargs.get("winrt"),
        )
        await fake_client.connect()
        return fake_client

    client = IneproModbusClient(
        {
            CONF_TRANSPORT: TransportType.BLUETOOTH.value,
            CONF_BLUETOOTH_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_TIMEOUT: 3,
            CONF_BLE_CLIENT_FACTORY: FakeBleakClient,
            CONF_BLUETOOTH_DEVICE_RESOLVER: lambda: ble_device,
        }
    )

    with patch(
        "inepro_metering.ble.establish_connection",
        new=AsyncMock(side_effect=fake_establish),
    ) as establish:
        try:
            registers = await client.async_read_registers(
                RegisterType.HOLDING,
                0x4000,
                2,
                1,
            )
        finally:
            await client.async_close()

    assert registers == [0x2510, 0x0001]
    assert establish.await_count == 1
    assert FakeBleakClient.instances[0].target is ble_device


async def test_ble_modbus_client_pairing_unsupported_is_reported() -> None:
    """Backends that cannot pair should surface a pairing-unsupported cause."""
    PairingUnsupportedFakeBleakClient.instances.clear()
    PairingUnsupportedFakeBleakClient.bonded_targets.clear()
    client = IneproModbusClient(
        {
            CONF_TRANSPORT: TransportType.BLUETOOTH.value,
            CONF_BLUETOOTH_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_TIMEOUT: 3,
            CONF_BLE_CLIENT_FACTORY: PairingUnsupportedFakeBleakClient,
        }
    )

    with pytest.raises(IneproReadError) as exc_info:
        await client.async_read_registers(RegisterType.HOLDING, 0x4000, 2, 1)

    assert _has_cause(exc_info.value, IneproBlePairingUnsupportedError)


async def test_ble_modbus_client_pairing_failure_is_reported() -> None:
    """A failed encrypted write after pairing should surface as pairing failed."""
    PairingFailsFakeBleakClient.instances.clear()
    PairingFailsFakeBleakClient.bonded_targets.clear()
    client = IneproModbusClient(
        {
            CONF_TRANSPORT: TransportType.BLUETOOTH.value,
            CONF_BLUETOOTH_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_TIMEOUT: 3,
            CONF_BLE_CLIENT_FACTORY: PairingFailsFakeBleakClient,
        }
    )

    with pytest.raises(IneproReadError) as exc_info:
        await client.async_read_registers(RegisterType.HOLDING, 0x4000, 2, 1)

    assert _has_cause(exc_info.value, IneproBlePairingFailedError)


async def test_ble_modbus_client_resolves_fresh_ble_device_on_retry() -> None:
    """Reconnect attempts should call the BLEDevice resolver again."""
    FailsFirstConnectFakeBleakClient.instances.clear()
    targets = [
        SimpleNamespace(name="old-device"),
        SimpleNamespace(name="fresh-device"),
    ]

    def resolve_ble_device():
        return targets.pop(0)

    client = IneproModbusClient(
        {
            CONF_TRANSPORT: TransportType.BLUETOOTH.value,
            CONF_BLUETOOTH_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_TIMEOUT: 3,
            CONF_BLE_CLIENT_FACTORY: FailsFirstConnectFakeBleakClient,
            CONF_BLUETOOTH_DEVICE_RESOLVER: resolve_ble_device,
        }
    )

    try:
        registers = await client.async_read_registers(
            RegisterType.HOLDING,
            0x4000,
            2,
            1,
        )
    finally:
        await client.async_close()

    assert registers == [0x2510, 0x0001]
    assert FailsFirstConnectFakeBleakClient.instances[0].target.name == "old-device"
    assert FailsFirstConnectFakeBleakClient.instances[1].target.name == "fresh-device"


async def test_ble_modbus_client_missing_write_characteristic_fails_clearly() -> None:
    """The BLE client should reject devices without the write characteristic."""
    MissingWriteCharacteristicFakeBleakClient.instances.clear()
    client = IneproModbusClient(
        {
            CONF_TRANSPORT: TransportType.BLUETOOTH.value,
            CONF_BLUETOOTH_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_TIMEOUT: 3,
            CONF_BLE_CLIENT_FACTORY: MissingWriteCharacteristicFakeBleakClient,
        }
    )

    with pytest.raises(IneproConnectionError) as exc_info:
        await client.async_read_registers(RegisterType.HOLDING, 0x4000, 2, 1)

    assert "Could not open the Modbus transport" in str(exc_info.value)


async def test_ble_modbus_client_missing_notify_characteristic_fails_clearly() -> None:
    """The BLE client should reject devices without the FFE4 notify characteristic."""
    MissingNotifyCharacteristicFakeBleakClient.instances.clear()
    client = IneproModbusClient(
        {
            CONF_TRANSPORT: TransportType.BLUETOOTH.value,
            CONF_BLUETOOTH_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_TIMEOUT: 3,
            CONF_BLE_CLIENT_FACTORY: MissingNotifyCharacteristicFakeBleakClient,
        }
    )

    with pytest.raises(IneproConnectionError) as exc_info:
        await client.async_read_registers(RegisterType.HOLDING, 0x4000, 2, 1)

    assert "Could not open the Modbus transport" in str(exc_info.value)


async def test_ble_modbus_client_rejects_large_ble_writes() -> None:
    """Large Modbus writes should fail over BLE instead of being truncated."""
    FakeBleakClient.instances.clear()
    client = IneproModbusClient(
        {
            CONF_TRANSPORT: TransportType.BLUETOOTH.value,
            CONF_BLUETOOTH_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_TIMEOUT: 3,
            CONF_BLE_CLIENT_FACTORY: FakeBleakClient,
        }
    )

    with pytest.raises(IneproWriteError, match="exceeds safe write size"):
        await client.async_write_registers(0x7000, list(range(16)), 1)


async def test_ble_modbus_client_writes_single_register() -> None:
    """The BLE transport should support single-register Modbus writes."""
    FakeBleakClient.instances.clear()
    client = IneproModbusClient(
        {
            CONF_TRANSPORT: TransportType.BLUETOOTH.value,
            CONF_BLUETOOTH_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_TIMEOUT: 3,
            CONF_BLE_CLIENT_FACTORY: FakeBleakClient,
        }
    )

    try:
        await client.async_write_register(0x4C06, 1, 157)
    finally:
        await client.async_close()

    fake_client = FakeBleakClient.instances[0]
    assert fake_client.writes == [
        (
            MODBUS_WRITE_CHARACTERISTIC_UUID,
            build_rtu_frame(157, FUNCTION_WRITE_SINGLE_REGISTER, bytes.fromhex("4C060001")),
            True,
        ),
        (
            MODBUS_WRITE_CHARACTERISTIC_UUID,
            build_rtu_frame(157, FUNCTION_READ_HOLDING_REGISTERS, bytes.fromhex("4C060001")),
            True,
        )
    ]


async def test_ble_modbus_client_reads_device_identification() -> None:
    """The BLE transport should decode Modbus 43/14 device-identification replies."""
    FakeBleakClient.instances.clear()
    client = IneproModbusClient(
        {
            CONF_TRANSPORT: TransportType.BLUETOOTH.value,
            CONF_BLUETOOTH_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_TIMEOUT: 3,
            CONF_BLE_CLIENT_FACTORY: FakeBleakClient,
        }
    )

    try:
        identification = await client.async_read_device_identification(1)
    finally:
        await client.async_close()

    fake_client = FakeBleakClient.instances[0]
    assert identification.manufacturer_name == "inepro Metering B.V."
    assert identification.product_name == "879-3120"
    assert identification.version == "V1.0.2744"
    assert fake_client.writes == [
        (
            MODBUS_WRITE_CHARACTERISTIC_UUID,
            build_rtu_frame(1, FUNCTION_ENCAPSULATED_INTERFACE, bytes.fromhex("0E0100")),
            True,
        )
    ]


def _has_cause(err: BaseException, expected_type: type[BaseException]) -> bool:
    """Return whether an exception chain contains the expected type."""
    current: BaseException | None = err
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        if isinstance(current, expected_type):
            return True
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return False
