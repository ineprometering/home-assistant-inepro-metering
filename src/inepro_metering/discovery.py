"""Discovery and identity helpers for Inepro Metering devices."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import ipaddress
import json
import logging
from pathlib import Path
import re
import select
import socket
import time
from typing import Any

from .const import (
    DEFAULT_BLUETOOTH_PROXY_HOST,
    DEFAULT_BLUETOOTH_PROXY_PORT,
    MeterFamily,
    TransportType,
)
from .modbus import (
    CONF_BAUDRATE,
    CONF_BYTESIZE,
    CONF_HOST,
    CONF_PARITY,
    CONF_PORT,
    CONF_SERIAL_PORT,
    CONF_STOPBITS,
    CONF_TIMEOUT,
    CONF_TRANSPORT,
    DEFAULT_PORT,
    IneproMeteringError,
    IneproModbusClient,
)
from .models import RegisterType, get_profile
from .runtime import MeterIdentity

CONF_SLAVE_ID_END = "slave_id_end"
CONF_SLAVE_ID_START = "slave_id_start"

_LOGGER = logging.getLogger(__name__)

GROW_SERIAL_PATTERN = re.compile(
    r"^(?P<product_code>(?:07|08)\d{2})(?P<year>\d{2})(?P<week>\d{2})(?P<sequence>\d{4})$"
)
GROW_BLUETOOTH_NAME_PATTERN = re.compile(r"^IM-(?P<serial>\d{12})$")

SERIAL_NUMBER_TAIL_ADDRESS = 0x4000
SERIAL_NUMBER_TAIL_COUNT = 2
METER_CODE_ADDRESS = 0x4002
PRO_METER_AMPS_ADDRESS = 0x400B
# Use the live product-code register when reconstructing a full GROW serial.
# The meter-code register can differ, while 0x4025 matches the serial prefix
# used throughout config entries and discovery results.
PRODUCT_CODE_ADDRESS = 0x4025

GROW_PRODUCT_PREFIX_TO_VARIANT = {
    "070": "grow_701",
    "075": "grow_750",
    "080": "grow_800",
    "085": "grow_850",
}

TCP_GATEWAY_DISCOVERY_BROADCAST_ADDRESS = "255.255.255.255"
TCP_GATEWAY_DISCOVERY_BROADCAST_PORT = 20000
TCP_GATEWAY_DISCOVERY_LISTEN_PORT = 20001
TCP_GATEWAY_DISCOVERY_REQUESTS = (b"\xff" * 6, b"\xff" * 7)
TCP_GATEWAY_DISCOVERY_TIMEOUT = 1.0
TCP_GATEWAY_TCP_DISCOVERY_CONCURRENCY = 64
TCP_GATEWAY_TCP_DISCOVERY_MAX_HOSTS = 512


@dataclass(frozen=True, slots=True)
class ProMeterIdentityRule:
    """Discovery rule for PRO-family meter-code identities."""

    variant: str
    forced_serial_prefix: int | None = None
    fallback_serial_prefix: int | None = None


PRO_METER_CODE_TO_VARIANT = {
    0x0102: ProMeterIdentityRule("pro_380", forced_serial_prefix=0x0257),
    0x0103: ProMeterIdentityRule("pro_380ct", forced_serial_prefix=0x0260),
    0x2007: ProMeterIdentityRule("pro_380_solare", fallback_serial_prefix=0x0257),
    0x2008: ProMeterIdentityRule("pro_380ct_solare", fallback_serial_prefix=0x0260),
    0x2009: ProMeterIdentityRule("pro_1_solare", fallback_serial_prefix=0x0254),
    0x2010: ProMeterIdentityRule("pro_2_solare", fallback_serial_prefix=0x0287),
    0x3201: ProMeterIdentityRule("n_1"),
}


@dataclass(frozen=True, slots=True)
class GrowSerialNumber:
    """Parsed GROW serial number details."""

    serial_number: str
    product_code: str
    production_year_code: int
    production_year: int
    production_week: int
    sequence: int


@dataclass(frozen=True, slots=True)
class DiscoveredGrowMeter:
    """A discovered meter found during a serial bus scan."""

    serial_number: str
    slave_id: int
    variant: str
    model_title: str
    product_code: str
    family: MeterFamily = MeterFamily.GROW
    meter_code: str | None = None

    @property
    def display_name(self) -> str:
        """Return a user-facing summary for selectors."""
        details = f"slave {self.slave_id} · {self.model_title}"
        if self.product_code != self.meter_code and self.meter_code is not None:
            details = f"{details} · code {self.product_code}"
        return f"{self.serial_number} ({details})"


@dataclass(frozen=True, slots=True)
class DiscoveredGrowBluetoothMeter:
    """A GROW meter discovered from Bluetooth or a Bluetooth proxy scan."""

    address: str
    bluetooth_name: str
    serial_number: str
    variant: str
    model_title: str
    product_code: str
    rssi: int | None = None
    transport: TransportType = TransportType.BLUETOOTH
    proxy_host: str | None = None
    proxy_port: int | None = None

    @property
    def display_name(self) -> str:
        """Return a user-facing summary for selectors."""
        details = f"{self.model_title} · {self.bluetooth_name}"
        if self.rssi is not None:
            details = f"{details} · {self.rssi} dBm"
        if self.transport is TransportType.BLUETOOTH_PROXY:
            details = f"{details} · Windows proxy"
        return f"{self.serial_number} ({details})"


@dataclass(frozen=True, slots=True)
class DiscoveredTcpGateway:
    """A discovered TCP gateway found through the UDP browse protocol."""

    host: str
    port: int = DEFAULT_PORT
    mac_address: str | None = None
    serial_number: str | None = None

    @property
    def display_name(self) -> str:
        """Return a user-facing summary for selectors."""
        details = [
            value
            for value in (self.serial_number, self.mac_address)
            if value
        ]
        if not details:
            return f"{self.host}:{self.port} (verified)"
        return f"{self.host}:{self.port} ({' · '.join(details)} · verified)"


def parse_grow_serial_number(serial_number: str) -> GrowSerialNumber | None:
    """Parse a GROW serial number if it matches the known format."""
    normalized = serial_number.strip()
    match = GROW_SERIAL_PATTERN.fullmatch(normalized)
    if match is None:
        return None

    year_code = int(match.group("year"))
    week = int(match.group("week"))
    if week < 1 or week > 53:
        return None

    return GrowSerialNumber(
        serial_number=normalized,
        product_code=match.group("product_code"),
        production_year_code=year_code,
        production_year=2000 + year_code,
        production_week=week,
        sequence=int(match.group("sequence")),
    )


def parse_grow_bluetooth_name(name: str) -> GrowSerialNumber | None:
    """Parse a GROW Bluetooth local name like IM-070125100001."""
    normalized = name.strip()
    match = GROW_BLUETOOTH_NAME_PATTERN.fullmatch(normalized)
    if match is None:
        return None
    return parse_grow_serial_number(match.group("serial"))


def build_grow_serial_number(
    product_code: str | None,
    serial_number_tail: str | None,
) -> str | None:
    """Build a full GROW serial from product code and the 0x4000 serial tail."""
    if product_code is None or serial_number_tail is None:
        return None

    normalized_product_code = product_code.strip().upper()
    normalized_tail = serial_number_tail.strip().upper()
    if (
        len(normalized_product_code) != 4
        or len(normalized_tail) != 8
        or not normalized_product_code.isdigit()
        or not normalized_tail.isdigit()
    ):
        return None

    serial_number = f"{normalized_product_code}{normalized_tail}"
    if parse_grow_serial_number(serial_number) is None:
        return None
    return serial_number


async def async_discover_tcp_gateways(
    *,
    timeout: float = TCP_GATEWAY_DISCOVERY_TIMEOUT,
    scan_target: str | None = None,
) -> tuple[DiscoveredTcpGateway, ...]:
    """Discover TCP gateways via UDP browse plus optional TCP probing."""
    normalized_scan_target = (
        None if scan_target is None else scan_target.strip() or None
    )
    _LOGGER.debug(
        "Gateway discovery scan started; target=%s",
        normalized_scan_target or "local-network",
    )

    if normalized_scan_target is None:
        discovered_gateways = await asyncio.to_thread(
            _discover_tcp_gateways,
            timeout=timeout,
        )
        if discovered_gateways:
            _LOGGER.debug(
                "Gateway discovery scan completed via UDP browse; verified=%s",
                len(discovered_gateways),
            )
            return discovered_gateways
        probe_hosts = _discover_local_probe_hosts()
    else:
        probe_hosts = _expand_tcp_gateway_scan_target(normalized_scan_target)

    if not probe_hosts:
        _LOGGER.debug("Gateway discovery scan completed; no candidate hosts")
        return ()

    discovered = await _async_probe_tcp_gateway_hosts(
        probe_hosts,
        timeout=timeout,
    )
    _LOGGER.debug(
        "Gateway discovery scan completed; verified=%s",
        len(discovered),
    )
    return discovered


async def async_read_grow_identity(
    client: IneproModbusClient,
    *,
    slave_id: int,
    product_code: str | None = None,
) -> MeterIdentity:
    """Read the current GROW identity values from one configured route."""
    serial_registers = await client.async_read_registers(
        register_type=RegisterType.HOLDING,
        address=SERIAL_NUMBER_TAIL_ADDRESS,
        count=SERIAL_NUMBER_TAIL_COUNT,
        slave_id=slave_id,
    )
    serial_number_tail = "".join(f"{register:04X}" for register in serial_registers)
    resolved_product_code = product_code or await _read_hex16(
        client,
        PRODUCT_CODE_ADDRESS,
        slave_id,
    )
    return MeterIdentity(
        serial_number=build_grow_serial_number(resolved_product_code, serial_number_tail),
        product_code=resolved_product_code,
    )


async def async_read_grow_serial_number(
    client: IneproModbusClient,
    *,
    slave_id: int,
    product_code: str | None = None,
) -> str | None:
    """Read the full live GROW serial number from one configured route."""
    identity = await async_read_grow_identity(
        client,
        slave_id=slave_id,
        product_code=product_code,
    )
    return identity.device_serial


def infer_grow_variant(
    serial_number: str | None,
    product_code: str | None = None,
) -> str | None:
    """Infer the current GROW profile variant from product-code identity values."""
    for candidate in (product_code, serial_number):
        if candidate is None:
            continue
        normalized = candidate.strip()
        if len(normalized) < 3:
            continue
        variant = GROW_PRODUCT_PREFIX_TO_VARIANT.get(normalized[:3])
        if variant is not None:
            return variant
    return None


async def async_discover_grow_bluetooth_proxy_meters(
    *,
    host: str = DEFAULT_BLUETOOTH_PROXY_HOST,
    port: int = DEFAULT_BLUETOOTH_PROXY_PORT,
    timeout: float = 10.0,
) -> tuple[DiscoveredGrowBluetoothMeter, ...]:
    """Return GROW meters discovered through the Windows BLE proxy."""
    for candidate_host in _candidate_ble_proxy_hosts(host):
        response = await _async_request_ble_proxy_scan(
            host=candidate_host,
            port=port,
            timeout=timeout,
        )
        if response is None:
            continue

        devices = response.get("devices")
        if not isinstance(devices, list):
            continue

        discovered: dict[str, DiscoveredGrowBluetoothMeter] = {}
        for device in devices:
            meter = _grow_bluetooth_meter_from_proxy_payload(
                device,
                host=candidate_host,
                port=port,
            )
            if meter is None:
                continue
            previous = discovered.get(meter.serial_number)
            if previous is None or _rssi_value(meter.rssi) > _rssi_value(previous.rssi):
                discovered[meter.serial_number] = meter

        if discovered:
            return tuple(sorted(discovered.values(), key=lambda meter: meter.serial_number))

    return ()


async def async_discover_grow_serial_bus(
    config: dict[str, Any],
    *,
    slave_id_start: int = 1,
    slave_id_end: int = 32,
) -> tuple[DiscoveredGrowMeter, ...]:
    """Scan a serial Modbus bus for supported meters."""
    scan_config = {
        CONF_TRANSPORT: TransportType.SERIAL.value,
        CONF_SERIAL_PORT: config[CONF_SERIAL_PORT],
        CONF_BAUDRATE: config[CONF_BAUDRATE],
        CONF_BYTESIZE: config[CONF_BYTESIZE],
        CONF_PARITY: config[CONF_PARITY],
        CONF_STOPBITS: config[CONF_STOPBITS],
        CONF_TIMEOUT: config[CONF_TIMEOUT],
    }
    return await _async_discover_grow_bus(
        scan_config,
        slave_id_start=slave_id_start,
        slave_id_end=slave_id_end,
    )


async def async_discover_grow_tcp_gateway(
    config: dict[str, Any],
    *,
    slave_id_start: int = 1,
    slave_id_end: int = 32,
) -> tuple[DiscoveredGrowMeter, ...]:
    """Scan a Modbus TCP gateway for downstream supported meters."""
    scan_config = {
        CONF_TRANSPORT: TransportType.TCP_GATEWAY.value,
        CONF_HOST: config[CONF_HOST],
        CONF_PORT: config[CONF_PORT],
        CONF_TIMEOUT: config[CONF_TIMEOUT],
    }
    return await _async_discover_grow_bus(
        scan_config,
        slave_id_start=slave_id_start,
        slave_id_end=slave_id_end,
    )


async def _async_discover_grow_bus(
    scan_config: dict[str, Any],
    *,
    slave_id_start: int,
    slave_id_end: int,
) -> tuple[DiscoveredGrowMeter, ...]:
    """Scan one shared Modbus route for supported meters."""
    client = IneproModbusClient(scan_config)
    found: list[DiscoveredGrowMeter] = []

    try:
        await client.async_ping()

        for slave_id in range(slave_id_start, slave_id_end + 1):
            discovered_meter = await _async_read_discovered_bus_meter(client, slave_id)
            if discovered_meter is not None:
                found.append(discovered_meter)
    finally:
        await client.async_close()

    return tuple(found)


async def _async_read_discovered_bus_meter(
    client: IneproModbusClient,
    slave_id: int,
) -> DiscoveredGrowMeter | None:
    """Read one supported bus meter identity from the shared register block."""
    try:
        serial_registers = await client.async_read_registers(
            RegisterType.HOLDING,
            SERIAL_NUMBER_TAIL_ADDRESS,
            SERIAL_NUMBER_TAIL_COUNT,
            slave_id,
        )
    except IneproMeteringError:
        return None

    serial_number_tail = "".join(f"{register:04X}" for register in serial_registers)
    meter_code = await _safe_read_hex16(client, METER_CODE_ADDRESS, slave_id)
    product_code = await _safe_read_hex16(client, PRODUCT_CODE_ADDRESS, slave_id)
    resolved_product_code = product_code or meter_code
    serial_number = build_grow_serial_number(
        resolved_product_code,
        serial_number_tail,
    )
    parsed_serial = (
        None if serial_number is None else parse_grow_serial_number(serial_number)
    )
    if parsed_serial is not None:
        inferred_variant = infer_grow_variant(
            parsed_serial.serial_number,
            resolved_product_code,
        )
        if inferred_variant is not None:
            profile = get_profile(MeterFamily.GROW, inferred_variant)
            return DiscoveredGrowMeter(
                serial_number=parsed_serial.serial_number,
                slave_id=slave_id,
                variant=inferred_variant,
                model_title=profile.title,
                product_code=resolved_product_code,
                family=MeterFamily.GROW,
                meter_code=meter_code,
            )

    return await _async_read_discovered_pro_meter(
        client,
        slave_id=slave_id,
        serial_number_tail=serial_number_tail,
        meter_code=meter_code,
        product_code=product_code,
    )


async def _async_read_discovered_pro_meter(
    client: IneproModbusClient,
    *,
    slave_id: int,
    serial_number_tail: str,
    meter_code: str | None,
    product_code: str | None,
) -> DiscoveredGrowMeter | None:
    """Identify a supported PRO meter from its model and serial registers."""
    if meter_code is None:
        return None

    try:
        meter_code_value = int(meter_code, 16)
    except ValueError:
        return None

    if meter_code_value == 0x0101:
        max_amps = await _safe_read_uint16(client, PRO_METER_AMPS_ADDRESS, slave_id)
        if max_amps is None:
            return None
        variant = "pro_2" if max_amps == 100 else "pro_1"
        serial_prefix = 0x0287 if variant == "pro_2" else 0x0254
    elif meter_code_value == 0x3203:
        max_amps = await _safe_read_uint16(client, PRO_METER_AMPS_ADDRESS, slave_id)
        if max_amps is None:
            return None
        variant = "n_380_40a" if max_amps == 40 else "n_380ct"
        serial_prefix = 0x0514 if variant == "n_380_40a" else 0x0516
    else:
        identity_rule = PRO_METER_CODE_TO_VARIANT.get(meter_code_value)
        if identity_rule is None:
            return None
        variant = identity_rule.variant
        serial_prefix = identity_rule.forced_serial_prefix

        if serial_prefix is None and product_code is not None:
            try:
                serial_prefix = int(product_code, 16)
            except ValueError:
                return None

        if serial_prefix is None:
            serial_prefix = identity_rule.fallback_serial_prefix

        if serial_prefix is None:
            return None

    resolved_product_code = product_code
    if resolved_product_code is None:
        resolved_product_code = f"{serial_prefix:04X}"

    profile = get_profile(MeterFamily.PRO, variant)
    return DiscoveredGrowMeter(
        serial_number=f"{serial_prefix:04X}{serial_number_tail}",
        slave_id=slave_id,
        variant=variant,
        model_title=profile.title,
        product_code=resolved_product_code,
        family=MeterFamily.PRO,
        meter_code=meter_code,
    )


async def _async_request_ble_proxy_scan(
    *,
    host: str,
    port: int,
    timeout: float,
) -> dict[str, Any] | None:
    """Request one BLE scan from the Windows proxy endpoint."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout,
        )
    except Exception:
        return None

    try:
        request = {"action": "scan", "timeout": float(timeout)}
        writer.write(json.dumps(request, separators=(",", ":")).encode("utf-8") + b"\n")
        await asyncio.wait_for(writer.drain(), timeout=timeout)
        raw_response = await asyncio.wait_for(reader.readline(), timeout=timeout)
        if not raw_response:
            return None
        response = json.loads(raw_response.decode("utf-8"))
    except Exception:
        return None
    finally:
        writer.close()
        await writer.wait_closed()

    if not isinstance(response, dict) or not response.get("ok", False):
        return None

    return response


