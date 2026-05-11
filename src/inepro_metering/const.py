"""Shared constants for the standalone Inepro Metering library."""

from __future__ import annotations

from enum import StrEnum

MAX_REGISTERS_PER_READ = 120


class MeterFamily(StrEnum):
    """Supported meter families."""

    GROW = "grow"
    PRO = "pro"


class TransportType(StrEnum):
    """Supported transport types."""

    SERIAL = "serial"
    TCP_GATEWAY = "tcp_gateway"
    TCP_WIFI = "tcp_wifi"
    TCP_ETHERNET = "tcp_ethernet"
    BLUETOOTH = "bluetooth"
    BLUETOOTH_PROXY = "bluetooth_proxy"


DEFAULT_BLUETOOTH_PROXY_HOST = "localhost"
DEFAULT_BLUETOOTH_PROXY_PORT = 15026
DEFAULT_BLUETOOTH_TIMEOUT = 10
DEFAULT_BLUETOOTH_PAIRING_TIMEOUT = 60


FAMILY_LABELS: dict[MeterFamily, str] = {
    MeterFamily.GROW: "GROW",
    MeterFamily.PRO: "PRO",
}

TRANSPORT_LABELS: dict[TransportType, str] = {
    TransportType.SERIAL: "Wired RS-485 / Modbus RTU",
    TransportType.TCP_GATEWAY: "Ambition Gateway",
    TransportType.TCP_WIFI: "Meter Wi-Fi",
    TransportType.TCP_ETHERNET: "Meter Ethernet",
    TransportType.BLUETOOTH: "Bluetooth",
    TransportType.BLUETOOTH_PROXY: "Windows BLE proxy (developer only)",
}
