"""Pure Python Modbus transport abstraction for Inepro Metering."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
import importlib
import inspect
import sys
from typing import Any

from pymodbus.client import AsyncModbusSerialClient, AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from .ble import (
    BleGattDeviceInformation,
    IneproBleDeviceInformationMissingError,
    IneproBleFrameTooLargeError,
    IneproBleModbusClient,
)
from .ble_proxy import IneproBleProxyModbusClient
from .const import (
    DEFAULT_BLUETOOTH_PAIRING_TIMEOUT,
    DEFAULT_BLUETOOTH_PROXY_PORT,
    DEFAULT_BLUETOOTH_TIMEOUT,
    TransportType,
)
from .exceptions import (
    IneproBluetoothNotPairedError,
    IneproConnectionError,
    IneproMeteringError,
    IneproReadError,
    IneproWriteError,
)
from .gateway_settings import (
    GATEWAY_MANAGEMENT_SLAVE_ID,
    GATEWAY_MODBUS_CONFIG_BLOCKS,
    GatewayConfiguration,
    decode_gateway_configuration_registers,
)
from .models import RegisterType

CONF_BLE_CLIENT_FACTORY = "ble_client_factory"
CONF_BLUETOOTH_ADDRESS = "bluetooth_address"
CONF_BLUETOOTH_DEVICE = "bluetooth_device"
CONF_BLUETOOTH_DEVICE_RESOLVER = "bluetooth_device_resolver"
CONF_BLUETOOTH_FORCE_REPAIR = "bluetooth_force_repair"
CONF_BLUETOOTH_PAIRING_MODE = "bluetooth_pairing_mode"
CONF_BLUETOOTH_PAIRING_PIN = "bluetooth_pairing_pin"
CONF_BLUETOOTH_PAIRING_PIN_PROVIDER = "bluetooth_pairing_pin_provider"
CONF_BLUETOOTH_PAIRING_TIMEOUT = "bluetooth_pairing_timeout"
CONF_BLUETOOTH_NAME = "bluetooth_name"
CONF_HOST = "host"
CONF_PORT = "port"
CONF_TIMEOUT = "timeout"
CONF_TRANSPORT = "transport"
CONF_SERIAL_PORT = "serial_port"
CONF_BAUDRATE = "baudrate"
CONF_BYTESIZE = "bytesize"
CONF_PARITY = "parity"
CONF_STOPBITS = "stopbits"

DEFAULT_PORT = 502
DEFAULT_TIMEOUT = 3
BLUETOOTH_PAIRING_MODE_NEVER = "never"
BLUETOOTH_PAIRING_MODE_AUTO = "auto"
BLUETOOTH_PAIRING_MODE_REQUIRED = "required"
WRITE_VERIFICATION_MAX_ATTEMPTS = 3
WRITE_VERIFICATION_RETRY_DELAY_SECONDS = 0.2
DEVICE_INFORMATION_BASIC = 0x01
DEVICE_INFORMATION_REGULAR = 0x02
DEVICE_INFORMATION_EXTENDED = 0x03
DEVICE_INFORMATION_SPECIFIC = 0x04

DEVICE_INFORMATION_OBJECT_MANUFACTURER = 0x00
DEVICE_INFORMATION_OBJECT_PRODUCT = 0x01
DEVICE_INFORMATION_OBJECT_VERSION = 0x02
DEVICE_INFORMATION_OBJECT_VENDOR_URL = 0x03
DEVICE_INFORMATION_OBJECT_PRODUCT_NAME = 0x04
DEVICE_INFORMATION_OBJECT_MODEL_NAME = 0x05
DEVICE_INFORMATION_OBJECT_USER_APPLICATION_NAME = 0x06

DEVICE_IDENTIFICATION_KEYS = {
    DEVICE_INFORMATION_OBJECT_MANUFACTURER: "modbus_manufacturer_name",
    DEVICE_INFORMATION_OBJECT_PRODUCT: "modbus_product_name",
    DEVICE_INFORMATION_OBJECT_VERSION: "modbus_device_version",
}

DEVICE_IDENTIFICATION_OBJECT_LABELS = {
    DEVICE_INFORMATION_OBJECT_MANUFACTURER: "VendorName",
    DEVICE_INFORMATION_OBJECT_PRODUCT: "ProductCode",
    DEVICE_INFORMATION_OBJECT_VERSION: "MajorMinorRevision",
    DEVICE_INFORMATION_OBJECT_VENDOR_URL: "VendorUrl",
    DEVICE_INFORMATION_OBJECT_PRODUCT_NAME: "ProductName",
    DEVICE_INFORMATION_OBJECT_MODEL_NAME: "ModelName",
    DEVICE_INFORMATION_OBJECT_USER_APPLICATION_NAME: "UserApplicationName",
}

TCP_GATEWAY_MANAGEMENT_SLAVE_ID = GATEWAY_MANAGEMENT_SLAVE_ID
TCP_GATEWAY_INFO_BLOCK_ADDRESS = 1024
TCP_GATEWAY_INFO_BLOCK_COUNT = 13
TCP_GATEWAY_DEVICE_INFO_FALLBACK_COUNT = 3
TCP_GATEWAY_FIRMWARE_ADDRESS = 1027
TCP_GATEWAY_VERSION_WORD_COUNT = 3
TCP_GATEWAY_BOOTLOADER_PATCH_ADDRESS = 1030
TCP_GATEWAY_BOOTLOADER_PATCH_COUNT = 1
TCP_GATEWAY_BOOTLOADER_MAJOR_MINOR_ADDRESS = 1035
TCP_GATEWAY_BOOTLOADER_MAJOR_MINOR_COUNT = 2
TCP_GATEWAY_PARITY_FIXER_FIRMWARE_TYPE = 11

TCP_GATEWAY_DEVICE_TYPES = {
    1: "TCP Gateway",
    2: "AC meter",
    330: "TCP Gateway",
}


@dataclass(frozen=True, slots=True)
class IneproDeviceIdentification:
    """Decoded Modbus Read Device Identification values."""

    manufacturer_name: str | None = None
    product_name: str | None = None
    version: str | None = None

    def as_readings(self) -> dict[str, str]:
        """Expose the decoded values using coordinator reading keys."""
        readings: dict[str, str] = {}
        if self.manufacturer_name:
            readings["modbus_manufacturer_name"] = self.manufacturer_name
        if self.product_name:
            readings["modbus_product_name"] = self.product_name
        if self.version:
            readings["modbus_device_version"] = self.version
        return readings


@dataclass(frozen=True, slots=True)
class IneproDeviceIdentificationObjects:
    """Normalized raw Modbus Read Device Identification objects."""

    read_code: int
    conformity_level: int | None = None
    objects: dict[int, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class IneproTcpGatewayInfo:
    """Decoded Ambition TCP gateway management metadata."""

    device_type_code: int | None = None
    device_type: str | None = None
    hardware_version: str | None = None
    serial_number: str | None = None
    firmware_type: int | None = None
    firmware_version: str | None = None
    bootloader_version: str | None = None

    def as_readings(self) -> dict[str, str | int]:
        """Expose decoded gateway metadata using coordinator reading keys."""
        readings: dict[str, str | int] = {}
        if self.device_type_code is not None:
            readings["tcp_gateway_device_type_code"] = self.device_type_code
        if self.device_type:
            readings["tcp_gateway_device_type"] = self.device_type
        if self.hardware_version:
            readings["tcp_gateway_hardware_version"] = self.hardware_version
        if self.serial_number:
            readings["tcp_gateway_serial_number"] = self.serial_number
        if self.firmware_type is not None:
            readings["tcp_gateway_firmware_type"] = self.firmware_type
        if self.firmware_version:
            readings["tcp_gateway_firmware_version"] = self.firmware_version
        if self.bootloader_version:
            readings["tcp_gateway_bootloader_version"] = self.bootloader_version
        return readings


class IneproModbusClient:
    """Thin async wrapper around pymodbus."""

    def __init__(self, config: Mapping[str, Any]) -> None:
        """Initialize the shared client wrapper."""
        self._config = dict(config)
        self._client: (
            AsyncModbusSerialClient
            | AsyncModbusTcpClient
            | IneproBleModbusClient
            | IneproBleProxyModbusClient
            | None
        ) = None
        self._lock = asyncio.Lock()

    async def async_ping(self) -> None:
        """Ensure the transport is reachable."""
        async with self._lock:
            await self._async_ensure_connected()

    async def async_read_registers(
        self,
        register_type: RegisterType,
        address: int,
        count: int,
        slave_id: int,
    ) -> list[int]:
        """Read one Modbus register block."""
        async with self._lock:
            return await self._async_read_register_block_locked(
                register_type=register_type,
                address=address,
                count=count,
                slave_id=slave_id,
            )

    async def async_write_register(
        self,
        address: int,
        value: int,
        slave_id: int,
    ) -> None:
        """Write one Modbus holding register."""
        async with self._lock:
            await self._async_write_and_verify_locked(
                address=address,
                values=[int(value)],
                slave_id=slave_id,
            )

    async def async_write_registers(
        self,
        address: int,
        values: list[int],
        slave_id: int,
    ) -> None:
        """Write a Modbus holding register block."""
        async with self._lock:
            await self._async_write_and_verify_locked(
                address=address,
                values=[int(value) for value in values],
                slave_id=slave_id,
            )

    async def async_read_device_identification(
        self,
        slave_id: int,
    ) -> IneproDeviceIdentification:
        """Read the Modbus device-identification basic objects."""
        async with self._lock:
            objects = await self._async_read_device_identification_objects_locked(
                slave_id,
                read_code=DEVICE_INFORMATION_BASIC,
                object_id=0x00,
            )
            return _decode_device_identification(objects.objects)

    async def async_read_bluetooth_device_information(
        self,
    ) -> BleGattDeviceInformation:
        """Read BLE GATT Device Information for direct Bluetooth transports."""
        async with self._lock:
            client = await self._async_ensure_connected()
            read_gatt_device_information = getattr(
                client,
                "read_gatt_device_information",
                None,
            )
            if read_gatt_device_information is None:
                raise IneproReadError(
                    "Modbus transport does not expose BLE Device Information"
                )

            try:
                return await read_gatt_device_information()
            except IneproBleDeviceInformationMissingError as err:
                raise IneproReadError("BLE Device Information service is missing") from err
            except Exception as err:
                await self._async_reset_client()
                raise IneproReadError(
                    "Unexpected BLE Device Information read failure"
                ) from err

    async def async_read_device_identification_objects(
        self,
        slave_id: int,
        *,
        read_code: int = DEVICE_INFORMATION_BASIC,
        object_id: int = 0x00,
    ) -> IneproDeviceIdentificationObjects:
        """Read normalized Modbus device-identification objects.

        This is useful for probing richer regular or extended 43/14 responses
        from bridges and gateways that expose more than the mandatory basic
        three objects.
        """
        async with self._lock:
            return await self._async_read_device_identification_objects_locked(
                slave_id,
                read_code=read_code,
                object_id=object_id,
            )

    async def async_read_tcp_gateway_info(
        self,
        *,
        slave_id: int = TCP_GATEWAY_MANAGEMENT_SLAVE_ID,
    ) -> IneproTcpGatewayInfo:
        """Read vendor-specific Ambition TCP gateway metadata registers."""
        async with self._lock:
            return await self._async_read_tcp_gateway_info_locked(slave_id=slave_id)

    async def async_read_tcp_gateway_configuration(
        self,
        *,
        slave_id: int = TCP_GATEWAY_MANAGEMENT_SLAVE_ID,
    ) -> GatewayConfiguration:
        """Read vendor-specific Ambition TCP gateway configuration registers."""
        async with self._lock:
            return await self._async_read_tcp_gateway_configuration_locked(
                slave_id=slave_id
            )

    async def async_close(self) -> None:
        """Close the underlying Modbus client."""
        async with self._lock:
            await self._async_reset_client()

    async def _async_ensure_connected(
        self,
    ) -> (
        AsyncModbusSerialClient
        | AsyncModbusTcpClient
        | IneproBleModbusClient
        | IneproBleProxyModbusClient
    ):
        """Create and connect the underlying client as needed."""
        await self._async_prepare_transport()

        if self._client is None:
            self._client = _build_client(self._config)

        if self._client.connected:
            return self._client

        try:
            connected = await self._client.connect()
        except IneproBluetoothNotPairedError:
            await self._async_reset_client()
            raise
        except Exception as err:
            await self._async_reset_client()
            raise IneproConnectionError("Could not open the Modbus transport") from err

        if not connected:
            await self._async_reset_client()
            raise IneproConnectionError("Modbus transport did not connect")

        return self._client

    async def _async_prepare_transport(self) -> None:
        """Prepare transport-specific modules that can block on first import."""
        if (
            TransportType(self._config[CONF_TRANSPORT]) is TransportType.SERIAL
            and "://" in str(self._config[CONF_SERIAL_PORT])
        ):
            await asyncio.to_thread(
                _prepare_serial_url_handler,
                str(self._config[CONF_SERIAL_PORT]),
            )

    async def _async_reset_client(self) -> None:
        """Close and drop the underlying client."""
        client = self._client
        self._client = None

        if client is None:
            return

        if self._requires_threaded_close():
            await asyncio.to_thread(client.close)
            return

        close_result = client.close()
        if inspect.isawaitable(close_result):
            await close_result

    async def _async_read_device_identification_objects_locked(
        self,
        slave_id: int,
        *,
        read_code: int,
        object_id: int,
    ) -> IneproDeviceIdentificationObjects:
        """Read one or more normalized 43/14 identification pages."""
        if not 0x00 <= int(object_id) <= 0xFF:
            raise IneproReadError("Modbus device-identification object ID out of range")
        if int(read_code) not in {
            DEVICE_INFORMATION_BASIC,
            DEVICE_INFORMATION_REGULAR,
            DEVICE_INFORMATION_EXTENDED,
            DEVICE_INFORMATION_SPECIFIC,
        }:
            raise IneproReadError("Unsupported Modbus device-identification read code")

        client = await self._async_ensure_connected()
        normalized_objects: dict[int, str] = {}
        conformity_level: int | None = None
        current_object_id = int(object_id)
        seen_object_ids: set[int] = set()

        while True:
            if current_object_id in seen_object_ids:
                raise IneproReadError("Modbus device-identification pagination loop detected")
            seen_object_ids.add(current_object_id)

            response = await self._async_read_device_identification_response_locked(
                client,
                slave_id=slave_id,
                read_code=int(read_code),
                object_id=current_object_id,
            )
            conformity = getattr(response, "conformity", None)
            if isinstance(conformity, int):
                conformity_level = conformity

            information = getattr(response, "information", None)
            if not isinstance(information, dict):
                raise IneproReadError("Malformed Modbus device-identification response")
            normalized_objects.update(_normalize_device_identification_objects(information))

            if int(read_code) == DEVICE_INFORMATION_SPECIFIC:
                break

            more_follows = getattr(response, "more_follows", 0)
            next_object_id = getattr(response, "next_object_id", 0)
            if int(more_follows) == 0:
                break
            current_object_id = int(next_object_id)

        return IneproDeviceIdentificationObjects(
            read_code=int(read_code),
            conformity_level=conformity_level,
            objects=normalized_objects,
        )

    async def _async_read_device_identification_response_locked(
        self,
        client: (
            AsyncModbusSerialClient
            | AsyncModbusTcpClient
            | IneproBleModbusClient
            | IneproBleProxyModbusClient
        ),
        *,
        slave_id: int,
        read_code: int,
        object_id: int,
    ) -> Any:
        """Issue one raw pymodbus Read Device Identification request."""
        read_device_information = getattr(client, "read_device_information", None)
        if read_device_information is None:
            raise IneproReadError("Modbus transport does not support device identification")

        try:
            response = await read_device_information(
                read_code=read_code,
                object_id=object_id,
                device_id=slave_id,
            )
        except IneproBluetoothNotPairedError:
            await self._async_reset_client()
            raise
        except ModbusException as err:
            await self._async_reset_client()
            raise IneproReadError("Modbus device-identification request failed") from err
        except Exception as err:
            await self._async_reset_client()
            raise IneproReadError("Unexpected Modbus device-identification failure") from err

        if response.isError():
            raise IneproReadError(f"Modbus device-identification error response: {response}")

        return response

    async def _async_read_register_block_locked(
        self,
        *,
        register_type: RegisterType,
        address: int,
        count: int,
        slave_id: int,
    ) -> list[int]:
        """Read one Modbus register block while holding the client lock."""
        client = await self._async_ensure_connected()

        try:
            if register_type is RegisterType.HOLDING:
                response = await client.read_holding_registers(
                    address,
                    count=count,
                    device_id=slave_id,
                )
            else:
                response = await client.read_input_registers(
                    address,
                    count=count,
                    device_id=slave_id,
                )
        except IneproBluetoothNotPairedError:
            await self._async_reset_client()
            raise
        except ModbusException as err:
            await self._async_reset_client()
            raise IneproReadError("Modbus request failed") from err
        except Exception as err:
            await self._async_reset_client()
            raise IneproReadError("Unexpected Modbus read failure") from err

        if response.isError():
            raise IneproReadError(f"Modbus error response: {response}")

        return list(response.registers)

    async def _async_read_tcp_gateway_info_locked(
        self,
        *,
        slave_id: int,
    ) -> IneproTcpGatewayInfo:
        """Read and decode the gateway metadata registers used by the vendor tool."""
        device_type_code: int | None = None
        hardware_version: str | None = None
        firmware_type: int | None = None
        serial_number: str | None = None
        firmware_version: str | None = None
        bootloader_version: str | None = None

        try:
            registers = await self._async_read_register_block_locked(
                register_type=RegisterType.HOLDING,
                address=TCP_GATEWAY_INFO_BLOCK_ADDRESS,
                count=TCP_GATEWAY_INFO_BLOCK_COUNT,
                slave_id=slave_id,
            )
        except IneproReadError:
            registers = []

        if len(registers) >= TCP_GATEWAY_INFO_BLOCK_COUNT:
            device_type_code = int(registers[0])
            hardware_version = _format_tcp_gateway_hardware_version(int(registers[1]))
            firmware_type = int(registers[2])
            firmware_version = _format_tcp_gateway_version(
                int(registers[3]),
                int(registers[4]),
                int(registers[5]),
            )
            bootloader_version = _format_tcp_gateway_version(
                int(registers[11]),
                int(registers[12]),
                int(registers[6]),
            )
            serial_number = _format_tcp_gateway_serial(registers[8:11])
        else:
            try:
                device_info = await self._async_read_register_block_locked(
                    register_type=RegisterType.HOLDING,
                    address=TCP_GATEWAY_INFO_BLOCK_ADDRESS,
                    count=TCP_GATEWAY_DEVICE_INFO_FALLBACK_COUNT,
                    slave_id=slave_id,
                )
            except IneproReadError:
                device_info = []
            if len(device_info) >= TCP_GATEWAY_DEVICE_INFO_FALLBACK_COUNT:
                device_type_code = int(device_info[0])
                hardware_version = _format_tcp_gateway_hardware_version(int(device_info[1]))
                firmware_type = int(device_info[2])

            try:
                firmware_info = await self._async_read_register_block_locked(
                    register_type=RegisterType.HOLDING,
                    address=TCP_GATEWAY_FIRMWARE_ADDRESS,
                    count=TCP_GATEWAY_VERSION_WORD_COUNT,
                    slave_id=slave_id,
                )
            except IneproReadError:
                firmware_info = []
            if len(firmware_info) >= TCP_GATEWAY_VERSION_WORD_COUNT:
                firmware_version = _format_tcp_gateway_version(
                    int(firmware_info[0]),
                    int(firmware_info[1]),
                    int(firmware_info[2]),
                )

            try:
                bootloader_patch = await self._async_read_register_block_locked(
                    register_type=RegisterType.HOLDING,
                    address=TCP_GATEWAY_BOOTLOADER_PATCH_ADDRESS,
                    count=TCP_GATEWAY_BOOTLOADER_PATCH_COUNT,
                    slave_id=slave_id,
                )
            except IneproReadError:
                bootloader_patch = []

            try:
                bootloader_major_minor = await self._async_read_register_block_locked(
                    register_type=RegisterType.HOLDING,
                    address=TCP_GATEWAY_BOOTLOADER_MAJOR_MINOR_ADDRESS,
                    count=TCP_GATEWAY_BOOTLOADER_MAJOR_MINOR_COUNT,
                    slave_id=slave_id,
                )
            except IneproReadError:
                bootloader_major_minor = []

            if (
                len(bootloader_patch) >= TCP_GATEWAY_BOOTLOADER_PATCH_COUNT
                and len(bootloader_major_minor) >= TCP_GATEWAY_BOOTLOADER_MAJOR_MINOR_COUNT
            ):
                bootloader_version = _format_tcp_gateway_version(
                    int(bootloader_major_minor[0]),
                    int(bootloader_major_minor[1]),
                    int(bootloader_patch[0]),
                )
            elif len(bootloader_patch) >= TCP_GATEWAY_BOOTLOADER_PATCH_COUNT:
                bootloader_version = str(int(bootloader_patch[0]))

        return IneproTcpGatewayInfo(
            device_type_code=device_type_code,
            device_type=_decode_tcp_gateway_device_type(device_type_code),
            hardware_version=hardware_version,
            serial_number=serial_number,
            firmware_type=firmware_type,
            firmware_version=firmware_version,
            bootloader_version=bootloader_version,
        )

    async def _async_read_tcp_gateway_configuration_locked(
        self,
        *,
        slave_id: int,
    ) -> GatewayConfiguration:
        """Read and decode the gateway configuration blocks used by the vendor tool."""
        blocks: dict[int, list[int]] = {}
        for start_address, count in GATEWAY_MODBUS_CONFIG_BLOCKS:
            blocks[start_address] = await self._async_read_register_block_locked(
                register_type=RegisterType.HOLDING,
                address=start_address,
                count=count,
                slave_id=slave_id,
            )

        modbus_block_start, _ = GATEWAY_MODBUS_CONFIG_BLOCKS[0]
        network_block_start, _ = GATEWAY_MODBUS_CONFIG_BLOCKS[1]
        return decode_gateway_configuration_registers(
            modbus_registers=blocks[modbus_block_start],
            network_registers=blocks[network_block_start],
        )

    def _requires_threaded_close(self) -> bool:
        """Return whether closing the configured transport can block the event loop."""
        return (
            TransportType(self._config[CONF_TRANSPORT]) is TransportType.SERIAL
            and "://" in str(self._config[CONF_SERIAL_PORT])
        )

    async def _async_write_and_verify_locked(
        self,
        *,
        address: int,
        values: list[int],
        slave_id: int,
    ) -> None:
        """Write holding registers and confirm the applied values by reading them back."""
        expected_values = [int(value) & 0xFFFF for value in values]
        last_error: IneproWriteError | None = None

        for attempt in range(1, WRITE_VERIFICATION_MAX_ATTEMPTS + 1):
            client = await self._async_ensure_connected()
            try:
                await self._async_issue_write_locked(
                    client,
                    address=address,
                    values=expected_values,
                    slave_id=slave_id,
                )
                await self._async_verify_write_locked(
                    client,
                    address=address,
                    expected_values=expected_values,
                    slave_id=slave_id,
                )
                return
            except IneproWriteError as err:
                last_error = err

            await self._async_reset_client()
            if attempt < WRITE_VERIFICATION_MAX_ATTEMPTS:
                await asyncio.sleep(WRITE_VERIFICATION_RETRY_DELAY_SECONDS)

        assert last_error is not None
        raise last_error

    async def _async_issue_write_locked(
        self,
        client: (
            AsyncModbusSerialClient
            | AsyncModbusTcpClient
            | IneproBleModbusClient
            | IneproBleProxyModbusClient
        ),
        *,
        address: int,
        values: list[int],
        slave_id: int,
    ) -> None:
        """Issue the underlying Modbus write request."""
        try:
            if len(values) == 1:
                response = await client.write_register(
                    address,
                    values[0],
                    device_id=slave_id,
                )
            else:
                response = await client.write_registers(
                    address,
                    values,
                    device_id=slave_id,
                )
        except IneproBluetoothNotPairedError:
            await self._async_reset_client()
            raise
        except ModbusException as err:
            raise IneproWriteError("Modbus write request failed") from err
        except IneproBleFrameTooLargeError as err:
            raise IneproWriteError(str(err)) from err
        except Exception as err:
            raise IneproWriteError("Unexpected Modbus write failure") from err

        if response.isError():
            raise IneproWriteError(f"Modbus write error response: {response}")

    async def _async_verify_write_locked(
        self,
        client: (
            AsyncModbusSerialClient
            | AsyncModbusTcpClient
            | IneproBleModbusClient
            | IneproBleProxyModbusClient
        ),
        *,
        address: int,
        expected_values: list[int],
        slave_id: int,
    ) -> None:
        """Read back written holding registers and confirm the values match."""
        try:
            response = await client.read_holding_registers(
                address,
                count=len(expected_values),
                device_id=slave_id,
            )
        except IneproBluetoothNotPairedError:
            await self._async_reset_client()
            raise
        except ModbusException as err:
            raise IneproWriteError("Modbus write verification read failed") from err
        except Exception as err:
            raise IneproWriteError("Unexpected Modbus write verification failure") from err

        if response.isError():
            raise IneproWriteError(
                f"Modbus write verification error response: {response}"
            )

        actual_values = [int(value) & 0xFFFF for value in response.registers]
        if actual_values != expected_values:
            raise IneproWriteError(
                "Modbus write verification mismatch at "
                f"0x{address:04X}: expected {expected_values}, got {actual_values}"
            )


async def async_validate_modbus_config(config: Mapping[str, Any]) -> None:
    """Validate a connection by opening the configured transport."""
    client = IneproModbusClient(config)
    try:
        await client.async_ping()
    finally:
        await client.async_close()


def _build_client(
    config: Mapping[str, Any],
) -> (
    AsyncModbusSerialClient
    | AsyncModbusTcpClient
    | IneproBleModbusClient
    | IneproBleProxyModbusClient
):
    """Create a pymodbus client for the selected transport."""
    transport = TransportType(config[CONF_TRANSPORT])
    timeout = float(
        config.get(
            CONF_TIMEOUT,
            DEFAULT_BLUETOOTH_TIMEOUT
            if transport in {TransportType.BLUETOOTH, TransportType.BLUETOOTH_PROXY}
            else DEFAULT_TIMEOUT,
        )
    )

    if transport is TransportType.SERIAL:
        return AsyncModbusSerialClient(
            port=str(config[CONF_SERIAL_PORT]),
            baudrate=int(config[CONF_BAUDRATE]),
            bytesize=int(config[CONF_BYTESIZE]),
            parity=str(config[CONF_PARITY]),
            stopbits=int(config[CONF_STOPBITS]),
            timeout=timeout,
            retries=1,
            reconnect_delay=0,
        )

    if transport in {
        TransportType.TCP_GATEWAY,
        TransportType.TCP_WIFI,
        TransportType.TCP_ETHERNET,
    }:
        return AsyncModbusTcpClient(
            host=str(config[CONF_HOST]),
            port=int(config.get(CONF_PORT, DEFAULT_PORT)),
            timeout=timeout,
            retries=1,
            reconnect_delay=0,
        )

    if transport is TransportType.BLUETOOTH:
        return IneproBleModbusClient(
            address=str(config[CONF_BLUETOOTH_ADDRESS]),
            name=str(config.get(CONF_BLUETOOTH_NAME) or config[CONF_BLUETOOTH_ADDRESS]),
            timeout=timeout,
            ble_device=config.get(CONF_BLUETOOTH_DEVICE),
            ble_device_resolver=config.get(CONF_BLUETOOTH_DEVICE_RESOLVER),
            client_factory=config.get(CONF_BLE_CLIENT_FACTORY),
            pairing_mode=str(
                config.get(CONF_BLUETOOTH_PAIRING_MODE, BLUETOOTH_PAIRING_MODE_AUTO)
            ),
            pairing_timeout=float(
                config.get(
                    CONF_BLUETOOTH_PAIRING_TIMEOUT,
                    DEFAULT_BLUETOOTH_PAIRING_TIMEOUT,
                )
            ),
            pairing_pin=(
                str(config[CONF_BLUETOOTH_PAIRING_PIN])
                if config.get(CONF_BLUETOOTH_PAIRING_PIN) is not None
                else None
            ),
            pairing_pin_provider=config.get(CONF_BLUETOOTH_PAIRING_PIN_PROVIDER),
            force_repair=bool(config.get(CONF_BLUETOOTH_FORCE_REPAIR, False)),
        )

    if transport is TransportType.BLUETOOTH_PROXY:
        return IneproBleProxyModbusClient(
            host=str(config[CONF_HOST]),
            port=int(config.get(CONF_PORT, DEFAULT_BLUETOOTH_PROXY_PORT)),
            timeout=timeout,
            address=str(config[CONF_BLUETOOTH_ADDRESS]),
            name=str(config.get(CONF_BLUETOOTH_NAME) or config[CONF_BLUETOOTH_ADDRESS]),
        )

    raise IneproMeteringError(f"Unsupported transport type: {transport}")


def _prepare_serial_url_handler(serial_port: str) -> None:
    """Preload pyserial URL handlers so socket-based ports do not import on the event loop."""
    if "://" not in serial_port:
        return

    scheme = serial_port.split("://", 1)[0].strip().lower()
    if not scheme:
        return

    importlib.import_module("serial.urlhandler")
    importlib.import_module(f"serial.urlhandler.protocol_{scheme}")
    _install_cached_serial_url_dispatch()


def _install_cached_serial_url_dispatch() -> None:
    """Patch pyserial's URL dispatch to reuse already imported handler modules."""
    import serial

    if getattr(serial, "_inepro_cached_serial_for_url_installed", False):
        return

    original_serial_for_url = serial.serial_for_url

    def cached_serial_for_url(url, *args, **kwargs):
        """Resolve already loaded URL handlers without calling importlib on the event loop."""
        try:
            url_lowercase = url.lower()
        except AttributeError:
            return original_serial_for_url(url, *args, **kwargs)

        if "://" not in url_lowercase:
            return original_serial_for_url(url, *args, **kwargs)

        protocol = url_lowercase.split("://", 1)[0]
        if not protocol:
            return original_serial_for_url(url, *args, **kwargs)

        package_name = "serial.urlhandler"
        module_name = f"{package_name}.protocol_{protocol}"
        package_module = sys.modules.get(package_name)
        handler_module = sys.modules.get(module_name)
        if package_module is None or handler_module is None:
            return original_serial_for_url(url, *args, **kwargs)

        do_open = not kwargs.pop("do_not_open", False)
        if hasattr(handler_module, "serial_class_for_url"):
            url, klass = handler_module.serial_class_for_url(url)
        else:
            klass = handler_module.Serial

        instance = klass(None, *args, **kwargs)
        instance.port = url
        if do_open:
            instance.open()
        return instance

    serial.serial_for_url = cached_serial_for_url
    serial._inepro_cached_serial_for_url_installed = True