def _candidate_ble_proxy_hosts(host: str) -> tuple[str, ...]:
    """Return likely hosts for local Bluetooth proxy installs."""
    candidates: list[str] = []
    normalized = str(host).strip()
    if normalized:
        candidates.append(normalized)

    gateway_host = _read_default_route_gateway_host()
    if gateway_host and gateway_host not in candidates:
        candidates.append(gateway_host)

    resolver_host = _read_resolver_nameserver_host()
    if resolver_host and resolver_host not in candidates:
        candidates.append(resolver_host)

    if DEFAULT_BLUETOOTH_PROXY_HOST not in candidates:
        candidates.append(DEFAULT_BLUETOOTH_PROXY_HOST)

    return tuple(candidates)


def _read_default_route_gateway_host() -> str | None:
    """Read the default-route gateway IP from procfs."""
    try:
        route_table = Path("/proc/net/route")
        if not route_table.exists():
            return None
        for line in route_table.read_text(encoding="utf-8").splitlines()[1:]:
            columns = line.split()
            if len(columns) < 3:
                continue
            destination = columns[1]
            gateway = columns[2]
            if destination != "00000000":
                continue
            gateway_int = int(gateway, 16)
            packed = gateway_int.to_bytes(4, byteorder="little")
            return str(ipaddress.IPv4Address(packed))
    except Exception:
        return None
    return None


