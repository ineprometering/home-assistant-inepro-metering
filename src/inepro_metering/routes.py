"""Shared configured-route models and helpers.

These types intentionally stay independent of any Home Assistant config-entry
shape so other adapters can reuse the same route semantics later.
"""

from __future__ import annotations

from dataclasses import dataclass

from .const import TRANSPORT_LABELS, TransportType

ROUTE_PURPOSE_ACTIVE = "active"
ROUTE_PURPOSE_ONBOARDING = "onboarding"


@dataclass(frozen=True, slots=True)
class RouteEndpoint:
    """Normalized transport endpoint independent of storage format."""

    transport: TransportType
    host: str | None = None
    port: int | None = None
    serial_port: str | None = None
    baudrate: int | None = None
    bytesize: int | None = None
    parity: str | None = None
    stopbits: int | None = None
    bluetooth_address: str | None = None
    bluetooth_name: str | None = None


@dataclass(frozen=True, slots=True)
class MeterRouteDefinition:
    """One configured transport route for reaching a physical meter."""

    transport: TransportType
    slave_id: int
    timeout: int
    purpose: str = ROUTE_PURPOSE_ACTIVE
    host: str | None = None
    port: int | None = None
    serial_port: str | None = None
    baudrate: int | None = None
    bytesize: int | None = None
    parity: str | None = None
    stopbits: int | None = None
    bluetooth_address: str | None = None
    bluetooth_name: str | None = None

    @property
    def endpoint(self) -> RouteEndpoint:
        """Return the transport endpoint without meter-selection metadata."""
        return RouteEndpoint(
            transport=self.transport,
            host=self.host,
            port=self.port,
            serial_port=self.serial_port,
            baudrate=self.baudrate,
            bytesize=self.bytesize,
            parity=self.parity,
            stopbits=self.stopbits,
            bluetooth_address=self.bluetooth_address,
            bluetooth_name=self.bluetooth_name,
        )


def build_route_key(route: MeterRouteDefinition) -> str:
    """Build a stable key for one configured route."""
    transport = route.transport
    if transport is TransportType.SERIAL:
        endpoint = f"{str(route.serial_port).strip().upper()}:{int(route.slave_id)}"
    elif transport in {TransportType.BLUETOOTH, TransportType.BLUETOOTH_PROXY}:
        endpoint = f"{str(route.bluetooth_address).strip().upper()}:{int(route.slave_id)}"
        if transport is TransportType.BLUETOOTH_PROXY:
            endpoint = (
                f"{str(route.host).strip().lower()}:{int(route.port)}:{endpoint}"
            )
    else:
        endpoint = f"{str(route.host).strip().lower()}:{int(route.port)}:{int(route.slave_id)}"
    return f"{transport.value}:{endpoint}"


def describe_route(route: MeterRouteDefinition) -> str:
    """Build a human-friendly route description."""
    if route.transport is TransportType.SERIAL:
        target = str(route.serial_port).strip().upper()
    elif route.transport is TransportType.BLUETOOTH:
        target = route.bluetooth_name or str(route.bluetooth_address).strip().upper()
    elif route.transport is TransportType.BLUETOOTH_PROXY:
        target = (
            f"{route.bluetooth_name or str(route.bluetooth_address).strip().upper()} "
            f"via {str(route.host).strip().lower()}:{int(route.port)}"
        )
    else:
        target = f"{str(route.host).strip().lower()}:{int(route.port)}"

    purpose_label = "Onboarding" if route.purpose != ROUTE_PURPOSE_ACTIVE else "Active"
    return (
        f"{TRANSPORT_LABELS[route.transport]} | slave {int(route.slave_id)} | "
        f"{target} | {purpose_label}"
    )


def route_matches_endpoint(
    route: MeterRouteDefinition,
    endpoint: RouteEndpoint,
) -> bool:
    """Return whether a route targets the same transport endpoint."""
    transport = endpoint.transport
    if route.transport is not transport:
        return False

    if transport is TransportType.SERIAL:
        return (
            str(route.serial_port).strip().upper()
            == str(endpoint.serial_port).strip().upper()
            and int(route.baudrate) == int(endpoint.baudrate)
            and int(route.bytesize) == int(endpoint.bytesize)
            and str(route.parity) == str(endpoint.parity)
            and int(route.stopbits) == int(endpoint.stopbits)
        )

    if transport is TransportType.BLUETOOTH:
        return str(route.bluetooth_address).strip().upper() == str(
            endpoint.bluetooth_address
        ).strip().upper()

    if transport is TransportType.BLUETOOTH_PROXY:
        return (
            str(route.host).strip().lower() == str(endpoint.host).strip().lower()
            and int(route.port) == int(endpoint.port)
            and str(route.bluetooth_address).strip().upper()
            == str(endpoint.bluetooth_address).strip().upper()
        )

    return (
        str(route.host).strip().lower() == str(endpoint.host).strip().lower()
        and int(route.port) == int(endpoint.port)
    )


__all__ = [
    "MeterRouteDefinition",
    "ROUTE_PURPOSE_ACTIVE",
    "ROUTE_PURPOSE_ONBOARDING",
    "RouteEndpoint",
    "build_route_key",
    "describe_route",
    "route_matches_endpoint",
]
