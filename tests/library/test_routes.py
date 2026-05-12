"""Tests for the shared configured-route helpers."""

from __future__ import annotations

from inepro_metering.const import TransportType
from inepro_metering.routes import (
    MeterRouteDefinition,
    ROUTE_PURPOSE_ACTIVE,
    ROUTE_PURPOSE_ONBOARDING,
    RouteEndpoint,
    build_route_key,
    describe_route,
    route_matches_endpoint,
)


def test_build_route_key_normalizes_serial_route_identity() -> None:
    """Serial route keys should stay stable across host formatting differences."""
    route = MeterRouteDefinition(
        transport=TransportType.SERIAL,
        slave_id=157,
        timeout=3,
        serial_port="com5",
        baudrate=9600,
        bytesize=8,
        parity="E",
        stopbits=1,
    )

    assert build_route_key(route) == "serial:COM5:157"
    assert describe_route(route) == "Wired RS-485 / Modbus RTU | slave 157 | COM5 | Active"


def test_build_route_key_includes_proxy_host_for_bluetooth_proxy_routes() -> None:
    """Proxy-backed Bluetooth routes should encode both proxy and meter identity."""
    route = MeterRouteDefinition(
        transport=TransportType.BLUETOOTH_PROXY,
        slave_id=1,
        timeout=5,
        purpose=ROUTE_PURPOSE_ONBOARDING,
        host="LOCALHOST",
        port=15026,
        bluetooth_address="aa:bb:cc:dd:ee:ff",
        bluetooth_name="IM-075625100001",
    )

    assert (
        build_route_key(route)
        == "bluetooth_proxy:localhost:15026:AA:BB:CC:DD:EE:FF:1"
    )
    assert (
        describe_route(route)
        == "Windows BLE proxy (developer only) | slave 1 | IM-075625100001 via localhost:15026 | Onboarding"
    )


def test_route_matches_endpoint_for_serial_routes() -> None:
    """Serial routes should compare against the full serial endpoint settings."""
    route = MeterRouteDefinition(
        transport=TransportType.SERIAL,
        slave_id=7,
        timeout=3,
        purpose=ROUTE_PURPOSE_ACTIVE,
        serial_port="COM5",
        baudrate=9600,
        bytesize=8,
        parity="E",
        stopbits=1,
    )

    matching_endpoint = RouteEndpoint(
        transport=TransportType.SERIAL,
        serial_port="com5",
        baudrate=9600,
        bytesize=8,
        parity="E",
        stopbits=1,
    )
    different_endpoint = RouteEndpoint(
        transport=TransportType.SERIAL,
        serial_port="COM5",
        baudrate=19200,
        bytesize=8,
        parity="E",
        stopbits=1,
    )

    assert route_matches_endpoint(route, matching_endpoint) is True
    assert route_matches_endpoint(route, different_endpoint) is False


def test_route_matches_endpoint_for_tcp_and_proxy_routes() -> None:
    """IP-backed routes should compare only the fields relevant to their transport."""
    tcp_route = MeterRouteDefinition(
        transport=TransportType.TCP_GATEWAY,
        slave_id=3,
        timeout=4,
        host="10.5.2.14",
        port=502,
    )
    proxy_route = MeterRouteDefinition(
        transport=TransportType.BLUETOOTH_PROXY,
        slave_id=3,
        timeout=4,
        host="127.0.0.1",
        port=15026,
        bluetooth_address="11:22:33:44:55:66",
    )

    assert route_matches_endpoint(
        tcp_route,
        RouteEndpoint(
            transport=TransportType.TCP_GATEWAY,
            host="10.5.2.14",
            port=502,
        ),
    )
    assert not route_matches_endpoint(
        tcp_route,
        RouteEndpoint(
            transport=TransportType.TCP_GATEWAY,
            host="10.5.2.15",
            port=502,
        ),
    )
    assert route_matches_endpoint(
        proxy_route,
        RouteEndpoint(
            transport=TransportType.BLUETOOTH_PROXY,
            host="127.0.0.1",
            port=15026,
            bluetooth_address="11:22:33:44:55:66",
        ),
    )
    assert not route_matches_endpoint(
        proxy_route,
        RouteEndpoint(
            transport=TransportType.BLUETOOTH_PROXY,
            host="127.0.0.1",
            port=15026,
            bluetooth_address="AA:BB:CC:DD:EE:FF",
        ),
    )


def test_route_endpoint_property_drops_meter_selection_fields() -> None:
    """Route endpoint snapshots should exclude per-meter metadata like slave id."""
    route = MeterRouteDefinition(
        transport=TransportType.TCP_ETHERNET,
        slave_id=9,
        timeout=6,
        host="192.0.2.15",
        port=502,
    )

    assert route.endpoint == RouteEndpoint(
        transport=TransportType.TCP_ETHERNET,
        host="192.0.2.15",
        port=502,
    )