def _read_resolver_nameserver_host() -> str | None:
    """Read the resolver nameserver host from resolv.conf."""
    try:
        resolv_conf = Path("/etc/resolv.conf")
        if not resolv_conf.exists():
            return None
        for line in resolv_conf.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line.startswith("nameserver "):
                continue
            host = line.split(None, 1)[1].strip()
            return host or None
    except Exception:
        return None
    return None


def _grow_bluetooth_meter_from_proxy_payload(
    device: Any,
    *,
    host: str,
    port: int,
) -> DiscoveredGrowBluetoothMeter | None:
    """Parse one Windows proxy scan payload into a GROW meter."""
    if not isinstance(device, dict):
        return None

    bluetooth_name = str(device.get("name", "") or "").strip()
    parsed = parse_grow_bluetooth_name(bluetooth_name)
    if parsed is None:
        return None

    variant = infer_grow_variant(parsed.serial_number, parsed.product_code)
    if variant is None:
        return None

    profile = get_profile(MeterFamily.GROW, variant)
    rssi = device.get("rssi")
    return DiscoveredGrowBluetoothMeter(
        address=str(device.get("address", "")).strip(),
        bluetooth_name=bluetooth_name,
        serial_number=parsed.serial_number,
        variant=variant,
        model_title=profile.title,
        product_code=parsed.product_code,
        rssi=None if rssi is None else int(rssi),
        transport=TransportType.BLUETOOTH_PROXY,
        proxy_host=host,
        proxy_port=int(port),
    )


