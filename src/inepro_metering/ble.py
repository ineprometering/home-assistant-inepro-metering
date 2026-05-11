"""Bluetooth Low Energy Modbus RTU transport for Inepro GROW meters."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
import inspect
import logging
import platform
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any

from .const import DEFAULT_BLUETOOTH_PAIRING_TIMEOUT
from .exceptions import IneproBluetoothNotPairedError

try:
    from bleak_retry_connector import establish_connection
except ImportError:  # pragma: no cover - dependency is available in HA
    establish_connection = None

DEVICE_INFORMATION_SERVICE_UUID = "0000180a-0000-1000-8000-00805f9b34fb"
DEVICE_INFORMATION_MODEL_CHARACTERISTIC_UUID = "00002a24-0000-1000-8000-00805f9b34fb"
DEVICE_INFORMATION_SERIAL_CHARACTERISTIC_UUID = "00002a25-0000-1000-8000-00805f9b34fb"
DEVICE_INFORMATION_FIRMWARE_CHARACTERISTIC_UUID = "00002a26-0000-1000-8000-00805f9b34fb"
DEVICE_INFORMATION_BLE_FIRMWARE_CHARACTERISTIC_UUID = "00002a28-0000-1000-8000-00805f9b34fb"
DEVICE_INFORMATION_MANUFACTURER_CHARACTERISTIC_UUID = "00002a29-0000-1000-8000-00805f9b34fb"
MODBUS_SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
MODBUS_NOTIFY_CHARACTERISTIC_UUID = "0000ffe4-0000-1000-8000-00805f9b34fb"
MODBUS_WRITE_CHARACTERISTIC_UUID = "0000ffe9-0000-1000-8000-00805f9b34fb"

FUNCTION_READ_HOLDING_REGISTERS = 0x03
FUNCTION_READ_INPUT_REGISTERS = 0x04
FUNCTION_WRITE_SINGLE_REGISTER = 0x06
FUNCTION_WRITE_MULTIPLE_REGISTERS = 0x10
FUNCTION_ENCAPSULATED_INTERFACE = 0x2B
MEI_READ_DEVICE_INFORMATION = 0x0E

LOGGER = logging.getLogger(__name__)
WINDOWS_WINRT_ARGS = {"use_cached_services": False}
BLUETOOTH_PAIRING_MODE_NEVER = "never"
BLUETOOTH_PAIRING_MODE_AUTO = "auto"
BLUETOOTH_PAIRING_MODE_REQUIRED = "required"
BLE_CONNECT_RETRY_DELAY_SECONDS = 0.25
BLE_CONNECT_ATTEMPTS = 3
DEFAULT_BLE_SAFE_RTU_FRAME_SIZE = 20
BLUEZ_SETUP_TIMEOUT = 10.0
BLUEZ_PIN_REQUEST_TIMEOUT = 10.0


class IneproBleError(Exception):
    """Base exception for BLE transport failures."""


class IneproBleDeviceNotFoundError(IneproBleError):
    """Raised when a current BLEDevice cannot be resolved before connecting."""


class IneproBleServicesMissingError(IneproBleError):
    """Raised when the expected GATT characteristics are not present."""


class IneproBleDeviceInformationMissingError(IneproBleError):
    """Raised when the expected Device Information service is not present."""


class IneproBlePairingFailedError(IneproBleError):
    """Raised when pairing was attempted but did not produce encrypted access."""


class IneproBlePairingUnsupportedError(IneproBleError):
    """Raised when the BLE backend cannot perform explicit pairing."""


class IneproBleFrameTooLargeError(IneproBleError):
    """Raised when a Modbus RTU frame is too large for the BLE write path."""


@dataclass(frozen=True, slots=True)
class BleGattDeviceInformation:
    """Device Information service values read over GATT."""

    model: str | None = None
    serial_number: str | None = None
    firmware_version: str | None = None
    ble_firmware_version: str | None = None
    manufacturer: str | None = None

    def as_dict(self) -> dict[str, str]:
        """Return populated fields as serializable readings."""
        readings: dict[str, str] = {}
        if self.model:
            readings["ble_model"] = self.model
        if self.serial_number:
            readings["ble_serial_number"] = self.serial_number
        if self.firmware_version:
            readings["ble_firmware_version"] = self.firmware_version
        if self.ble_firmware_version:
            readings["ble_stack_firmware_version"] = self.ble_firmware_version
        if self.manufacturer:
            readings["ble_manufacturer"] = self.manufacturer
        return readings


@dataclass(frozen=True, slots=True)
class BleModbusResponse:
    """Small response object with the subset of the pymodbus API we need."""

    registers: list[int]
    error: str | None = None

    def isError(self) -> bool:
        """Return whether the Modbus response is an exception response."""
        return self.error is not None

    def __str__(self) -> str:
        """Return a useful error string for coordinator exceptions."""
        return self.error or "OK"


@dataclass(frozen=True, slots=True)
class BleDeviceInformationResponse:
    """Small response object for Modbus Read Device Identification over BLE."""

    information: dict[int, bytes]
    error: str | None = None

    def isError(self) -> bool:
        """Return whether the Modbus response is an exception response."""
        return self.error is not None

    def __str__(self) -> str:
        """Return a useful error string for coordinator exceptions."""
        return self.error or "OK"


async def async_read_ble_device_information_only(
    *,
    address: str,
    timeout: float,
    name: str | None = None,
    ble_device: Any | None = None,
    ble_device_resolver: Callable[[], Any | Awaitable[Any]] | None = None,
    client_factory: Callable[..., Any] | None = None,
) -> BleGattDeviceInformation:
    """Read BLE Device Information without touching the encrypted Modbus service."""
    if client_factory is None:
        from bleak import BleakClient

        client_factory = BleakClient

    device_name = name or address
    target = await _resolve_ble_target(
        address=address,
        name=device_name,
        ble_device=ble_device,
        ble_device_resolver=ble_device_resolver,
    )
    client_kwargs: dict[str, Any] = {
        "timeout": float(timeout),
        "pair": False,
    }
    if platform.system() == "Windows":
        client_kwargs["winrt"] = WINDOWS_WINRT_ARGS

    LOGGER.debug(
        "ble_gatt_connect_start name=%s address=%s pair=False timeout=%s",
        device_name,
        address,
        timeout,
    )
    client = None
    try:
        client = await _create_connected_client(
            client_factory=client_factory,
            target=target,
            name=device_name,
            client_kwargs=client_kwargs,
            max_attempts=BLE_CONNECT_ATTEMPTS,
        )
        info = await _read_gatt_device_information_from_client(client, device_name)
        LOGGER.debug(
            "ble_gatt_device_info_ok name=%s model=%s serial=%s firmware=%s ble_firmware=%s manufacturer=%s",
            device_name,
            info.model,
            info.serial_number,
            info.firmware_version,
            info.ble_firmware_version,
            info.manufacturer,
        )
        return info
    except Exception as err:
        LOGGER.debug(
            "BLE GATT Device Information precheck failed for %s phase=gatt_precheck exception_chain=%s",
            device_name,
            _format_exception_chain(err),
        )
        raise
    finally:
        if client is not None and getattr(client, "is_connected", False):
            try:
                await client.disconnect()
            except Exception as err:
                LOGGER.debug(
                    "Failed to disconnect BLE GATT precheck client for %s: %s",
                    device_name,
                    err,
                )


class IneproBleModbusClient:
    """Modbus RTU-over-BLE client for the Inepro FFE4/FFE9 proxy service."""

    def __init__(
        self,
        *,
        address: str,
        timeout: float,
        name: str | None = None,
        ble_device: Any | None = None,
        ble_device_resolver: Callable[[], Any | Awaitable[Any]] | None = None,
        client_factory: Callable[..., Any] | None = None,
        pair: bool = True,
        pairing_mode: str = BLUETOOTH_PAIRING_MODE_AUTO,
        pairing_timeout: float = DEFAULT_BLUETOOTH_PAIRING_TIMEOUT,
        pairing_pin: str | None = None,
        pairing_pin_provider: (
            Callable[[], str | None | Awaitable[str | None]] | None
        ) = None,
        force_repair: bool = False,
    ) -> None:
        """Initialize the BLE Modbus client."""
        self._address = address
        self._timeout = timeout
        self._name = name or address
        self._ble_device = ble_device
        self._ble_device_resolver = ble_device_resolver
        self._client_factory = client_factory
        self._pair = pair
        self._force_repair = bool(force_repair)
        self._pairing_mode = (
            pairing_mode
            if pairing_mode
            in {
                BLUETOOTH_PAIRING_MODE_NEVER,
                BLUETOOTH_PAIRING_MODE_AUTO,
                BLUETOOTH_PAIRING_MODE_REQUIRED,
            }
            else BLUETOOTH_PAIRING_MODE_AUTO
        )
        self._pairing_timeout = float(pairing_timeout)
        self._pairing_pin = _normalize_pairing_pin(pairing_pin)
        self._pairing_pin_provider = pairing_pin_provider
        self._client: Any | None = None
        self._notification_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._notify_started = False
        self._connect_lock = asyncio.Lock()
        self._transaction_lock = asyncio.Lock()
        self._pairing_attempted = False
        self._force_repair_attempted = False

    @property
    def connected(self) -> bool:
        """Return whether the BLE client is connected."""
        return bool(self._client is not None and self._client.is_connected)

    def _diagnostic_log(self, message: str, *args: Any) -> None:
        """Log BLE setup diagnostics loudly while pairing, quietly at runtime."""
        level = (
            logging.WARNING
            if self._pairing_mode == BLUETOOTH_PAIRING_MODE_AUTO
            else logging.DEBUG
        )
        LOGGER.log(level, message, *args)

    async def connect(self) -> bool:
        """Connect and subscribe to the Modbus notification characteristic."""
        async with self._connect_lock:
            if self.connected:
                return True

            pair_first = self._pairing_mode == BLUETOOTH_PAIRING_MODE_REQUIRED
            try:
                connected = await self._connect_once(pair=pair_first)
            except Exception as err:
                if pair_first:
                    LOGGER.debug(
                        "BLE pairing connection attempt for %s failed phase=connect pair=True exception_chain=%s; retrying once",
                        self._name,
                        _format_exception_chain(err),
                    )
                    await asyncio.sleep(BLE_CONNECT_RETRY_DELAY_SECONDS)
                    return await self._connect_with_pairing()
                LOGGER.debug(
                    "BLE connection attempt for %s failed phase=connect pair=%s exception_chain=%s; retrying once",
                    self._name,
                    pair_first,
                    _format_exception_chain(err),
                )
                await asyncio.sleep(BLE_CONNECT_RETRY_DELAY_SECONDS)
                return await self._connect_once(pair=pair_first)

            if connected:
                return True

            LOGGER.debug("BLE connection for %s returned false; retrying once", self._name)
            await asyncio.sleep(BLE_CONNECT_RETRY_DELAY_SECONDS)
            if pair_first:
                return await self._connect_with_pairing()
            return await self._connect_once(pair=False)

    async def _connect_with_pairing(self) -> bool:
        """Connect once with pairing enabled and classify pairing failures."""
        try:
            return await self._connect_once(pair=True)
        except IneproBlePairingUnsupportedError:
            raise
        except Exception as err:
            if _pairing_unsupported(err):
                raise IneproBlePairingUnsupportedError(
                    f"BLE pairing is not supported by this backend for {self._name}"
                ) from err
            raise IneproBlePairingFailedError(
                f"BLE pairing failed for {self._name}"
            ) from err

    async def _connect_once(self, *, pair: bool) -> bool:
        """Open one BLE session and start notifications."""
        if self._client_factory is None:
            from bleak import BleakClient

            self._client_factory = BleakClient

        await self._reset_client()
        self._notification_queue = asyncio.Queue()
        target = await self._resolve_target()
        client_kwargs: dict[str, Any] = {
            "timeout": self._pairing_timeout if pair else self._timeout,
            "pair": bool(pair and self._pair),
        }
        if platform.system() == "Windows":
            # Windows can cache an incomplete GATT database for the meter and then
            # intermittently "lose" FFE4/FFE9 on reconnect. Force uncached service
            # discovery so each session asks the device again for the live map.
            client_kwargs["winrt"] = WINDOWS_WINRT_ARGS

        self._diagnostic_log(
            "ble_modbus_connect_start name=%s address=%s pair=%s timeout=%s",
            self._name,
            self._address,
            client_kwargs["pair"],
            client_kwargs["timeout"],
        )
        try:
            if self._force_repair and not self._force_repair_attempted:
                self._force_repair_attempted = True
                self._client = self._client_factory(target, **client_kwargs)
                await self._unpair_current_client_if_supported()
                self._client = None
            if client_kwargs["pair"]:
                async with _bluez_pairing_agent(
                    name=self._name,
                    pairing_timeout=self._pairing_timeout,
                    pairing_pin=self._pairing_pin,
                    pairing_pin_provider=self._pairing_pin_provider,
                ):
                    self._client = await _create_connected_client(
                        client_factory=self._client_factory,
                        target=target,
                        name=self._name,
                        client_kwargs=client_kwargs,
                        max_attempts=BLE_CONNECT_ATTEMPTS,
                    )
            else:
                self._client = await _create_connected_client(
                    client_factory=self._client_factory,
                    target=target,
                    name=self._name,
                    client_kwargs=client_kwargs,
                    max_attempts=BLE_CONNECT_ATTEMPTS,
                )

            self._diagnostic_log(
                "ble_modbus_connect_ok name=%s address=%s pair=%s",
                self._name,
                self._address,
                client_kwargs["pair"],
            )
            self._validate_required_characteristics()
            self._diagnostic_log("ble_modbus_notify_subscribe_start name=%s", self._name)
            await self._ensure_notify_subscription()
            self._diagnostic_log("ble_modbus_notify_subscribe_ok name=%s", self._name)
            return True
        except Exception as err:
            self._diagnostic_log(
                "BLE connection failed for %s phase=connect_or_services pair=%s exception_chain=%s",
                self._name,
                client_kwargs["pair"],
                _format_exception_chain(err),
            )
            await self._reset_client()
            if pair and _pairing_unsupported(err):
                raise IneproBlePairingUnsupportedError(
                    f"BLE pairing is not supported by this backend for {self._name}"
                ) from err
            raise

    async def _unpair_current_client_if_supported(self) -> None:
        """Clear a stale bond before an explicit setup pairing attempt."""
        if self._client is None:
            return

        unpair = getattr(self._client, "unpair", None)
        if unpair is None:
            LOGGER.debug(
                "BLE backend for %s does not expose unpair before pairing",
                self._name,
            )
            return

        try:
            result = unpair()
            if inspect.isawaitable(result):
                await result
            LOGGER.debug("Cleared existing BLE bond for %s before setup pairing", self._name)
        except Exception as err:
            LOGGER.debug(
                "Could not clear existing BLE bond for %s before setup pairing; continuing: %s",
                self._name,
                err,
            )

    async def close(self) -> None:
        """Disconnect from the BLE meter."""
        await self._reset_client()

    async def _reset_client(self) -> None:
        """Drop the current BLE client and clear notification state."""
        client = self._client
        notify_started = self._notify_started
        self._client = None
        self._notify_started = False
        self._notification_queue = asyncio.Queue()

        if client is None:
            return

        if getattr(client, "is_connected", False):
            try:
                if notify_started:
                    await client.stop_notify(MODBUS_NOTIFY_CHARACTERISTIC_UUID)
            except Exception as err:
                LOGGER.debug(
                    "Failed to stop BLE notifications before disconnect for %s: %s",
                    self._name,
                    err,
                )
            try:
                await client.disconnect()
            except Exception as err:
                LOGGER.debug("Failed to disconnect BLE client for %s: %s", self._name, err)

    async def _resolve_target(self) -> Any:
        """Resolve the freshest target object before creating a BleakClient."""
        target = await _resolve_ble_target(
            address=self._address,
            name=self._name,
            ble_device=self._ble_device,
            ble_device_resolver=self._ble_device_resolver,
        )
        if target is not self._address:
            self._ble_device = target
        return target

    async def read_holding_registers(
        self,
        address: int,
        *,
        count: int,
        device_id: int,
    ) -> BleModbusResponse:
        """Read holding registers through the BLE Modbus proxy."""
        return await self._async_read_registers(
            FUNCTION_READ_HOLDING_REGISTERS,
            address,
            count,
            device_id,
        )

    async def read_input_registers(
        self,
        address: int,
        *,
        count: int,
        device_id: int,
    ) -> BleModbusResponse:
        """Read input registers through the BLE Modbus proxy."""
        return await self._async_read_registers(
            FUNCTION_READ_INPUT_REGISTERS,
            address,
            count,
            device_id,
        )

    async def write_register(
        self,
        address: int,
        value: int,
        *,
        device_id: int,
    ) -> BleModbusResponse:
        """Write one holding register through the BLE Modbus proxy."""
        payload = _uint16(address) + _uint16(value)
        frame = build_rtu_frame(device_id, FUNCTION_WRITE_SINGLE_REGISTER, payload)
        response = await self.async_transceive_frame(
            frame,
            slave_id=device_id,
            function_code=FUNCTION_WRITE_SINGLE_REGISTER,
        )
        return _decode_write_response(response, FUNCTION_WRITE_SINGLE_REGISTER)

    async def write_registers(
        self,
        address: int,
        values: Iterable[int],
        *,
        device_id: int,
    ) -> BleModbusResponse:
        """Write a block of holding registers through the BLE Modbus proxy."""
        register_values = tuple(int(value) & 0xFFFF for value in values)
        payload = (
            _uint16(address)
            + _uint16(len(register_values))
            + bytes([len(register_values) * 2])
            + b"".join(_uint16(value) for value in register_values)
        )
        frame = build_rtu_frame(device_id, FUNCTION_WRITE_MULTIPLE_REGISTERS, payload)
        response = await self.async_transceive_frame(
            frame,
            slave_id=device_id,
            function_code=FUNCTION_WRITE_MULTIPLE_REGISTERS,
        )
        return _decode_write_response(response, FUNCTION_WRITE_MULTIPLE_REGISTERS)

    async def read_device_information(
        self,
        *,
        read_code: int | None = None,
        object_id: int = 0x00,
        device_id: int = 1,
        no_response_expected: bool = False,
    ) -> BleDeviceInformationResponse:
        """Read Modbus device-identification objects through the BLE proxy."""
        del no_response_expected
        payload = bytes(
            [
                MEI_READ_DEVICE_INFORMATION,
                int(read_code or 0x01) & 0xFF,
                int(object_id) & 0xFF,
            ]
        )
        frame = build_rtu_frame(device_id, FUNCTION_ENCAPSULATED_INTERFACE, payload)
        response = await self.async_transceive_frame(
            frame,
            slave_id=device_id,
            function_code=FUNCTION_ENCAPSULATED_INTERFACE,
        )
        return _decode_device_information_response(response)

    async def read_gatt_device_information(self) -> BleGattDeviceInformation:
        """Read the BLE Device Information service before Modbus-over-BLE traffic."""
        if self._client is None or not self.connected:
            connected = await self.connect()
            if not connected:
                raise TimeoutError(f"Could not connect to BLE meter {self._name}")

        return await _read_gatt_device_information_from_client(self._client, self._name)

    async def _async_read_registers(
        self,
        function_code: int,
        address: int,
        count: int,
        slave_id: int,
    ) -> BleModbusResponse:
        """Read registers using the requested Modbus function code."""
        payload = _uint16(address) + _uint16(count)
        frame = build_rtu_frame(slave_id, function_code, payload)
        response = await self.async_transceive_frame(
            frame,
            slave_id=slave_id,
            function_code=function_code,
        )
        return _decode_read_response(response, function_code)

    async def async_transceive_frame(
        self,
        frame: bytes,
        *,
        slave_id: int | None = None,
        function_code: int | None = None,
    ) -> bytes:
        """Write one RTU frame and wait for the matching notification response."""
        async with self._transaction_lock:
            try:
                return await self._async_transceive_frame_locked(
                    frame,
                    slave_id=slave_id,
                    function_code=function_code,
                )
            except Exception:
                await self.close()
                raise

    async def _async_transceive_frame_locked(
        self,
        frame: bytes,
        *,
        slave_id: int | None = None,
        function_code: int | None = None,
    ) -> bytes:
        """Write one RTU frame and wait for the matching response while locked."""
        if len(frame) < 2:
            raise ValueError("BLE Modbus frame must contain at least slave id and function")

        expected_slave_id = int(slave_id if slave_id is not None else frame[0])
        expected_function_code = int(
            function_code if function_code is not None else (frame[1] & 0x7F)
        )

        if self._client is None or not self.connected:
            connected = await self.connect()
            if not connected:
                raise TimeoutError(f"Could not connect to BLE meter {self._name}")

        if not self._notify_started:
            await self._ensure_notify_subscription()

        self._clear_notification_queue()

        try:
            async with self._pairing_agent_for_transaction():
                await self._write_frame(frame)
                return await self._await_matching_response(
                    slave_id=expected_slave_id,
                    function_code=expected_function_code,
                )
        except Exception as err:
            if not self._should_attempt_pairing(err):
                if (
                    self._pairing_mode == BLUETOOTH_PAIRING_MODE_NEVER
                    and is_ble_pairing_trigger_error(err)
                ):
                    raise IneproBluetoothNotPairedError(
                        "BLE meter is not paired with the host"
                    ) from err
                raise
            return await self._pair_reconnect_retry_frame(
                frame,
                slave_id=expected_slave_id,
                function_code=expected_function_code,
                trigger=err,
                failure_phase=(
                    "wait_notify"
                    if isinstance(err, TimeoutError)
                    else "write_ffe9"
                ),
            )

    def _clear_notification_queue(self) -> None:
        """Discard stale notification chunks before a new Modbus transaction."""
        while not self._notification_queue.empty():
            self._notification_queue.get_nowait()

    async def _await_matching_response(
        self,
        *,
        slave_id: int,
        function_code: int,
    ) -> bytes:
        """Wait for notification chunks until a matching RTU response is complete."""
        buffer = bytearray()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._timeout
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError(f"Timed out waiting for BLE Modbus response from {self._name}")

            chunk = await asyncio.wait_for(
                self._notification_queue.get(),
                timeout=remaining,
            )
            buffer.extend(chunk)
            response = try_extract_rtu_response(
                bytes(buffer),
                slave_id=slave_id,
                function_code=function_code,
            )
            if response is not None:
                self._diagnostic_log(
                    "ble_modbus_notify_received name=%s length=%s",
                    self._name,
                    len(response),
                )
                return response

    def _handle_notification(self, _sender: Any, data: bytearray | bytes | memoryview) -> None:
        """Queue notification chunks from the Modbus notify characteristic."""
        self._notification_queue.put_nowait(bytes(data))

    async def _write_frame(self, frame: bytes) -> None:
        """Write one RTU frame to the BLE Modbus write characteristic."""
        max_size = self._max_write_size()
        if len(frame) > max_size:
            raise IneproBleFrameTooLargeError(
                "BLE Modbus frame length "
                f"{len(frame)} exceeds safe write size {max_size}; large BLE writes "
                "are not enabled for this meter firmware"
            )

        self._diagnostic_log(
            "ble_modbus_write_ffe9_attempt name=%s length=%s pairing_mode=%s pairing_attempted=%s force_repair=%s",
            self._name,
            len(frame),
            self._pairing_mode,
            self._pairing_attempted,
            self._force_repair,
        )
        await self._client.write_gatt_char(
            MODBUS_WRITE_CHARACTERISTIC_UUID,
            frame,
            response=True,
        )

    @asynccontextmanager
    async def _pairing_agent_for_transaction(self):
        """Keep the setup PIN agent alive for write and notification response."""
        if not self._should_register_pairing_agent_for_write():
            yield
            return

        async with _bluez_pairing_agent(
            name=self._name,
            pairing_timeout=self._pairing_timeout,
            pairing_pin=self._pairing_pin,
            pairing_pin_provider=self._pairing_pin_provider,
        ):
            yield

    def _should_register_pairing_agent_for_write(self) -> bool:
        """Return whether first encrypted-write setup should answer a BlueZ PIN."""
        return (
            self._pairing_mode == BLUETOOTH_PAIRING_MODE_AUTO
            and not self._pairing_attempted
            and (
                self._pairing_pin is not None
                or self._pairing_pin_provider is not None
            )
        )

    async def _pair_reconnect_retry_frame(
        self,
        frame: bytes,
        *,
        slave_id: int,
        function_code: int,
        trigger: BaseException,
        failure_phase: str,
    ) -> bytes:
        """Pair once, reconnect/resubscribe, and retry the same Modbus frame."""
        LOGGER.warning(
            "ble_pairing_required_detected name=%s phase=%s exception_class=%s exception=%s pairing_mode=%s pairing_attempted=%s force_repair=%s",
            self._name,
            failure_phase,
            type(trigger).__name__,
            trigger,
            self._pairing_mode,
            self._pairing_attempted,
            self._force_repair,
        )
        self._pairing_attempted = True
        try:
            await self._pair_current_device_for_retry()
            self._clear_notification_queue()
            self._diagnostic_log(
                "ble_modbus_retry_write_ffe9 name=%s length=%s",
                self._name,
                len(frame),
            )
            await self._write_frame(frame)
            return await self._await_matching_response(
                slave_id=slave_id,
                function_code=function_code,
            )
        except IneproBlePairingUnsupportedError:
            self._diagnostic_log("ble_pairing_failed name=%s reason=unsupported", self._name)
            raise
        except Exception as pairing_err:
            self._diagnostic_log(
                "ble_pairing_failed name=%s phase=%s exception_chain=%s",
                self._name,
                failure_phase,
                _format_exception_chain(pairing_err),
            )
            if _pairing_unsupported(pairing_err):
                raise IneproBlePairingUnsupportedError(
                    f"BLE pairing is not supported by this backend for {self._name}"
                ) from pairing_err
            if is_ble_pairing_trigger_error(pairing_err):
                raise IneproBlePairingFailedError(
                    f"BLE pairing failed for {self._name}"
                ) from pairing_err
            raise

    def _should_attempt_pairing(self, err: BaseException) -> bool:
        """Return whether setup pairing fallback may run for this failure."""
        if (
            self._pairing_mode != BLUETOOTH_PAIRING_MODE_AUTO
            or self._pairing_attempted
            or not (
                isinstance(err, TimeoutError)
                or is_ble_pairing_trigger_error(err)
            )
        ):
            return False
        LOGGER.warning(
            "ble_modbus_write_ffe9_failed name=%s exception_class=%s exception=%s pairing_mode=%s pairing_attempted=%s force_repair=%s",
            self._name,
            type(err).__name__,
            err,
            self._pairing_mode,
            self._pairing_attempted,
            self._force_repair,
        )
        return True

    async def _pair_current_device_for_retry(self) -> None:
        """Trigger pairing and keep the active session when the backend allows it."""
        LOGGER.warning("ble_pairing_start name=%s", self._name)
        pair_error: BaseException | None = None
        if self._client is not None and self.connected:
            try:
                await asyncio.wait_for(
                    self._pair_current_client(),
                    timeout=self._pairing_timeout,
                )
                LOGGER.warning(
                    "ble_pairing_success name=%s method=current_client_pair",
                    self._name,
                )
                if self.connected:
                    await self._ensure_notify_subscription(force=True)
                    return
                await self._reconnect_after_pairing(pair=False)
                return
            except IneproBlePairingUnsupportedError as err:
                pair_error = err
                self._diagnostic_log(
                    "BLE current-client pair unsupported for %s; retrying with pair-enabled reconnect",
                    self._name,
                )
            except Exception as err:
                pair_error = err
                self._diagnostic_log(
                    "BLE current-client pair for %s failed; retrying with pair-enabled reconnect exception_chain=%s",
                    self._name,
                    _format_exception_chain(err),
                )

        try:
            await self._reconnect_after_pairing(pair=True)
            LOGGER.warning(
                "ble_pairing_success name=%s method=pair_enabled_reconnect",
                self._name,
            )
        except IneproBlePairingUnsupportedError:
            raise
        except Exception as err:
            if _pairing_unsupported(err):
                raise IneproBlePairingUnsupportedError(
                    f"BLE pairing is not supported by this backend for {self._name}"
                ) from err
            raise IneproBlePairingFailedError(
                f"BLE pairing failed for {self._name}"
            ) from (pair_error or err)

    async def _reconnect_after_pairing(self, *, pair: bool) -> None:
        """Reconnect after pairing and verify notifications are subscribed again."""
        self._diagnostic_log(
            "ble_reconnect_after_pairing_start name=%s pair=%s timeout=%s",
            self._name,
            pair,
            self._pairing_timeout if pair else self._timeout,
        )
        connected = await self._connect_once(pair=pair)
        if not connected:
            raise TimeoutError(f"Could not reconnect to BLE meter {self._name}")
        self._diagnostic_log(
            "ble_notify_resubscribe_after_pairing_ok name=%s",
            self._name,
        )

    async def _pair_current_client(self) -> None:
        """Ask the active Bleak client to start the native backend pairing flow."""
        if self._client is None:
            raise IneproBlePairingFailedError(
                f"No active BLE client available for pairing {self._name}"
            )

        pair = getattr(self._client, "pair", None)
        if pair is None:
            raise IneproBlePairingUnsupportedError(
                f"BLE pairing is not supported by this backend for {self._name}"
            )

        async with _bluez_pairing_agent(
            name=self._name,
            pairing_timeout=self._pairing_timeout,
            pairing_pin=self._pairing_pin,
            pairing_pin_provider=self._pairing_pin_provider,
        ):
            result = pair()
            if inspect.isawaitable(result):
                await result

    async def _ensure_notify_subscription(self, *, force: bool = False) -> None:
        """Start FFE4 notifications if the current session is not subscribed."""
        if self._client is None:
            raise TimeoutError(f"Could not subscribe to BLE notifications for {self._name}")
        if self._notify_started and not force:
            return
        if self._notify_started and force:
            try:
                await self._client.stop_notify(MODBUS_NOTIFY_CHARACTERISTIC_UUID)
            except Exception as err:
                LOGGER.debug(
                    "Failed to refresh BLE notifications for %s before retry: %s",
                    self._name,
                    err,
                )
            self._notify_started = False
        await self._client.start_notify(
            MODBUS_NOTIFY_CHARACTERISTIC_UUID,
            self._handle_notification,
        )
        self._notify_started = True

    def _validate_required_characteristics(self) -> None:
        """Verify the expected notify and write characteristics are available."""
        services = getattr(self._client, "services", None)
        if services is None:
            self._diagnostic_log(
                "BLE service collection unavailable for %s; characteristic preflight skipped",
                self._name,
            )
            return

        missing = [
            uuid
            for uuid in (
                MODBUS_NOTIFY_CHARACTERISTIC_UUID,
                MODBUS_WRITE_CHARACTERISTIC_UUID,
            )
            if _find_characteristic(services, uuid) is None
        ]
        if missing:
            self._diagnostic_log(
                "BLE service discovery for %s missing required characteristics: %s",
                self._name,
                ", ".join(missing),
            )
            raise IneproBleServicesMissingError(
                "Required BLE Modbus characteristics are missing: "
                + ", ".join(missing)
            )
        self._diagnostic_log("BLE service discovery succeeded for %s", self._name)

    def _max_write_size(self) -> int:
        """Return the safest currently known BLE write size."""
        services = getattr(self._client, "services", None)
        characteristic = (
            None
            if services is None
            else _find_characteristic(services, MODBUS_WRITE_CHARACTERISTIC_UUID)
        )
        max_without_response = getattr(
            characteristic,
            "max_write_without_response_size",
            None,
        )
        if isinstance(max_without_response, int) and max_without_response > 0:
            return max_without_response
        return DEFAULT_BLE_SAFE_RTU_FRAME_SIZE


def build_rtu_frame(slave_id: int, function_code: int, payload: bytes) -> bytes:
    """Build a Modbus RTU frame with CRC16."""
    body = bytes([slave_id & 0xFF, function_code & 0xFF]) + payload
    crc = modbus_crc16(body)
    return body + bytes([crc & 0xFF, (crc >> 8) & 0xFF])


def try_extract_rtu_response(
    buffer: bytes,
    *,
    slave_id: int,
    function_code: int,
) -> bytes | None:
    """Return a complete validated RTU response from a notification buffer."""
    for start in range(len(buffer)):
        if buffer[start] != (slave_id & 0xFF):
            continue

        candidate = buffer[start:]
        expected_length = _expected_response_length(candidate, function_code)
        if expected_length is None or len(candidate) < expected_length:
            continue

        response = candidate[:expected_length]
        if _has_valid_crc(response):
            return response

    return None


async def _resolve_ble_target(
    *,
    address: str,
    name: str,
    ble_device: Any | None,
    ble_device_resolver: Callable[[], Any | Awaitable[Any]] | None,
) -> Any:
    """Resolve the freshest BLE target object before creating a BleakClient."""
    if ble_device_resolver is not None:
        resolved = ble_device_resolver()
        if inspect.isawaitable(resolved):
            resolved = await resolved
        if resolved is None:
            LOGGER.debug(
                "BLEDevice resolver returned no connectable device for %s",
                address,
            )
            raise IneproBleDeviceNotFoundError(
                f"No connectable BLEDevice found for {name}"
            )
        LOGGER.debug(
            "Resolved fresh BLEDevice for %s name=%s",
            address,
            getattr(resolved, "name", None),
        )
        return resolved

    return ble_device if ble_device is not None else address


async def _create_connected_client(
    *,
    client_factory: Callable[..., Any],
    target: Any,
    name: str,
    client_kwargs: dict[str, Any],
    max_attempts: int,
) -> Any:
    """Create and connect a BLE client, using bleak-retry-connector when possible."""
    if establish_connection is not None and _can_use_retry_connector(target):
        LOGGER.debug(
            "Using bleak-retry-connector for BLE connection name=%s pair=%s timeout=%s attempts=%s",
            name,
            client_kwargs.get("pair"),
            client_kwargs.get("timeout"),
            max_attempts,
        )
        return await establish_connection(
            client_factory,
            target,
            name,
            max_attempts=max_attempts,
            use_services_cache=False,
            **client_kwargs,
        )

    client = client_factory(target, **client_kwargs)
    connect_result = await client.connect()
    connected = bool(
        connect_result if connect_result is not None else getattr(client, "is_connected", False)
    )
    if not connected:
        try:
            await client.disconnect()
        except Exception:
            pass
        raise TimeoutError(f"Could not connect to BLE meter {name}")
    return client


def _can_use_retry_connector(target: Any) -> bool:
    """Return whether target looks like a BLEDevice accepted by establish_connection."""
    return not isinstance(target, str) and hasattr(target, "address")


def _bluez_pairing_in_progress_error(err: BaseException) -> bool:
    """Return whether BlueZ reports a pairing operation already in progress."""
    message = _format_exception_chain(err).casefold()
    return "in progress" in message or "org.bluez.error.inprogress" in message


async def async_bluez_pair_device(
    *,
    address: str,
    name: str,
    pairing_timeout: float,
    pairing_pin: str | None = None,
    pairing_pin_provider: Callable[[], str | None | Awaitable[str | None]] | None = None,
    force_repair: bool = False,
    pin_request_timeout: float = BLUEZ_PIN_REQUEST_TIMEOUT,
) -> None:
    """Experimentally pair a BlueZ device using the temporary Inepro PIN agent."""
    if platform.system() != "Linux":
        raise IneproBlePairingUnsupportedError(
            "Direct BlueZ pairing is only available on Linux"
        )

    try:
        from dbus_fast import Message, MessageType, Variant
        from dbus_fast.aio import MessageBus
        from dbus_fast.constants import BusType
    except ImportError as err:
        raise IneproBlePairingUnsupportedError(
            "Direct BlueZ pairing requires dbus-fast on the Home Assistant host"
        ) from err

    def _raise_for_error(reply) -> None:
        if reply.message_type is MessageType.ERROR:
            message = reply.body[0] if reply.body else reply.error_name
            raise RuntimeError(str(message or reply.error_name))

    LOGGER.debug(
        "ble_bluez_direct_pair_prepare name=%s address=%s timeout=%s platform=%s has_pin=%s has_provider=%s force_repair=%s",
        name,
        address,
        pairing_timeout,
        platform.system(),
        pairing_pin is not None,
        pairing_pin_provider is not None,
        force_repair,
    )
    pairing_request_event = asyncio.Event()

    def _mark_pairing_request() -> None:
        pairing_request_event.set()

    async with _bluez_pairing_agent(
        name=name,
        pairing_timeout=pairing_timeout,
        pairing_pin=pairing_pin,
        pairing_pin_provider=pairing_pin_provider,
        pairing_request_callback=_mark_pairing_request,
    ):
        LOGGER.debug("ble_bluez_direct_bus_connect_start name=%s", name)
        bus = await asyncio.wait_for(
            MessageBus(bus_type=BusType.SYSTEM).connect(),
            timeout=BLUEZ_SETUP_TIMEOUT,
        )
        LOGGER.debug("ble_bluez_direct_bus_connected name=%s", name)
        try:
            device_path = await asyncio.wait_for(
                _bluez_device_path_for_address(
                    bus,
                    address=address,
                    Message=Message,
                    raise_for_error=_raise_for_error,
                ),
                timeout=BLUEZ_SETUP_TIMEOUT,
            )
            if force_repair:
                adapter_path = _bluez_adapter_path_for_device_path(device_path)
                await _bluez_cancel_device_pairing(
                    bus,
                    Message=Message,
                    device_path=device_path,
                    name=name,
                    address=address,
                    raise_for_error=_raise_for_error,
                )
                await _bluez_remove_device(
                    bus,
                    Message=Message,
                    device_path=device_path,
                    name=name,
                    address=address,
                    raise_for_error=_raise_for_error,
                )
                await _bluez_start_adapter_discovery(
                    bus,
                    Message=Message,
                    adapter_path=adapter_path,
                    name=name,
                    address=address,
                    raise_for_error=_raise_for_error,
                )
                try:
                    device_path = await _bluez_wait_for_device_path(
                        bus,
                        address=address,
                        Message=Message,
                        raise_for_error=_raise_for_error,
                        timeout=max(BLUEZ_SETUP_TIMEOUT, min(float(pairing_timeout), 30.0)),
                    )
                finally:
                    await _bluez_stop_adapter_discovery(
                        bus,
                        Message=Message,
                        adapter_path=adapter_path,
                        name=name,
                        address=address,
                        raise_for_error=_raise_for_error,
                    )
                LOGGER.warning(
                    "ble_bluez_direct_remove_device_rediscovered name=%s address=%s path=%s",
                    name,
                    address,
                    device_path,
                )
            LOGGER.warning(
                "ble_bluez_direct_pair_start name=%s address=%s path=%s",
                name,
                address,
                device_path,
            )
            try:
                reply = await _bluez_pair_device_once(
                    bus,
                    Message=Message,
                    device_path=device_path,
                    name=name,
                    address=address,
                    pairing_timeout=float(pairing_timeout),
                    pin_request_timeout=pin_request_timeout,
                    pairing_request_event=pairing_request_event,
                    raise_for_error=_raise_for_error,
                )
                _raise_for_error(reply)
            except asyncio.CancelledError:
                await _bluez_cancel_device_pairing(
                    bus,
                    Message=Message,
                    device_path=device_path,
                    name=name,
                    address=address,
                    raise_for_error=_raise_for_error,
                )
                raise
            except Exception as err:
                if not _bluez_pairing_in_progress_error(err):
                    raise
                LOGGER.warning(
                    "ble_bluez_direct_pair_in_progress name=%s address=%s path=%s",
                    name,
                    address,
                    device_path,
                )
                await _bluez_cancel_device_pairing(
                    bus,
                    Message=Message,
                    device_path=device_path,
                    name=name,
                    address=address,
                    raise_for_error=_raise_for_error,
                )
                await asyncio.sleep(BLE_CONNECT_RETRY_DELAY_SECONDS)
                LOGGER.warning(
                    "ble_bluez_direct_pair_retry_start name=%s address=%s path=%s",
                    name,
                    address,
                    device_path,
                )
                pairing_request_event.clear()
                reply = await _bluez_pair_device_once(
                    bus,
                    Message=Message,
                    device_path=device_path,
                    name=name,
                    address=address,
                    pairing_timeout=float(pairing_timeout),
                    pin_request_timeout=pin_request_timeout,
                    pairing_request_event=pairing_request_event,
                    raise_for_error=_raise_for_error,
                )
                _raise_for_error(reply)
            LOGGER.warning(
                "ble_bluez_direct_pair_success name=%s address=%s path=%s",
                name,
                address,
                device_path,
            )
            try:
                reply = await asyncio.wait_for(
                    bus.call(
                        Message(
                            destination="org.bluez",
                            path=device_path,
                            interface="org.freedesktop.DBus.Properties",
                            member="Set",
                            signature="ssv",
                            body=[
                                "org.bluez.Device1",
                                "Trusted",
                                Variant("b", True),
                            ],
                        )
                    ),
                    timeout=BLUEZ_SETUP_TIMEOUT,
                )
                _raise_for_error(reply)
                LOGGER.warning(
                    "ble_bluez_direct_trusted_set name=%s address=%s path=%s",
                    name,
                    address,
                    device_path,
                )
            except Exception as err:
                LOGGER.debug(
                    "Could not mark BlueZ device trusted for %s: %s",
                    name,
                    err,
                )
        except Exception as err:
            LOGGER.warning(
                "ble_bluez_direct_pair_failed name=%s address=%s exception_chain=%s",
                name,
                address,
                _format_exception_chain(err),
            )
            if _pairing_unsupported(err):
                raise IneproBlePairingUnsupportedError(
                    f"BlueZ pairing is not supported for {name}"
                ) from err
            raise IneproBlePairingFailedError(
                f"BlueZ pairing failed for {name}"
            ) from err
        finally:
            bus.disconnect()


async def _bluez_call_device_method(
    bus: Any,
    *,
    Message: Any,
    device_path: str,
    member: str,
    timeout: float,
) -> Any:
    """Call one BlueZ Device1 method with a bounded timeout."""
    return await asyncio.wait_for(
        bus.call(
            Message(
                destination="org.bluez",
                path=device_path,
                interface="org.bluez.Device1",
                member=member,
            )
        ),
        timeout=timeout,
    )


async def _bluez_pair_device_once(
    bus: Any,
    *,
    Message: Any,
    device_path: str,
    name: str,
    address: str,
    pairing_timeout: float,
    pin_request_timeout: float,
    pairing_request_event: asyncio.Event,
    raise_for_error: Callable[[Any], None],
) -> Any:
    """Call Device1.Pair, falling back quickly if BlueZ never asks for a PIN."""
    pair_task = asyncio.create_task(
        _bluez_call_device_method(
            bus,
            Message=Message,
            device_path=device_path,
            member="Pair",
            timeout=pairing_timeout + BLUEZ_SETUP_TIMEOUT,
        )
    )
    request_task = asyncio.create_task(pairing_request_event.wait())
    try:
        done, _pending = await asyncio.wait(
            {pair_task, request_task},
            timeout=pin_request_timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if pair_task in done:
            request_task.cancel()
            return pair_task.result()
        if request_task in done:
            LOGGER.warning(
                "ble_bluez_direct_pin_request_observed name=%s address=%s path=%s",
                name,
                address,
                device_path,
            )
            return await pair_task

        LOGGER.warning(
            "ble_bluez_direct_pin_request_timeout name=%s address=%s path=%s timeout=%s",
            name,
            address,
            device_path,
            pin_request_timeout,
        )
        pair_task.cancel()
        with suppress(asyncio.CancelledError):
            await pair_task
        await _bluez_cancel_device_pairing(
            bus,
            Message=Message,
            device_path=device_path,
            name=name,
            address=address,
            raise_for_error=raise_for_error,
        )
        await _bluez_disconnect_device(
            bus,
            Message=Message,
            device_path=device_path,
            name=name,
            address=address,
            raise_for_error=raise_for_error,
        )
        raise TimeoutError(
            f"BlueZ pairing did not request a PIN for {name} within {pin_request_timeout}s"
        )
    finally:
        request_task.cancel()
        with suppress(asyncio.CancelledError):
            await request_task


async def _bluez_cancel_device_pairing(
    bus: Any,
    *,
    Message: Any,
    device_path: str,
    name: str,
    address: str,
    raise_for_error: Callable[[Any], None],
) -> None:
    """Cancel a stale BlueZ pairing operation if one is active."""
    try:
        LOGGER.warning(
            "ble_bluez_direct_cancel_pairing_start name=%s address=%s path=%s",
            name,
            address,
            device_path,
        )
        reply = await _bluez_call_device_method(
            bus,
            Message=Message,
            device_path=device_path,
            member="CancelPairing",
            timeout=BLUEZ_SETUP_TIMEOUT,
        )
        raise_for_error(reply)
        LOGGER.warning(
            "ble_bluez_direct_cancel_pairing_ok name=%s address=%s path=%s",
            name,
            address,
            device_path,
        )
    except Exception as err:
        LOGGER.warning(
            "ble_bluez_direct_cancel_pairing_failed name=%s address=%s path=%s exception_chain=%s",
            name,
            address,
            device_path,
            _format_exception_chain(err),
        )


def _bluez_adapter_path_for_device_path(device_path: str) -> str | None:
    """Return the adapter object path for one BlueZ device path."""
    adapter_path = device_path.rsplit("/dev_", 1)[0]
    if adapter_path == device_path:
        return None
    return adapter_path


async def _bluez_call_adapter_method(
    bus: Any,
    *,
    Message: Any,
    adapter_path: str,
    member: str,
    timeout: float,
) -> Any:
    """Call one BlueZ Adapter1 method with a bounded timeout."""
    return await asyncio.wait_for(
        bus.call(
            Message(
                destination="org.bluez",
                path=adapter_path,
                interface="org.bluez.Adapter1",
                member=member,
            )
        ),
        timeout=timeout,
    )


async def _bluez_start_adapter_discovery(
    bus: Any,
    *,
    Message: Any,
    adapter_path: str | None,
    name: str,
    address: str,
    raise_for_error: Callable[[Any], None],
) -> None:
    """Ask BlueZ to discover the meter again after RemoveDevice."""
    if adapter_path is None:
        LOGGER.warning(
            "ble_bluez_direct_start_discovery_skipped name=%s address=%s",
            name,
            address,
        )
        return
    try:
        LOGGER.warning(
            "ble_bluez_direct_start_discovery name=%s address=%s adapter=%s",
            name,
            address,
            adapter_path,
        )
        reply = await _bluez_call_adapter_method(
            bus,
            Message=Message,
            adapter_path=adapter_path,
            member="StartDiscovery",
            timeout=BLUEZ_SETUP_TIMEOUT,
        )
        raise_for_error(reply)
        LOGGER.warning(
            "ble_bluez_direct_start_discovery_ok name=%s address=%s adapter=%s",
            name,
            address,
            adapter_path,
        )
    except Exception as err:
        LOGGER.warning(
            "ble_bluez_direct_start_discovery_failed name=%s address=%s adapter=%s exception_chain=%s",
            name,
            address,
            adapter_path,
            _format_exception_chain(err),
        )


async def _bluez_stop_adapter_discovery(
    bus: Any,
    *,
    Message: Any,
    adapter_path: str | None,
    name: str,
    address: str,
    raise_for_error: Callable[[Any], None],
) -> None:
    """Release the temporary BlueZ discovery request."""
    if adapter_path is None:
        return
    try:
        reply = await _bluez_call_adapter_method(
            bus,
            Message=Message,
            adapter_path=adapter_path,
            member="StopDiscovery",
            timeout=BLUEZ_SETUP_TIMEOUT,
        )
        raise_for_error(reply)
        LOGGER.warning(
            "ble_bluez_direct_stop_discovery_ok name=%s address=%s adapter=%s",
            name,
            address,
            adapter_path,
        )
    except Exception as err:
        LOGGER.warning(
            "ble_bluez_direct_stop_discovery_failed name=%s address=%s adapter=%s exception_chain=%s",
            name,
            address,
            adapter_path,
            _format_exception_chain(err),
        )


async def _bluez_disconnect_device(
    bus: Any,
    *,
    Message: Any,
    device_path: str,
    name: str,
    address: str,
    raise_for_error: Callable[[Any], None],
) -> None:
    """Disconnect a device after a cancelled BlueZ pairing attempt."""
    try:
        LOGGER.warning(
            "ble_bluez_direct_disconnect_start name=%s address=%s path=%s",
            name,
            address,
            device_path,
        )
        reply = await _bluez_call_device_method(
            bus,
            Message=Message,
            device_path=device_path,
            member="Disconnect",
            timeout=BLUEZ_SETUP_TIMEOUT,
        )
        raise_for_error(reply)
        LOGGER.warning(
            "ble_bluez_direct_disconnect_ok name=%s address=%s path=%s",
            name,
            address,
            device_path,
        )
    except Exception as err:
        LOGGER.warning(
            "ble_bluez_direct_disconnect_failed name=%s address=%s path=%s exception_chain=%s",
            name,
            address,
            device_path,
            _format_exception_chain(err),
        )


async def _bluez_remove_device(
    bus: Any,
    *,
    Message: Any,
    device_path: str,
    name: str,
    address: str,
    raise_for_error: Callable[[Any], None],
) -> None:
    """Remove a stale BlueZ bond before an explicit reset pairing attempt."""
    adapter_path = _bluez_adapter_path_for_device_path(device_path)
    if adapter_path is None:
        LOGGER.warning(
            "ble_bluez_direct_remove_device_skipped name=%s address=%s path=%s",
            name,
            address,
            device_path,
        )
        return
    try:
        LOGGER.warning(
            "ble_bluez_direct_remove_device_start name=%s address=%s path=%s adapter=%s",
            name,
            address,
            device_path,
            adapter_path,
        )
        reply = await asyncio.wait_for(
            bus.call(
                Message(
                    destination="org.bluez",
                    path=adapter_path,
                    interface="org.bluez.Adapter1",
                    member="RemoveDevice",
                    signature="o",
                    body=[device_path],
                )
            ),
            timeout=BLUEZ_SETUP_TIMEOUT,
        )
        raise_for_error(reply)
        LOGGER.warning(
            "ble_bluez_direct_remove_device_ok name=%s address=%s path=%s",
            name,
            address,
            device_path,
        )
    except Exception as err:
        LOGGER.warning(
            "ble_bluez_direct_remove_device_failed name=%s address=%s path=%s exception_chain=%s",
            name,
            address,
            device_path,
            _format_exception_chain(err),
        )


async def _bluez_device_path_for_address(
    bus: Any,
    *,
    address: str,
    Message: Any,
    raise_for_error: Callable[[Any], None],
    allow_fallback: bool = True,
) -> str:
    """Return the BlueZ object path for one device address."""
    normalized_address = address.casefold()
    reply = await bus.call(
        Message(
            destination="org.bluez",
            path="/",
            interface="org.freedesktop.DBus.ObjectManager",
            member="GetManagedObjects",
        )
    )
    raise_for_error(reply)
    managed_objects = reply.body[0] if reply.body else {}
    for object_path, interfaces in managed_objects.items():
        device_props = interfaces.get("org.bluez.Device1")
        if not isinstance(device_props, dict):
            continue
        candidate = device_props.get("Address")
        candidate_value = getattr(candidate, "value", candidate)
        if str(candidate_value).casefold() == normalized_address:
            return str(object_path)

    if allow_fallback:
        return f"/org/bluez/hci0/dev_{address.replace(':', '_').upper()}"

    raise IneproBleDeviceNotFoundError(f"BlueZ device {address} is not available")


async def _bluez_wait_for_device_path(
    bus: Any,
    *,
    address: str,
    Message: Any,
    raise_for_error: Callable[[Any], None],
    timeout: float,
) -> str:
    """Wait until BlueZ exposes a real Device1 object for the address."""
    LOGGER.warning(
        "ble_bluez_direct_wait_for_device_start address=%s timeout=%s",
        address,
        timeout,
    )
    deadline = asyncio.get_running_loop().time() + timeout
    last_error: BaseException | None = None
    while True:
        try:
            path = await asyncio.wait_for(
                _bluez_device_path_for_address(
                    bus,
                    address=address,
                    Message=Message,
                    raise_for_error=raise_for_error,
                    allow_fallback=False,
                ),
                timeout=BLUEZ_SETUP_TIMEOUT,
            )
            LOGGER.warning(
                "ble_bluez_direct_wait_for_device_ok address=%s path=%s",
                address,
                path,
            )
            return path
        except (IneproBleDeviceNotFoundError, TimeoutError) as err:
            last_error = err
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise IneproBleDeviceNotFoundError(
                    f"BlueZ device {address} was not rediscovered after reset"
                ) from last_error
            await asyncio.sleep(min(0.5, remaining))


@asynccontextmanager
async def _bluez_pairing_agent(
    *,
    name: str,
    pairing_timeout: float,
    pairing_pin: str | None,
    pairing_pin_provider: Callable[[], str | None | Awaitable[str | None]] | None,
    pairing_request_callback: Callable[[], None] | None = None,
):
    """Register an experimental temporary BlueZ pairing agent for PIN entry."""
    current_platform = platform.system()
    LOGGER.debug(
        "ble_bluez_pairing_agent_enter name=%s platform=%s has_pin=%s has_provider=%s",
        name,
        current_platform,
        pairing_pin is not None,
        pairing_pin_provider is not None,
    )
    if (
        current_platform != "Linux"
        or (pairing_pin is None and pairing_pin_provider is None)
    ):
        LOGGER.debug(
            "ble_bluez_pairing_agent_skipped name=%s platform=%s has_pin=%s has_provider=%s",
            name,
            current_platform,
            pairing_pin is not None,
            pairing_pin_provider is not None,
        )
        yield
        return

    try:
        LOGGER.debug("ble_bluez_pairing_agent_import_start name=%s", name)
        from dbus_fast import Message, MessageType
        from dbus_fast.aio import MessageBus
        from dbus_fast.constants import BusType
        from ._bluez_agent import IneproBlueZPairingAgent

        LOGGER.debug("ble_bluez_pairing_agent_import_ok name=%s", name)
    except ImportError as err:
        LOGGER.warning(
            "ble_bluez_pairing_agent_import_failed name=%s exception=%r",
            name,
            err,
        )
        raise IneproBlePairingUnsupportedError(
            "BlueZ PIN pairing requires dbus-fast on the Home Assistant host"
        ) from err

    def _raise_for_error(reply) -> None:
        if reply.message_type is MessageType.ERROR:
            message = reply.body[0] if reply.body else reply.error_name
            raise RuntimeError(str(message or reply.error_name))

    LOGGER.debug("ble_bluez_pairing_agent_connect_start name=%s", name)
    bus = await asyncio.wait_for(
        MessageBus(bus_type=BusType.SYSTEM).connect(),
        timeout=BLUEZ_SETUP_TIMEOUT,
    )
    LOGGER.debug("ble_bluez_pairing_agent_bus_connected name=%s", name)
    LOGGER.debug("ble_bluez_pairing_agent_construct_start name=%s", name)
    agent = IneproBlueZPairingAgent(
        name,
        pairing_timeout,
        pairing_pin,
        pairing_pin_provider,
        _normalize_pairing_pin,
        pairing_request_callback,
    )
    LOGGER.debug("ble_bluez_pairing_agent_construct_ok name=%s", name)
    agent_path = f"/org/inepro_metering/bluez_agent_{id(agent):x}"
    registered = False
    bus.export(agent_path, agent)
    try:
        LOGGER.debug(
            "ble_bluez_pairing_agent_register_start name=%s capability=KeyboardDisplay",
            name,
        )
        reply = await asyncio.wait_for(
            bus.call(
                Message(
                    destination="org.bluez",
                    path="/org/bluez",
                    interface="org.bluez.AgentManager1",
                    member="RegisterAgent",
                    signature="os",
                    body=[agent_path, "KeyboardDisplay"],
                )
            ),
            timeout=BLUEZ_SETUP_TIMEOUT,
        )
        _raise_for_error(reply)
        registered = True
        LOGGER.debug(
            "ble_bluez_pairing_agent_registered name=%s capability=KeyboardDisplay",
            name,
        )
        LOGGER.debug("ble_bluez_pairing_agent_default_start name=%s", name)
        reply = await asyncio.wait_for(
            bus.call(
                Message(
                    destination="org.bluez",
                    path="/org/bluez",
                    interface="org.bluez.AgentManager1",
                    member="RequestDefaultAgent",
                    signature="o",
                    body=[agent_path],
                )
            ),
            timeout=BLUEZ_SETUP_TIMEOUT,
        )
        _raise_for_error(reply)
        LOGGER.debug("ble_bluez_pairing_agent_default_registered name=%s", name)
        yield
    finally:
        if registered:
            try:
                reply = await bus.call(
                    Message(
                        destination="org.bluez",
                        path="/org/bluez",
                        interface="org.bluez.AgentManager1",
                        member="UnregisterAgent",
                        signature="o",
                        body=[agent_path],
                    )
                )
                _raise_for_error(reply)
            except Exception as err:
                LOGGER.debug(
                    "Failed to unregister BlueZ pairing agent for %s: %s",
                    name,
                    err,
                )
        bus.unexport(agent_path)
        bus.disconnect()


async def _read_gatt_device_information_from_client(
    client: Any,
    name: str,
) -> BleGattDeviceInformation:
    """Read the standard BLE Device Information characteristics from a client."""
    services = getattr(client, "services", None)
    characteristics = {
        "model": DEVICE_INFORMATION_MODEL_CHARACTERISTIC_UUID,
        "serial_number": DEVICE_INFORMATION_SERIAL_CHARACTERISTIC_UUID,
        "firmware_version": DEVICE_INFORMATION_FIRMWARE_CHARACTERISTIC_UUID,
        "ble_firmware_version": DEVICE_INFORMATION_BLE_FIRMWARE_CHARACTERISTIC_UUID,
        "manufacturer": DEVICE_INFORMATION_MANUFACTURER_CHARACTERISTIC_UUID,
    }
    available_characteristics = {
        field: uuid
        for field, uuid in characteristics.items()
        if services is None or _find_characteristic(services, uuid) is not None
    }
    if not available_characteristics:
        LOGGER.debug(
            "BLE Device Information service missing for %s",
            name,
        )
        raise IneproBleDeviceInformationMissingError(
            f"BLE Device Information service missing for {name}"
        )

    values: dict[str, str] = {}
    for field, uuid in available_characteristics.items():
        try:
            raw_value = await client.read_gatt_char(uuid)
        except Exception as err:
            LOGGER.debug(
                "Failed reading BLE Device Information %s for %s: %s",
                field,
                name,
                err,
            )
            continue
        decoded_value = _decode_gatt_text(raw_value)
        if decoded_value:
            values[field] = decoded_value

    if not values:
        raise IneproBleDeviceInformationMissingError(
            f"BLE Device Information service did not return values for {name}"
        )

    info = BleGattDeviceInformation(**values)
    LOGGER.debug(
        "BLE Device Information read for %s model=%s serial=%s firmware=%s ble_firmware=%s manufacturer=%s",
        name,
        info.model,
        info.serial_number,
        info.firmware_version,
        info.ble_firmware_version,
        info.manufacturer,
    )
    return info


def _find_characteristic(services: Any, uuid: str) -> Any | None:
    """Return a GATT characteristic by UUID from common Bleak service shapes."""
    get_characteristic = getattr(services, "get_characteristic", None)
    if callable(get_characteristic):
        characteristic = get_characteristic(uuid)
        if characteristic is not None:
            return characteristic

    normalized_uuid = uuid.casefold()
    try:
        iterable = services.values() if isinstance(services, dict) else services
        for service in iterable:
            characteristics = getattr(service, "characteristics", None)
            if characteristics is None and isinstance(service, dict):
                characteristics = service.get("characteristics")
            if characteristics is None:
                characteristics = (service,)
            for characteristic in characteristics:
                candidate_uuid = getattr(characteristic, "uuid", None)
                if candidate_uuid is None and isinstance(characteristic, dict):
                    candidate_uuid = characteristic.get("uuid")
                if str(candidate_uuid).casefold() == normalized_uuid:
                    return characteristic
    except TypeError:
        return None

    return None


def modbus_crc16(data: bytes) -> int:
    """Return the standard Modbus RTU CRC16 for the provided bytes."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def _decode_read_response(response: bytes, function_code: int) -> BleModbusResponse:
    """Decode a read-register RTU response."""
    exception = _decode_exception_response(response, function_code)
    if exception is not None:
        return exception

    byte_count = response[2]
    register_bytes = response[3 : 3 + byte_count]
    if byte_count % 2:
        return BleModbusResponse([], error="Odd byte count in Modbus read response")

    return BleModbusResponse(
        [
            (register_bytes[index] << 8) | register_bytes[index + 1]
            for index in range(0, byte_count, 2)
        ]
    )


