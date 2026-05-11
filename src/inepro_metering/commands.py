"""Shared write plans and command helpers for Inepro Metering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

WIFI_SSID_ADDRESS = 0x4C32
WIFI_SSID_REGISTER_COUNT = 16
WIFI_PASSWORD_ADDRESS = 0x4C42
WIFI_PASSWORD_REGISTER_COUNT = 32
WIFI_ENABLE_ADDRESS = 0x4C06
WIFI_ENABLE_VALUE = 1
WIFI_APPLY_ADDRESS = 0x4C62
WIFI_APPLY_VALUE = 1


@dataclass(frozen=True, slots=True)
class RegisterWrite:
    """One holding-register write for a device command."""

    address: int
    values: tuple[int, ...]
    multiple: bool = True


class SupportsRegisterWrites(Protocol):
    """Minimal register-write surface shared by library commands."""

    async def async_write_register(self, address: int, value: int, slave_id: int) -> None:
        """Write one holding register."""

    async def async_write_registers(
        self,
        address: int,
        values: list[int],
        slave_id: int,
    ) -> None:
        """Write multiple holding registers."""


async def async_apply_register_writes(
    client: SupportsRegisterWrites,
    writes: tuple[RegisterWrite, ...],
    *,
    slave_id: int,
) -> None:
    """Apply an ordered register-write plan through one Modbus route."""
    for write in writes:
        if write.multiple:
            await client.async_write_registers(write.address, list(write.values), slave_id)
        else:
            await client.async_write_register(write.address, write.values[0], slave_id)


def build_wifi_credential_writes(
    ssid: str,
    password: str,
    *,
    apply: bool = True,
) -> tuple[RegisterWrite, ...]:
    """Build the ordered GROW register writes for Wi-Fi credentials."""
    writes = [
        RegisterWrite(
            address=WIFI_ENABLE_ADDRESS,
            values=(WIFI_ENABLE_VALUE,),
            multiple=False,
        ),
        RegisterWrite(
            address=WIFI_SSID_ADDRESS,
            values=encode_ascii_registers(
                ssid,
                register_count=WIFI_SSID_REGISTER_COUNT,
                field_name="SSID",
                allow_empty=False,
            ),
        ),
        RegisterWrite(
            address=WIFI_PASSWORD_ADDRESS,
            values=encode_ascii_registers(
                password,
                register_count=WIFI_PASSWORD_REGISTER_COUNT,
                field_name="Wi-Fi password",
            ),
        ),
    ]
    if apply:
        writes.append(RegisterWrite(address=WIFI_APPLY_ADDRESS, values=(WIFI_APPLY_VALUE,)))
    return tuple(writes)


def encode_ascii_registers(
    value: str,
    *,
    register_count: int,
    field_name: str,
    allow_empty: bool = True,
) -> tuple[int, ...]:
    """Encode an ASCII string into big-endian 16-bit Modbus registers."""
    if not allow_empty and not value:
        raise ValueError(f"{field_name} must not be empty")

    try:
        raw_value = value.encode("ascii")
    except UnicodeEncodeError as err:
        raise ValueError(f"{field_name} must contain ASCII characters only") from err

    max_bytes = register_count * 2
    if len(raw_value) > max_bytes:
        raise ValueError(f"{field_name} must be {max_bytes} ASCII characters or fewer")

    padded = raw_value.ljust(max_bytes, b"\x00")
    return tuple(
        (padded[index] << 8) | padded[index + 1]
        for index in range(0, max_bytes, 2)
    )