def _rssi_value(rssi: int | None) -> int:
    """Normalize missing RSSI for best-advertisement comparisons."""
    return -999 if rssi is None else int(rssi)


def _discover_tcp_gateways(
    *,
    timeout: float,
) -> tuple[DiscoveredTcpGateway, ...]:
    """Synchronously discover TCP gateways with the vendor UDP browse command."""
    found: dict[str, DiscoveredTcpGateway] = {}
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            udp_socket.bind(("0.0.0.0", TCP_GATEWAY_DISCOVERY_LISTEN_PORT))
        except OSError:
            udp_socket.bind(("0.0.0.0", 0))

        udp_socket.setblocking(False)
        for request in TCP_GATEWAY_DISCOVERY_REQUESTS:
            udp_socket.sendto(
                request,
                (
                    TCP_GATEWAY_DISCOVERY_BROADCAST_ADDRESS,
                    TCP_GATEWAY_DISCOVERY_BROADCAST_PORT,
                ),
            )

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break

            readable, _, _ = select.select([udp_socket], [], [], remaining)
            if not readable:
                break

            message, address = udp_socket.recvfrom(57)
            discovered_gateway = _parse_tcp_gateway_discovery_response(
                message,
                host=address[0],
            )
            if discovered_gateway is None:
                continue
            found[discovered_gateway.host] = discovered_gateway
    except OSError:
        return tuple(sorted(found.values(), key=_tcp_gateway_sort_key))
    finally:
        udp_socket.close()

    return tuple(sorted(found.values(), key=_tcp_gateway_sort_key))