def _decode_device_identification(
    information: dict[int, Any],
) -> IneproDeviceIdentification:
    """Decode pymodbus Read Device Identification objects into named values."""
    decoded: dict[str, str] = {}
    for object_id, key in DEVICE_IDENTIFICATION_KEYS.items():
        value = information.get(object_id)
        decoded_value = _decode_device_identification_value(value)
        if decoded_value is not None:
            decoded[key] = decoded_value

    return IneproDeviceIdentification(
        manufacturer_name=decoded.get("modbus_manufacturer_name"),
        product_name=decoded.get("modbus_product_name"),
        version=decoded.get("modbus_device_version"),
    )


def _normalize_device_identification_objects(
    information: dict[int, Any],
) -> dict[int, str]:
    """Decode all returned 43/14 objects into normalized text values."""
    decoded: dict[int, str] = {}
    for object_id, value in information.items():
        decoded_value = _decode_device_identification_value(value)
        if decoded_value is not None:
            decoded[int(object_id)] = decoded_value
    return decoded


def _decode_device_identification_value(value: Any) -> str | None:
    """Normalize one Read Device Identification object value into text."""
    if isinstance(value, list):
        if not value:
            return None
        value = value[0]

    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="ignore")
    elif value is None:
        return None
    else:
        text = str(value)

    normalized = text.replace("\x00", "").strip()
    return normalized or None


def _decode_tcp_gateway_device_type(device_type_code: int | None) -> str | None:
    """Return the user-facing gateway device type from the vendor code."""
    if device_type_code is None:
        return None
    if device_type_code in TCP_GATEWAY_DEVICE_TYPES:
        return TCP_GATEWAY_DEVICE_TYPES[device_type_code]
    return f"unknown ({device_type_code})"


def _format_tcp_gateway_serial(words: list[int]) -> str | None:
    """Format the three gateway serial words the same way as the vendor tool."""
    if len(words) < 3:
        return None
    return "".join(f"{int(word) & 0xFFFF:04x}" for word in words[:3])


def _format_tcp_gateway_version(major: int, minor: int, patch: int) -> str:
    """Format one vendor-specific dotted gateway version string."""
    return f"{int(major)}.{int(minor)}.{int(patch)}"


def _format_tcp_gateway_hardware_version(value: int) -> str:
    """Format the gateway hardware revision the way the old tool displays it."""
    return str(int(value))