def _decode_write_response(response: bytes, function_code: int) -> BleModbusResponse:
    """Decode a write-register RTU response."""
    exception = _decode_exception_response(response, function_code)
    if exception is not None:
        return exception
    return BleModbusResponse([])


def _decode_exception_response(
    response: bytes,
    function_code: int,
) -> BleModbusResponse | None:
    """Decode a Modbus exception response, if present."""
    if response[1] != (function_code | 0x80):
        return None
    return BleModbusResponse(
        [],
        error=f"Modbus exception response: function=0x{function_code:02X} code={response[2]}",
    )


def _expected_response_length(buffer: bytes, function_code: int) -> int | None:
    """Return the complete response length once enough header bytes are known."""
    if len(buffer) < 2:
        return None

    response_function = buffer[1]
    if response_function == (function_code | 0x80):
        return 5

    if response_function != function_code:
        return None

    if function_code in {
        FUNCTION_READ_HOLDING_REGISTERS,
        FUNCTION_READ_INPUT_REGISTERS,
    }:
        if len(buffer) < 3:
            return None
        return 5 + buffer[2]

    if function_code in {
        FUNCTION_WRITE_SINGLE_REGISTER,
        FUNCTION_WRITE_MULTIPLE_REGISTERS,
    }:
        return 8

    if function_code == FUNCTION_ENCAPSULATED_INTERFACE:
        if len(buffer) < 8:
            return None

        object_count = buffer[7]
        offset = 8
        for _ in range(object_count):
            if len(buffer) < offset + 2:
                return None
            object_length = buffer[offset + 1]
            offset += 2 + object_length
            if len(buffer) < offset:
                return None

        return offset + 2

    return None