def _parse_tcp_gateway_discovery_response(
    message: bytes,
    *,
    host: str,
) -> DiscoveredTcpGateway | None:
    """Parse one UDP browse response from a TCP gateway."""
    if len(message) < 29:
        return None

    if message[6] == 0xFF:
        serial_bytes = message[20:32]
    else:
        serial_bytes = message[17:29]

    serial_number = _decode_gateway_serial(serial_bytes)
    if _is_grow_meter_serial(serial_number):
        _LOGGER.debug(
            "Gateway UDP browse candidate ignored for %s: serial %s is a GROW meter",
            host,
            serial_number,
        )
        return None

    mac_address = ":".join(f"{byte:02X}" for byte in message[:6])
    return DiscoveredTcpGateway(
        host=host,
        port=DEFAULT_PORT,
        mac_address=mac_address,
        serial_number=serial_number,
    )


def _decode_gateway_serial(serial_bytes: bytes) -> str | None:
    """Decode an ASCII serial number from a browse payload."""
    try:
        decoded = serial_bytes.decode("ascii").strip("\x00 ").strip()
    except UnicodeDecodeError:
        return None
    return decoded or None


def _tcp_gateway_sort_key(discovered_gateway: DiscoveredTcpGateway) -> tuple[int, str]:
    """Sort discovered gateways by IPv4 address when possible."""
    try:
        return (0, f"{int(ipaddress.IPv4Address(discovered_gateway.host)):010d}")
    except ipaddress.AddressValueError:
        return (1, discovered_gateway.host.lower())


