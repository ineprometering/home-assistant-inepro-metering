"""TCP bridge for running Inepro GROW BLE transport through a local host proxy."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from typing import Any

from .ble import (
    BleDeviceInformationResponse,
    BleModbusResponse,
    FUNCTION_ENCAPSULATED_INTERFACE,
    FUNCTION_READ_HOLDING_REGISTERS,
    FUNCTION_READ_INPUT_REGISTERS,
    FUNCTION_WRITE_MULTIPLE_REGISTERS,
    FUNCTION_WRITE_SINGLE_REGISTER,
    _decode_device_information_response,
    _decode_read_response,
    _decode_write_response,
    build_rtu_frame,
)

PROXY_ACTION_PING = "ping"
PROXY_ACTION_SCAN = "scan"
PROXY_ACTION_TRANSCEIVE = "transceive"


class IneproBleProxyModbusClient:
    """Modbus RTU-over-BLE proxy client for Home Assistant running outside Windows."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        timeout: float,
        address: str,
        name: str | None = None,
    ) -> None:
        """Initialize the proxy client."""
        self._host = host
        self._port = int(port)
        self._timeout = float(timeout)
        self._address = address
        self._name = name or address
        self._connected = False

    @property
    def connected(self) -> bool:
        """Return whether the last ping to the proxy succeeded."""
        return self._connected

    async def connect(self) -> bool:
        """Reach the Windows BLE proxy."""
        await self._async_request({ "action": PROXY_ACTION_PING })
        self._connected = True
        return True

    def close(self) -> None:
        """Close the proxy client."""
        self._connected = False

    async def read_holding_registers(
        self,
        address: int,
        *,
        count: int,
        device_id: int,
    ) -> BleModbusResponse:
        """Read holding registers through the Windows BLE proxy."""
        payload = _uint16(address) + _uint16(count)
        frame = build_rtu_frame(device_id, FUNCTION_READ_HOLDING_REGISTERS, payload)
        response = await self.async_transceive_frame(
            frame,
            slave_id=device_id,
            function_code=FUNCTION_READ_HOLDING_REGISTERS,
        )
        return _decode_read_response(response, FUNCTION_READ_HOLDING_REGISTERS)

    async def read_input_registers(
        self,
        address: int,
        *,
        count: int,
        device_id: int,
    ) -> BleModbusResponse:
        """Read input registers through the Windows BLE proxy."""
        payload = _uint16(address) + _uint16(count)
        frame = build_rtu_frame(device_id, FUNCTION_READ_INPUT_REGISTERS, payload)
        response = await self.async_transceive_frame(
            frame,
            slave_id=device_id,
            function_code=FUNCTION_READ_INPUT_REGISTERS,
        )
        return _decode_read_response(response, FUNCTION_READ_INPUT_REGISTERS)

    async def write_register(
        self,
        address: int,
        value: int,
        *,
        device_id: int,
    ) -> BleModbusResponse:
        """Write one holding register through the Windows BLE proxy."""
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
        values: list[int],
        *,
        device_id: int,
    ) -> BleModbusResponse:
        """Write a holding register block through the Windows BLE proxy."""
        normalized_values = tuple(int(value) & 0xFFFF for value in values)
        payload = (
            _uint16(address)
            + _uint16(len(normalized_values))
            + bytes([len(normalized_values) * 2])
            + b"".join(_uint16(value) for value in normalized_values)
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
        """Read Modbus device-identification objects through the Windows BLE proxy."""
        del no_response_expected
        payload = bytes([0x0E, int(read_code or 0x01) & 0xFF, int(object_id) & 0xFF])
        frame = build_rtu_frame(device_id, FUNCTION_ENCAPSULATED_INTERFACE, payload)
        response = await self.async_transceive_frame(
            frame,
            slave_id=device_id,
            function_code=FUNCTION_ENCAPSULATED_INTERFACE,
        )
        return _decode_device_information_response(response)

    async def async_transceive_frame(
        self,
        frame: bytes,
        *,
        slave_id: int | None = None,
        function_code: int | None = None,
    ) -> bytes:
        """Send a raw Modbus RTU frame through the Windows BLE proxy."""
        del slave_id, function_code
        response = await self._async_request(
            {
                "action": PROXY_ACTION_TRANSCEIVE,
                "address": self._address,
                "name": self._name,
                "timeout": self._timeout,
                "frame": frame.hex(),
            }
        )
        response_hex = response.get("response")
        if not isinstance(response_hex, str) or not response_hex:
            raise RuntimeError("Malformed BLE proxy response payload")
        return bytes.fromhex(response_hex)

    async def _async_request(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Send one JSON request to the proxy and read one JSON response."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port),
                timeout=self._timeout,
            )
        except Exception:
            self._connected = False
            raise

        try:
            request_bytes = json.dumps(dict(payload), separators=(",", ":")).encode("utf-8") + b"\n"
            writer.write(request_bytes)
            await asyncio.wait_for(writer.drain(), timeout=self._timeout)
            raw_response = await asyncio.wait_for(reader.readline(), timeout=self._timeout)
            if not raw_response:
                raise RuntimeError("BLE proxy closed the connection without a response")
            response = json.loads(raw_response.decode("utf-8"))
        finally:
            writer.close()
            await writer.wait_closed()

        if not isinstance(response, dict):
            raise RuntimeError("BLE proxy returned a non-object response")
        if not response.get("ok", False):
            raise RuntimeError(str(response.get("error") or "BLE proxy request failed"))

        self._connected = True
        return response


def _uint16(value: int) -> bytes:
    """Encode one unsigned 16-bit integer in Modbus register byte order."""
    normalized = int(value) & 0xFFFF
    return bytes([(normalized >> 8) & 0xFF, normalized & 0xFF])
