"""Shared TCP gateway configuration definitions for Inepro Metering."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import ipaddress
import re
from typing import Literal

from .commands import RegisterWrite, encode_ascii_registers
from .const import TransportType

GatewayEntityPlatform = Literal["switch", "select", "number", "text"]
GatewayReadingValue = bool | str | int | float
GatewaySettingValue = bool | float | str | None

GATEWAY_MANAGEMENT_SLAVE_ID = 0xFF

CONFIG_MODBUS_BAUDRATE = 0x0000
CONFIG_MODBUS_PARITY = 0x0001
CONFIG_MODBUS_UART_DEVICE = 0x0002
CONFIG_MODBUS_TIMEOUT = 0x0003
CONFIG_MODBUS_DEVICEID = 0x0004

CONFIG_IP_HIGH = 0x0064
CONFIG_IP_LOW = 0x0065
CONFIG_NETMASK_HIGH = 0x0066
CONFIG_NETMASK_LOW = 0x0067
CONFIG_GATEWAY_HIGH = 0x0068
CONFIG_GATEWAY_LOW = 0x0069
CONFIG_DHCP_ENABLED = 0x006A
CONFIG_DNS_SERVER_HIGH = 0x006B
CONFIG_DNS_SERVER_LOW = 0x006C
CONFIG_NTP_SERVER_HIGH = 0x006D
CONFIG_NTP_SERVER_LOW = 0x006E
CONFIG_SECONDARY_DNS_SERVER_HIGH = 0x006F
CONFIG_SECONDARY_DNS_SERVER_LOW = 0x0070
CONFIG_SECONDARY_NTP_SERVER_HIGH = 0x0071
CONFIG_SECONDARY_NTP_SERVER_LOW = 0x0072
CONFIG_HOSTNAME_START = 0x0073
CONFIG_HOSTNAME_END = 0x0082
CONFIG_NTP_SUPPORT_ENABLED = 0x0083

SETTINGS_REVERT = 0x03F0
SETTINGS_APPLY = 0x03F1
SETTINGS_STORE = 0x03F2

HOSTNAME_REGISTER_COUNT = CONFIG_HOSTNAME_END - CONFIG_HOSTNAME_START + 1
TIMEOUT_MIN_VALUE = 0
TIMEOUT_MAX_VALUE = 60000
TIMEOUT_DEFAULT_VALUE = 500
HOSTNAME_MAX_LENGTH = HOSTNAME_REGISTER_COUNT * 2
HOSTNAME_ALLOWED_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,30}[A-Za-z0-9])?$")

GATEWAY_MODBUS_CONFIG_BLOCKS: tuple[tuple[int, int], ...] = (
    (CONFIG_MODBUS_BAUDRATE, CONFIG_MODBUS_DEVICEID - CONFIG_MODBUS_BAUDRATE + 1),
    (CONFIG_IP_HIGH, CONFIG_NTP_SUPPORT_ENABLED - CONFIG_IP_HIGH + 1),
)

MODBUS_PORT_OPTIONS_BY_VALUE = {
    0: "AUTO",
    1: "RS232",
    2: "RS485",
}

# Mirror the legacy tool's exposed baudrates. The older Python constants also
# mention 300 and 600 baud values, but the UI intentionally omitted them.
BAUDRATE_OPTIONS_BY_VALUE = {
    3: "1200",
    4: "2400",
    5: "4800",
    6: "9600",
    7: "19200",
    8: "38400",
    9: "57600",
    10: "115200",
}

PARITY_OPTIONS_BY_VALUE = {
    1: "EVEN",
    2: "NONE",
    3: "ODD",
}


@dataclass(frozen=True, slots=True)
class GatewayConfiguration:
    """Decoded TCP gateway configuration state."""

    dhcp_enabled: bool | None = None
    ip_address: str | None = None
    netmask: str | None = None
    default_gateway: str | None = None
    dns_server_1: str | None = None
    dns_server_2: str | None = None
    ntp_enabled: bool | None = None
    ntp_server_1: str | None = None
    ntp_server_2: str | None = None
    host_name: str | None = None
    modbus_port: str | None = None
    baudrate: str | None = None
    parity: str | None = None
    timeout_ms: int | None = None

    def as_readings(self) -> dict[str, GatewayReadingValue]:
        """Expose the decoded values using stable reading keys."""
        readings: dict[str, GatewayReadingValue] = {}
        if self.dhcp_enabled is not None:
            readings["tcp_gateway_dhcp_enabled"] = self.dhcp_enabled
        if self.ip_address is not None:
            readings["tcp_gateway_ip_address"] = self.ip_address
        if self.netmask is not None:
            readings["tcp_gateway_netmask"] = self.netmask
        if self.default_gateway is not None:
            readings["tcp_gateway_default_gateway"] = self.default_gateway
        if self.dns_server_1 is not None:
            readings["tcp_gateway_dns_server_1"] = self.dns_server_1
        if self.dns_server_2 is not None:
            readings["tcp_gateway_dns_server_2"] = self.dns_server_2
        if self.ntp_enabled is not None:
            readings["tcp_gateway_ntp_enabled"] = self.ntp_enabled
        if self.ntp_server_1 is not None:
            readings["tcp_gateway_ntp_server_1"] = self.ntp_server_1
        if self.ntp_server_2 is not None:
            readings["tcp_gateway_ntp_server_2"] = self.ntp_server_2
        if self.host_name is not None:
            readings["tcp_gateway_host_name"] = self.host_name
        if self.modbus_port is not None:
            readings["tcp_gateway_modbus_port"] = self.modbus_port
        if self.baudrate is not None:
            readings["tcp_gateway_baudrate"] = self.baudrate
        if self.parity is not None:
            readings["tcp_gateway_parity"] = self.parity
        if self.timeout_ms is not None:
            readings["tcp_gateway_timeout_ms"] = self.timeout_ms
        return readings


def decode_gateway_configuration_registers(
    *,
    modbus_registers: Sequence[int],
    network_registers: Sequence[int],
) -> GatewayConfiguration:
    """Decode the confirmed gateway configuration blocks from raw registers."""
    return GatewayConfiguration(
        dhcp_enabled=_decode_bool(_network_value(network_registers, CONFIG_DHCP_ENABLED)),
        ip_address=_decode_ipv4_text(
            _network_value(network_registers, CONFIG_IP_HIGH),
            _network_value(network_registers, CONFIG_IP_LOW),
        ),
        netmask=_decode_ipv4_text(
            _network_value(network_registers, CONFIG_NETMASK_HIGH),
            _network_value(network_registers, CONFIG_NETMASK_LOW),
        ),
        default_gateway=_decode_ipv4_text(
            _network_value(network_registers, CONFIG_GATEWAY_HIGH),
            _network_value(network_registers, CONFIG_GATEWAY_LOW),
        ),
        dns_server_1=_decode_ipv4_text(
            _network_value(network_registers, CONFIG_DNS_SERVER_HIGH),
            _network_value(network_registers, CONFIG_DNS_SERVER_LOW),
        ),
        dns_server_2=_decode_ipv4_text(
            _network_value(network_registers, CONFIG_SECONDARY_DNS_SERVER_HIGH),
            _network_value(network_registers, CONFIG_SECONDARY_DNS_SERVER_LOW),
        ),
        ntp_enabled=_decode_bool(
            _network_value(network_registers, CONFIG_NTP_SUPPORT_ENABLED)
        ),
        ntp_server_1=_decode_ipv4_text(
            _network_value(network_registers, CONFIG_NTP_SERVER_HIGH),
            _network_value(network_registers, CONFIG_NTP_SERVER_LOW),
        ),
        ntp_server_2=_decode_ipv4_text(
            _network_value(network_registers, CONFIG_SECONDARY_NTP_SERVER_HIGH),
            _network_value(network_registers, CONFIG_SECONDARY_NTP_SERVER_LOW),
        ),
        host_name=_decode_hostname(network_registers),
        modbus_port=MODBUS_PORT_OPTIONS_BY_VALUE.get(
            _block_value(modbus_registers, CONFIG_MODBUS_UART_DEVICE)
        ),
        baudrate=BAUDRATE_OPTIONS_BY_VALUE.get(
            _block_value(modbus_registers, CONFIG_MODBUS_BAUDRATE)
        ),
        parity=PARITY_OPTIONS_BY_VALUE.get(
            _block_value(modbus_registers, CONFIG_MODBUS_PARITY)
        ),
        timeout_ms=_block_value(modbus_registers, CONFIG_MODBUS_TIMEOUT),
    )


@dataclass(frozen=True, slots=True)
class GatewaySettingDescription:
    """Canonical metadata and write semantics for one gateway setting."""

    key: str
    name: str
    entity_platform: GatewayEntityPlatform
    read_key: str
    register_address: int | None = None
    native_min_value: float | None = None
    native_max_value: float | None = None
    native_step: float | None = None
    native_unit_of_measurement: str | None = None
    options_by_value: Mapping[int, str] | None = None
    number_mode: str | None = None
    text_normalizer: Callable[[str], str] | None = None
    write_builder: Callable[[bool | float | str], tuple[RegisterWrite, ...]] | None = None

    def value_by_option(self) -> dict[str, int]:
        """Return the reverse option lookup for select entities."""
        if self.options_by_value is None:
            raise ValueError(f"Gateway setting {self.key!r} does not define options")
        return {label: value for value, label in self.options_by_value.items()}

    def normalize_value(self, value: bool | float | str) -> bool | float | str:
        """Validate and normalize one gateway setting value before writing."""
        if self.entity_platform == "switch":
            return bool(value)

        if self.entity_platform == "select":
            if not isinstance(value, str):
                raise ValueError(f"Unsupported option for {self.key}: {value!r}")
            if value not in self.value_by_option():
                raise ValueError(f"Unsupported option for {self.key}: {value}")
            return value

        if self.entity_platform == "number":
            try:
                numeric_value = float(value)
            except (TypeError, ValueError) as err:
                raise ValueError(f"Unsupported value for {self.key}: {value!r}") from err
            if (
                self.native_min_value is not None
                and numeric_value < self.native_min_value
            ) or (
                self.native_max_value is not None
                and numeric_value > self.native_max_value
            ):
                raise ValueError(
                    f"{self.key} must stay between "
                    f"{self.native_min_value} and {self.native_max_value}"
                )
            return float(int(round(numeric_value)))

        if self.entity_platform == "text":
            if not isinstance(value, str):
                raise ValueError(f"Unsupported value for {self.key}: {value!r}")
            normalized = value.strip()
            if self.text_normalizer is not None:
                return self.text_normalizer(normalized)
            return normalized

        raise ValueError(f"Unsupported entity platform {self.entity_platform!r}")

    def decode_value(
        self,
        readings: Mapping[str, GatewayReadingValue],
    ) -> GatewaySettingValue:
        """Decode the current logical setting state from decoded gateway readings."""
        value = readings.get(self.read_key)
        if value is None:
            return None

        if self.entity_platform == "switch":
            if isinstance(value, str):
                return value.strip().lower() in {"enabled", "on", "true", "1"}
            return bool(value)

        if self.entity_platform == "select":
            if isinstance(value, str):
                return value
            if self.options_by_value is None:
                return None
            return self.options_by_value.get(int(value))

        if self.entity_platform == "number":
            return float(value)

        if self.entity_platform == "text":
            return str(value)

        raise ValueError(f"Unsupported entity platform {self.entity_platform!r}")

    def build_writes(self, value: bool | float | str) -> tuple[RegisterWrite, ...]:
        """Build the register write plan for one logical gateway setting update."""
        normalized_value = self.normalize_value(value)
        if self.write_builder is not None:
            return self.write_builder(normalized_value)
        if self.register_address is None:
            raise ValueError(f"Gateway setting {self.key!r} does not define a register")

        if self.entity_platform == "switch":
            register_value = 1 if bool(normalized_value) else 0
        elif self.entity_platform == "select":
            register_value = self.value_by_option()[str(normalized_value)]
        elif self.entity_platform == "number":
            register_value = int(float(normalized_value))
        else:
            raise ValueError(f"Unsupported entity platform {self.entity_platform!r}")

        return (
            RegisterWrite(
                address=self.register_address,
                values=(register_value,),
                multiple=False,
            ),
        )


@dataclass(frozen=True, slots=True)
class GatewaySettingState:
    """Current logical state for one supported gateway setting."""

    description: GatewaySettingDescription
    value: GatewaySettingValue


@dataclass(frozen=True, slots=True)
class GatewayActionDescription:
    """One confirmed explicit gateway configuration action."""

    key: str
    name: str
    writes: tuple[RegisterWrite, ...]

    def build_writes(self) -> tuple[RegisterWrite, ...]:
        """Return the ordered action write plan."""
        return self.writes


def build_gateway_setting_states(
    readings: Mapping[str, GatewayReadingValue],
) -> dict[str, GatewaySettingState]:
    """Build the current logical setting-state map for the TCP gateway."""
    return {
        setting.key: GatewaySettingState(
            description=setting,
            value=setting.decode_value(readings),
        )
        for setting in GATEWAY_SETTINGS
    }


def get_gateway_settings(
    *,
    entity_platform: GatewayEntityPlatform | None = None,
) -> tuple[GatewaySettingDescription, ...]:
    """Return the confirmed gateway settings supported by the shared library."""
    return tuple(
        setting
        for setting in GATEWAY_SETTINGS
        if entity_platform is None or setting.entity_platform == entity_platform
    )


def get_gateway_setting(key: str) -> GatewaySettingDescription:
    """Return one gateway setting definition by its stable key."""
    for setting in GATEWAY_SETTINGS:
        if setting.key == key:
            return setting
    raise KeyError(f"Unknown gateway setting {key!r}")


def get_gateway_actions() -> tuple[GatewayActionDescription, ...]:
    """Return the confirmed explicit gateway configuration actions."""
    return GATEWAY_ACTIONS


def get_gateway_action(key: str) -> GatewayActionDescription:
    """Return one gateway action definition by its stable key."""
    for action in GATEWAY_ACTIONS:
        if action.key == key:
            return action
    raise KeyError(f"Unknown gateway action {key!r}")


def supports_gateway_management(transport: TransportType) -> bool:
    """Return whether one transport reaches the TCP gateway management plane."""
    return transport is TransportType.TCP_GATEWAY


def _bool_setting(
    *,
    key: str,
    name: str,
    read_key: str,
    register_address: int,
) -> GatewaySettingDescription:
    return GatewaySettingDescription(
        key=key,
        name=name,
        entity_platform="switch",
        read_key=read_key,
        register_address=register_address,
    )


def _select_setting(
    *,
    key: str,
    name: str,
    read_key: str,
    register_address: int,
    options_by_value: Mapping[int, str],
) -> GatewaySettingDescription:
    return GatewaySettingDescription(
        key=key,
        name=name,
        entity_platform="select",
        read_key=read_key,
        register_address=register_address,
        options_by_value=options_by_value,
    )


def _number_setting(
    *,
    key: str,
    name: str,
    read_key: str,
    register_address: int,
    native_min_value: float,
    native_max_value: float,
    native_step: float,
    native_unit_of_measurement: str | None = None,
    number_mode: str | None = None,
) -> GatewaySettingDescription:
    return GatewaySettingDescription(
        key=key,
        name=name,
        entity_platform="number",
        read_key=read_key,
        register_address=register_address,
        native_min_value=native_min_value,
        native_max_value=native_max_value,
        native_step=native_step,
        native_unit_of_measurement=native_unit_of_measurement,
        number_mode=number_mode,
    )


def _ipv4_setting(
    *,
    key: str,
    name: str,
    read_key: str,
    high_address: int,
    field_name: str,
) -> GatewaySettingDescription:
    return GatewaySettingDescription(
        key=key,
        name=name,
        entity_platform="text",
        read_key=read_key,
        text_normalizer=lambda value: _normalize_ipv4_text(value, field_name=field_name),
        write_builder=lambda value: (
            RegisterWrite(
                address=high_address,
                values=_encode_ipv4_registers(str(value), field_name=field_name),
            ),
        ),
    )


def _normalize_host_name(value: str) -> str:
    """Validate the hostname field using confirmed and conservative rules.

    The fixed-width ASCII register block is confirmed. The vendor docs we have
    do not clearly spell out the allowed hostname characters, so keep writes
    conservative and accept only a single DNS-style label made of ASCII
    letters, digits, and hyphens.
    """
    try:
        value.encode("ascii")
    except UnicodeEncodeError as err:
        raise ValueError("Host name must contain ASCII characters only") from err

    if not value:
        raise ValueError("Host name must not be empty")

    if len(value) > HOSTNAME_MAX_LENGTH:
        raise ValueError(
            f"Host name must be {HOSTNAME_MAX_LENGTH} ASCII characters or fewer"
        )

    if not HOSTNAME_ALLOWED_PATTERN.fullmatch(value):
        raise ValueError(
            "Host name may only contain ASCII letters, numbers, or hyphens"
        )
    return value


def _hostname_setting() -> GatewaySettingDescription:
    return GatewaySettingDescription(
        key="host_name",
        name="Host Name",
        entity_platform="text",
        read_key="tcp_gateway_host_name",
        text_normalizer=_normalize_host_name,
        write_builder=lambda value: (
            RegisterWrite(
                address=CONFIG_HOSTNAME_START,
                values=encode_ascii_registers(
                    str(value),
                    register_count=HOSTNAME_REGISTER_COUNT,
                    field_name="Host name",
                ),
            ),
        ),
    )


DHCP_ENABLED_SETTING = _bool_setting(
    key="dhcp_enabled",
    name="DHCP",
    read_key="tcp_gateway_dhcp_enabled",
    register_address=CONFIG_DHCP_ENABLED,
)

IP_ADDRESS_SETTING = _ipv4_setting(
    key="ip_address",
    name="IP Address",
    read_key="tcp_gateway_ip_address",
    high_address=CONFIG_IP_HIGH,
    field_name="IP address",
)

NETMASK_SETTING = _ipv4_setting(
    key="netmask",
    name="Netmask",
    read_key="tcp_gateway_netmask",
    high_address=CONFIG_NETMASK_HIGH,
    field_name="Netmask",
)

DEFAULT_GATEWAY_SETTING = _ipv4_setting(
    key="default_gateway",
    name="Default Gateway",
    read_key="tcp_gateway_default_gateway",
    high_address=CONFIG_GATEWAY_HIGH,
    field_name="Default gateway",
)

DNS_SERVER_1_SETTING = _ipv4_setting(
    key="dns_server_1",
    name="DNS Server 1",
    read_key="tcp_gateway_dns_server_1",
    high_address=CONFIG_DNS_SERVER_HIGH,
    field_name="DNS server 1",
)

DNS_SERVER_2_SETTING = _ipv4_setting(
    key="dns_server_2",
    name="DNS Server 2",
    read_key="tcp_gateway_dns_server_2",
    high_address=CONFIG_SECONDARY_DNS_SERVER_HIGH,
    field_name="DNS server 2",
)

NTP_ENABLED_SETTING = _bool_setting(
    key="ntp_enabled",
    name="NTP Enable",
    read_key="tcp_gateway_ntp_enabled",
    register_address=CONFIG_NTP_SUPPORT_ENABLED,
)

NTP_SERVER_1_SETTING = _ipv4_setting(
    key="ntp_server_1",
    name="NTP Server 1",
    read_key="tcp_gateway_ntp_server_1",
    high_address=CONFIG_NTP_SERVER_HIGH,
    field_name="NTP server 1",
)

NTP_SERVER_2_SETTING = _ipv4_setting(
    key="ntp_server_2",
    name="NTP Server 2",
    read_key="tcp_gateway_ntp_server_2",
    high_address=CONFIG_SECONDARY_NTP_SERVER_HIGH,
    field_name="NTP server 2",
)

HOST_NAME_SETTING = _hostname_setting()

MODBUS_PORT_SETTING = _select_setting(
    key="modbus_port",
    name="Modbus Port",
    read_key="tcp_gateway_modbus_port",
    register_address=CONFIG_MODBUS_UART_DEVICE,
    options_by_value=MODBUS_PORT_OPTIONS_BY_VALUE,
)

BAUDRATE_SETTING = _select_setting(
    key="baudrate",
    name="Baudrate",
    read_key="tcp_gateway_baudrate",
    register_address=CONFIG_MODBUS_BAUDRATE,
    options_by_value=BAUDRATE_OPTIONS_BY_VALUE,
)

PARITY_SETTING = _select_setting(
    key="parity",
    name="Parity",
    read_key="tcp_gateway_parity",
    register_address=CONFIG_MODBUS_PARITY,
    options_by_value=PARITY_OPTIONS_BY_VALUE,
)

TIMEOUT_SETTING = _number_setting(
    key="timeout_ms",
    name="Timeout",
    read_key="tcp_gateway_timeout_ms",
    register_address=CONFIG_MODBUS_TIMEOUT,
    native_min_value=TIMEOUT_MIN_VALUE,
    native_max_value=TIMEOUT_MAX_VALUE,
    native_step=1,
    native_unit_of_measurement="ms",
    number_mode="box",
)

# The legacy vendor configurator also mentions a frame-delay control, but this
# integration intentionally omits it until the register and semantics are
# confirmed against current gateway firmware.
GATEWAY_SETTINGS: tuple[GatewaySettingDescription, ...] = (
    DHCP_ENABLED_SETTING,
    IP_ADDRESS_SETTING,
    NETMASK_SETTING,
    DEFAULT_GATEWAY_SETTING,
    DNS_SERVER_1_SETTING,
    DNS_SERVER_2_SETTING,
    NTP_ENABLED_SETTING,
    NTP_SERVER_1_SETTING,
    NTP_SERVER_2_SETTING,
    HOST_NAME_SETTING,
    MODBUS_PORT_SETTING,
    BAUDRATE_SETTING,
    PARITY_SETTING,
    TIMEOUT_SETTING,
)

GATEWAY_REVERT_ACTION = GatewayActionDescription(
    key="revert",
    name="Revert",
    writes=(
        RegisterWrite(address=SETTINGS_REVERT, values=(1,), multiple=False),
    ),
)

GATEWAY_APPLY_ACTION = GatewayActionDescription(
    key="apply",
    name="Apply",
    writes=(
        RegisterWrite(address=SETTINGS_APPLY, values=(1,), multiple=False),
    ),
)

GATEWAY_APPLY_AND_STORE_ACTION = GatewayActionDescription(
    key="apply_and_store",
    name="Apply and Store",
    writes=(
        RegisterWrite(address=SETTINGS_STORE, values=(1,), multiple=False),
        RegisterWrite(address=SETTINGS_APPLY, values=(1,), multiple=False),
    ),
)

GATEWAY_ACTIONS: tuple[GatewayActionDescription, ...] = (
    GATEWAY_REVERT_ACTION,
    GATEWAY_APPLY_ACTION,
    GATEWAY_APPLY_AND_STORE_ACTION,
)


def _block_value(registers: Sequence[int], address: int) -> int | None:
    """Return one register from the low-address Modbus config block."""
    offset = address - CONFIG_MODBUS_BAUDRATE
    if offset < 0 or offset >= len(registers):
        return None
    return int(registers[offset]) & 0xFFFF


def _network_value(registers: Sequence[int], address: int) -> int | None:
    """Return one register from the gateway network config block."""
    offset = address - CONFIG_IP_HIGH
    if offset < 0 or offset >= len(registers):
        return None
    return int(registers[offset]) & 0xFFFF


def _decode_bool(value: int | None) -> bool | None:
    """Decode one Modbus boolean register into a Python bool."""
    if value is None:
        return None
    return bool(int(value))


def _decode_ipv4_text(high_word: int | None, low_word: int | None) -> str | None:
    """Decode one IPv4 pair the same way as the legacy gateway tool."""
    if high_word is None or low_word is None:
        return None
    address = ((int(high_word) & 0xFFFF) << 16) | (int(low_word) & 0xFFFF)
    return str(ipaddress.IPv4Address(address))


def _encode_ipv4_registers(value: str, *, field_name: str) -> tuple[int, int]:
    """Encode one IPv4 address into the confirmed high/low register pair."""
    normalized = _normalize_ipv4_text(value, field_name=field_name)
    address = int(ipaddress.IPv4Address(normalized))
    return ((address >> 16) & 0xFFFF, address & 0xFFFF)


def _normalize_ipv4_text(value: str, *, field_name: str) -> str:
    """Validate and normalize one IPv4 text field."""
    try:
        return str(ipaddress.IPv4Address(value))
    except ipaddress.AddressValueError as err:
        raise ValueError(f"{field_name} must be a valid IPv4 address") from err


def _decode_hostname(registers: Sequence[int]) -> str | None:
    """Decode the fixed-length hostname block into stripped ASCII text."""
    start = CONFIG_HOSTNAME_START - CONFIG_IP_HIGH
    end = CONFIG_HOSTNAME_END - CONFIG_IP_HIGH + 1
    if start < 0 or end > len(registers):
        return None

    raw = bytearray()
    for word in registers[start:end]:
        raw.extend(((int(word) >> 8) & 0xFF, int(word) & 0xFF))

    text = raw.decode("ascii", errors="ignore").replace("\x00", "").strip()
    return text or ""