def _expand_tcp_gateway_scan_target(scan_target: str) -> tuple[str, ...]:
    """Expand one explicit gateway scan target into concrete IPv4 hosts."""
    normalized_target = scan_target.strip()
    if not normalized_target:
        return ()

    try:
        host = ipaddress.ip_address(normalized_target)
    except ValueError:
        pass
    else:
        if host.version != 4:
            raise ValueError("Only IPv4 gateway scan targets are supported")
        return (str(host),)

    if "-" in normalized_target:
        return _expand_tcp_gateway_host_range(normalized_target)

    try:
        network = ipaddress.ip_network(normalized_target, strict=False)
    except ValueError:
        network = None

    if network is not None:
        if network.version != 4:
            raise ValueError("Only IPv4 gateway scan targets are supported")
        hosts = (
            (str(network.network_address),)
            if network.num_addresses == 1
            else tuple(str(host) for host in network.hosts())
        )
        _validate_tcp_gateway_probe_host_count(len(hosts))
        return hosts

    try:
        resolved_hosts = {
            info[4][0]
            for info in socket.getaddrinfo(
                normalized_target,
                None,
                family=socket.AF_INET,
                type=socket.SOCK_STREAM,
            )
        }
    except OSError as err:
        raise ValueError("Unsupported gateway scan target") from err

    hosts = tuple(
        sorted(
            resolved_hosts,
            key=lambda host: int(ipaddress.IPv4Address(host)),
        )
    )
    _validate_tcp_gateway_probe_host_count(len(hosts))
    return hosts


