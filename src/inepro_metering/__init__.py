"""Standalone protocol and model library for Inepro Metering devices."""

from importlib.metadata import PackageNotFoundError, version

from .const import FAMILY_LABELS, TRANSPORT_LABELS, MeterFamily, TransportType
from .discovery import (
    DiscoveredGrowMeter,
    GrowSerialNumber,
    build_grow_serial_number,
    infer_grow_variant,
    parse_grow_bluetooth_name,
    parse_grow_serial_number,
)
from .exceptions import (
    IneproBluetoothNotPairedError,
    IneproConnectionError,
    IneproMeteringError,
    IneproReadError,
    IneproWriteError,
)
from .models import MeterProfile, MeterSensorDescription, get_profile, get_profiles_for_family
from .ocmf import GROW_OCMF_REGISTERS, OcmfRegisterDefinition
from .routes import (
    MeterRouteDefinition,
    ROUTE_PURPOSE_ACTIVE,
    ROUTE_PURPOSE_ONBOARDING,
    RouteEndpoint,
    build_route_key,
    describe_route,
    route_matches_endpoint,
)

try:
    __version__ = version("inepro-metering")
except PackageNotFoundError:
    __version__ = "0.1.0"

__all__ = [
    "__version__",
    "FAMILY_LABELS",
    "TRANSPORT_LABELS",
    "MeterFamily",
    "TransportType",
    "DiscoveredGrowMeter",
    "GrowSerialNumber",
    "MeterProfile",
    "MeterSensorDescription",
    "MeterRouteDefinition",
    "OcmfRegisterDefinition",
    "GROW_OCMF_REGISTERS",
    "ROUTE_PURPOSE_ACTIVE",
    "ROUTE_PURPOSE_ONBOARDING",
    "RouteEndpoint",
    "IneproBluetoothNotPairedError",
    "IneproConnectionError",
    "IneproMeteringError",
    "IneproReadError",
    "IneproWriteError",
    "build_grow_serial_number",
    "build_route_key",
    "describe_route",
    "infer_grow_variant",
    "parse_grow_bluetooth_name",
    "parse_grow_serial_number",
    "get_profile",
    "get_profiles_for_family",
    "route_matches_endpoint",
]