def _has_valid_crc(frame: bytes) -> bool:
    """Return whether the final two bytes match the Modbus CRC."""
    if len(frame) < 4:
        return False
    expected = modbus_crc16(frame[:-2])
    received = frame[-2] | (frame[-1] << 8)
    return expected == received


def _uint16(value: int) -> bytes:
    """Encode one unsigned 16-bit integer in Modbus big-endian register order."""
    normalized = int(value) & 0xFFFF
    return bytes([(normalized >> 8) & 0xFF, normalized & 0xFF])


def _normalize_pairing_pin(pin: str | None) -> str | None:
    """Return a valid 6-digit Bluetooth pairing PIN or None."""
    if pin is None:
        return None
    normalized = str(pin).strip()
    if len(normalized) == 6 and normalized.isdigit():
        return normalized
    return None


def is_ble_pairing_trigger_error(err: BaseException) -> bool:
    """Return whether a BLE transaction failure can indicate missing pairing."""
    message = str(err).casefold()
    return any(
        marker in message
        for marker in (
            "insufficient authentication",
            "insufficient encryption",
            "authentication",
            "encryption",
            "encrypt",
            "pair",
            "not connected",
            "disconnected",
            "connection closed",
            "cancel send",
            "not permitted",
            "permission",
            "secure",
            "security",
            "protocol error 0x0f",
            "protocol error: 0x0f",
            "protocol error 0x05",
            "protocol error: 0x05",
            "protocol error 0x08",
            "protocol error: 0x08",
            "protocol error 0x0c",
            "protocol error: 0x0c",
            "att error: 0x05",
            "att error: 0x08",
            "att error: 0x0c",
            "att error: 0x0f",
            "0x05",
            "0x08",
            "0x0c",
            "0x0f",
        )
    )