def _expand_tcp_gateway_host_range(scan_target: str) -> tuple[str, ...]:
    """Expand an explicit inclusive IPv4 host range like 10.5.2.1-10.5.2.20."""
    start_text, end_text = (part.strip() for part in scan_target.split("-", 1))
    try:
        start_address = ipaddress.ip_address(start_text)
        end_address = ipaddress.ip_address(end_text)
    except ValueError as err:
        raise ValueError("Invalid IPv4 host range") from err

    if start_address.version != 4 or end_address.version != 4:
        raise ValueError("Only IPv4 gateway scan targets are supported")
    if int(start_address) > int(end_address):
        raise ValueError("Gateway scan range start must be <= end")

    hosts = tuple(
        str(ipaddress.IPv4Address(address))
        for address in range(int(start_address), int(end_address) + 1)
    )
    _validate_tcp_gateway_probe_host_count(len(hosts))
    return hosts


def _validate_tcp_gateway_probe_host_count(host_count: int) -> None:
    """Reject scan targets that would probe an excessively large host range."""
    if host_count > TCP_GATEWAY_TCP_DISCOVERY_MAX_HOSTS:
        raise ValueError("Gateway scan target is too large")


def _discover_local_probe_hosts() -> tuple[str, ...]:
    """Build a small set of TCP probe hosts from the current local IPv4 interfaces."""
    local_hosts: set[str] = set()
    for address in _discover_local_ipv4_addresses():
        if (
            address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_unspecified
        ):
            continue
        network = ipaddress.ip_network(f"{address}/24", strict=False)
        for host in network.hosts():
            if host == address:
                continue
            local_hosts.add(str(host))

    return tuple(
        sorted(
            local_hosts,
            key=lambda host: int(ipaddress.IPv4Address(host)),
        )
    )


def _discover_local_ipv4_addresses() -> tuple[ipaddress.IPv4Address, ...]:
    """Return IPv4 addresses assigned to the current runtime."""
    addresses: set[ipaddress.IPv4Address] = set()

    try:
        for info in socket.getaddrinfo(
            socket.gethostname(),
            None,
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
        ):
            addresses.add(ipaddress.IPv4Address(info[4][0]))
    except OSError:
        pass

    probe_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe_socket.connect(("8.8.8.8", 80))
        addresses.add(ipaddress.IPv4Address(probe_socket.getsockname()[0]))
    except OSError:
        pass
    finally:
        probe_socket.close()

    return tuple(sorted(addresses, key=int))