def _requires_pairing(err: BaseException) -> bool:
    """Backward-compatible alias for pairing-trigger classification."""
    return is_ble_pairing_trigger_error(err)


def _pairing_unsupported(err: Exception) -> bool:
    """Return whether a backend reports that explicit pairing is unavailable."""
    if isinstance(err, (NotImplementedError, TypeError)):
        return True
    message = str(err).casefold()
    return any(
        marker in message
        for marker in (
            "pairing is not supported",
            "pairing not supported",
            "pair not supported",
            "unsupported pair",
            "unexpected keyword argument 'pair'",
            "explicit pairing",
        )
    )


def _format_exception_chain(err: BaseException) -> str:
    """Return a compact debug rendering of an exception cause chain."""
    parts: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = err
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        parts.append(f"{type(current).__name__}: {current}")
        current = current.__cause__ or current.__context__
    return " <- ".join(parts)


def _decode_gatt_text(value: Any) -> str | None:
    """Decode a text-ish GATT Device Information characteristic."""
    if value is None:
        return None
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, bytearray):
        value = bytes(value)
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="ignore")
    else:
        text = str(value)
    text = text.replace("\x00", "").strip()
    return text or None


def _decode_device_information_response(response: bytes) -> BleDeviceInformationResponse:
    """Decode a Modbus Read Device Identification response."""
    exception = _decode_exception_response(response, FUNCTION_ENCAPSULATED_INTERFACE)
    if exception is not None:
        return BleDeviceInformationResponse({}, error=exception.error)

    if len(response) < 10 or response[2] != MEI_READ_DEVICE_INFORMATION:
        return BleDeviceInformationResponse(
            {},
            error="Malformed Modbus device-identification response",
        )

    object_count = response[7]
    offset = 8
    information: dict[int, bytes] = {}

    for _ in range(object_count):
        if len(response) < offset + 2:
            return BleDeviceInformationResponse(
                {},
                error="Truncated Modbus device-identification response",
            )
        object_id = response[offset]
        object_length = response[offset + 1]
        offset += 2
        if len(response) < offset + object_length + 2:
            return BleDeviceInformationResponse(
                {},
                error="Truncated Modbus device-identification object payload",
            )
        information[object_id] = response[offset : offset + object_length]
        offset += object_length

    return BleDeviceInformationResponse(information)