async def _async_probe_tcp_gateway_hosts(
    hosts: tuple[str, ...],
    *,
    timeout: float,
) -> tuple[DiscoveredTcpGateway, ...]:
    """Probe candidate hosts over Modbus TCP and keep confirmed gateways only."""
    found: dict[str, DiscoveredTcpGateway] = {}
    semaphore = asyncio.Semaphore(TCP_GATEWAY_TCP_DISCOVERY_CONCURRENCY)

    async def probe(host: str) -> None:
        async with semaphore:
            _LOGGER.debug("Checking gateway candidate host=%s port=%s", host, DEFAULT_PORT)
            discovered_gateway = await _async_probe_tcp_gateway_host(
                host=host,
                timeout=timeout,
            )
        if discovered_gateway is not None:
            found[discovered_gateway.host] = discovered_gateway

    await asyncio.gather(*(probe(host) for host in hosts))
    return tuple(sorted(found.values(), key=_tcp_gateway_sort_key))


async def _async_probe_tcp_gateway_host(
    *,
    host: str,
    timeout: float,
) -> DiscoveredTcpGateway | None:
    """Confirm whether one host exposes the vendor TCP gateway metadata block."""
    client = IneproModbusClient(
        {
            CONF_TRANSPORT: TransportType.TCP_GATEWAY.value,
            CONF_HOST: host,
            CONF_PORT: DEFAULT_PORT,
            CONF_TIMEOUT: max(float(timeout), 0.5),
        }
    )

    try:
        gateway_info = await client.async_read_tcp_gateway_info()
    except Exception as err:
        _LOGGER.debug(
            "Gateway validation failed for %s:%s: %s",
            host,
            DEFAULT_PORT,
            err,
        )
        return None
    finally:
        await client.async_close()

    if gateway_info.device_type != "TCP Gateway":
        _LOGGER.debug(
            "Gateway validation failed for %s:%s: unexpected device_type=%s",
            host,
            DEFAULT_PORT,
            gateway_info.device_type,
        )
        return None
    if _is_grow_meter_serial(gateway_info.serial_number):
        _LOGGER.debug(
            "Gateway validation failed for %s:%s: serial %s is a GROW meter",
            host,
            DEFAULT_PORT,
            gateway_info.serial_number,
        )
        return None
    if (
        gateway_info.serial_number is None
        and gateway_info.firmware_version is None
        and gateway_info.hardware_version is None
    ):
        _LOGGER.debug(
            "Gateway validation failed for %s:%s: missing identity fields",
            host,
            DEFAULT_PORT,
        )
        return None

    _LOGGER.debug(
        "Gateway validation succeeded for %s:%s serial=%s",
        host,
        DEFAULT_PORT,
        gateway_info.serial_number,
    )
    return DiscoveredTcpGateway(
        host=host,
        port=DEFAULT_PORT,
        serial_number=gateway_info.serial_number,
    )


def _is_grow_meter_serial(serial_number: str | None) -> bool:
    """Return whether a serial identifies a directly connected GROW meter."""
    if serial_number is None:
        return False
    return parse_grow_serial_number(serial_number) is not None


async def _safe_read_hex16(
    client: IneproModbusClient,
    address: int,
    slave_id: int,
) -> str | None:
    """Read one HEX16 register, returning None when the read fails."""
    try:
        registers = await client.async_read_registers(
            register_type=RegisterType.HOLDING,
            address=address,
            count=1,
            slave_id=slave_id,
        )
    except IneproMeteringError:
        return None
    return f"{registers[0]:04X}"


async def _safe_read_uint16(
    client: IneproModbusClient,
    address: int,
    slave_id: int,
) -> int | None:
    """Read one unsigned 16-bit register, returning None when the read fails."""
    try:
        registers = await client.async_read_registers(
            register_type=RegisterType.HOLDING,
            address=address,
            count=1,
            slave_id=slave_id,
        )
    except IneproMeteringError:
        return None
    return int(registers[0])


async def _read_hex16(
    client: IneproModbusClient,
    address: int,
    slave_id: int,
) -> str:
    """Read one HEX16 register and propagate transport failures."""
    registers = await client.async_read_registers(
        register_type=RegisterType.HOLDING,
        address=address,
        count=1,
        slave_id=slave_id,
    )
    return f"{registers[0]:04X}"
