"""Canonical decoded runtime models for Inepro Metering devices."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from .const import TransportType
from .models import MeterProfile
from .settings import WritableSettingState, build_writable_setting_states

MeterReadingValue = str | int | float
MeterReadings = dict[str, MeterReadingValue]

VERSION_CRC_KEYS = {
    "legal_software_version": "legal_software_crc",
    "non_legal_software_version": "non_legal_software_crc",
}

KNOWN_FIRMWARE_VERSION_BY_CRC = {
    "6A479857": "1.0.2536",
}


def format_meter_version_value(value: MeterReadingValue | None) -> str | None:
    """Normalize decoded version values for device metadata and presentation."""
    if value is None:
        return None
    if isinstance(value, float):
        text = f"{value:.4f}".rstrip("0").rstrip(".")
        if "." not in text:
            text = f"{text}.0"
        return text
    return str(value)


def format_meter_firmware_version(
    value: MeterReadingValue | None,
    crc: str | None,
) -> str | None:
    """Return the canonical user-facing version string for one firmware field."""
    version = format_meter_version_value(value)
    if version is None:
        return None
    if crc is None:
        return version

    normalized_crc = crc.upper()
    mapped_version = KNOWN_FIRMWARE_VERSION_BY_CRC.get(normalized_crc)
    if mapped_version is not None:
        return mapped_version
    return f"{version} ({normalized_crc})"


@dataclass(frozen=True, slots=True)
class MeterIdentity:
    """Stable logical identity for one decoded meter."""

    serial_number: str | None = None
    product_code: str | None = None
    meter_code: str | None = None

    @property
    def device_serial(self) -> str | None:
        """Return the full user-facing device serial number when available."""
        if (
            self.product_code
            and self.serial_number
            and self.serial_number.startswith(self.product_code)
        ):
            return self.serial_number
        if self.product_code and self.serial_number:
            return f"{self.product_code}{self.serial_number}"
        return self.serial_number

    @classmethod
    def from_readings(cls, readings: Mapping[str, MeterReadingValue]) -> MeterIdentity:
        """Build a logical identity object from decoded meter readings."""
        product_code = readings.get("product_code")
        serial_number = readings.get("serial_number")
        meter_code = readings.get("meter_code")
        return cls(
            serial_number=serial_number if isinstance(serial_number, str) else None,
            product_code=product_code if isinstance(product_code, str) else None,
            meter_code=meter_code if isinstance(meter_code, str) else None,
        )


@dataclass(frozen=True, slots=True)
class MeterDeviceIdentification:
    """Stable device-identification metadata decoded from the transport layer."""

    manufacturer_name: str | None = None
    product_name: str | None = None
    device_version: str | None = None

    @classmethod
    def from_readings(
        cls,
        readings: Mapping[str, MeterReadingValue],
    ) -> MeterDeviceIdentification:
        """Build device-identification metadata from decoded readings."""
        manufacturer_name = readings.get("modbus_manufacturer_name")
        product_name = readings.get("modbus_product_name")
        device_version = readings.get("modbus_device_version")
        return cls(
            manufacturer_name=(
                manufacturer_name if isinstance(manufacturer_name, str) else None
            ),
            product_name=product_name if isinstance(product_name, str) else None,
            device_version=device_version if isinstance(device_version, str) else None,
        )


@dataclass(frozen=True, slots=True)
class MeterFirmwareInfo:
    """Decoded firmware and hardware information for one meter."""

    legal_software_version_value: MeterReadingValue | None = None
    legal_software_crc: str | None = None
    non_legal_software_version_value: MeterReadingValue | None = None
    non_legal_software_crc: str | None = None
    protocol_version_value: MeterReadingValue | None = None
    software_version_value: MeterReadingValue | None = None
    hardware_version_value: MeterReadingValue | None = None
    device_version_value: str | None = None

    @classmethod
    def from_readings(cls, readings: Mapping[str, MeterReadingValue]) -> MeterFirmwareInfo:
        """Build a firmware model from decoded meter readings."""
        legal_crc = readings.get("legal_software_crc")
        non_legal_crc = readings.get("non_legal_software_crc")
        device_version = readings.get("modbus_device_version")
        return cls(
            legal_software_version_value=readings.get("legal_software_version"),
            legal_software_crc=legal_crc if isinstance(legal_crc, str) else None,
            non_legal_software_version_value=readings.get("non_legal_software_version"),
            non_legal_software_crc=(
                non_legal_crc if isinstance(non_legal_crc, str) else None
            ),
            protocol_version_value=readings.get("protocol_version"),
            software_version_value=readings.get("software_version"),
            hardware_version_value=readings.get("hardware_version"),
            device_version_value=device_version if isinstance(device_version, str) else None,
        )

    def formatted_version(self, key: str) -> str | None:
        """Return the user-facing version string for one version field."""
        if key == "legal_software_version":
            return format_meter_firmware_version(
                self.legal_software_version_value,
                self.legal_software_crc,
            )
        elif key == "non_legal_software_version":
            return format_meter_firmware_version(
                self.non_legal_software_version_value,
                self.non_legal_software_crc,
            )
        elif key == "protocol_version":
            return format_meter_version_value(self.protocol_version_value)
        elif key == "software_version":
            return format_meter_version_value(self.software_version_value)
        elif key == "hardware_version":
            return self.hardware_version
        return None

    def version_attributes(self, key: str) -> dict[str, str] | None:
        """Return attribute metadata for one version field."""
        if key == "legal_software_version":
            raw_value = self.legal_software_version_value
            crc = self.legal_software_crc
        elif key == "non_legal_software_version":
            raw_value = self.non_legal_software_version_value
            crc = self.non_legal_software_crc
        else:
            return None

        attributes: dict[str, str] = {}
        raw_version = format_meter_version_value(raw_value)
        if raw_version is not None:
            attributes["raw_version"] = raw_version
        if crc is not None:
            attributes["crc"] = crc.upper()
        return attributes or None

    @property
    def software_version(self) -> str | None:
        """Return the compact device-registry software-version string."""
        legal_version = self.formatted_version("legal_software_version")
        non_legal_version = self.formatted_version("non_legal_software_version")

        # Prefer the richer paired legal/non-legal firmware view when both are
        # available, then fall back to transport-level identification or the
        # generic version fields used by other meter families.
        if legal_version and non_legal_version:
            if legal_version == non_legal_version:
                return legal_version
            return f"legal {legal_version} / non-legal {non_legal_version}"
        if self.device_version_value is not None:
            return self.device_version_value
        generic_software_version = self.formatted_version("software_version")
        if generic_software_version is not None:
            return generic_software_version
        protocol_version = self.formatted_version("protocol_version")
        if protocol_version is not None:
            return protocol_version
        return legal_version or non_legal_version

    @property
    def hardware_version(self) -> str | None:
        """Return the normalized hardware-version string."""
        return format_meter_version_value(self.hardware_version_value)


@dataclass(frozen=True, slots=True)
class MeterGatewayInfo:
    """Decoded metadata for a TCP gateway route when available."""

    device_type: str | None = None
    hardware_version: str | None = None
    serial_number: str | None = None
    firmware_version: str | None = None
    bootloader_version: str | None = None

    @classmethod
    def from_readings(cls, readings: Mapping[str, MeterReadingValue]) -> MeterGatewayInfo:
        """Build a gateway metadata view from decoded readings."""
        device_type = readings.get("tcp_gateway_device_type")
        hardware_version = readings.get("tcp_gateway_hardware_version")
        serial_number = readings.get("tcp_gateway_serial_number")
        firmware_version = readings.get("tcp_gateway_firmware_version")
        bootloader_version = readings.get("tcp_gateway_bootloader_version")
        return cls(
            device_type=device_type if isinstance(device_type, str) else None,
            hardware_version=(
                hardware_version if isinstance(hardware_version, str) else None
            ),
            serial_number=serial_number if isinstance(serial_number, str) else None,
            firmware_version=firmware_version if isinstance(firmware_version, str) else None,
            bootloader_version=(
                bootloader_version if isinstance(bootloader_version, str) else None
            ),
        )


@dataclass(frozen=True, slots=True)
class MeterRoute:
    """Stable route information for reaching one meter."""

    transport: TransportType
    slave_id: int


@dataclass(frozen=True, slots=True)
class MeterConnectionState:
    """Availability and last-success timing for one meter route."""

    available: bool
    last_successful_update: datetime | None


@dataclass(frozen=True, slots=True)
class MeterRuntimeData:
    """Canonical logical runtime model consumed by Home Assistant.

    This is the shared boundary between protocol/transport code and higher-level
    consumers such as the Home Assistant wrapper or future MQTT/Victron layers.
    """

    profile: MeterProfile
    route: MeterRoute
    connection: MeterConnectionState
    readings: MeterReadings
    identity: MeterIdentity
    device_identification: MeterDeviceIdentification
    firmware: MeterFirmwareInfo
    gateway: MeterGatewayInfo
    writable_settings: dict[str, WritableSettingState]

    @classmethod
    def from_readings(
        cls,
        *,
        profile: MeterProfile,
        route: MeterRoute,
        readings: Mapping[str, MeterReadingValue],
        available: bool,
        last_successful_update: datetime | None,
    ) -> MeterRuntimeData:
        """Build one canonical runtime model from decoded register values."""
        normalized_readings = dict(readings)
        return cls(
            profile=profile,
            route=route,
            connection=MeterConnectionState(
                available=available,
                last_successful_update=last_successful_update,
            ),
            readings=normalized_readings,
            identity=MeterIdentity.from_readings(normalized_readings),
            device_identification=MeterDeviceIdentification.from_readings(
                normalized_readings
            ),
            firmware=MeterFirmwareInfo.from_readings(normalized_readings),
            gateway=MeterGatewayInfo.from_readings(normalized_readings),
            writable_settings=build_writable_setting_states(profile, normalized_readings),
        )


def build_meter_runtime_data(
    *,
    profile: MeterProfile,
    route: MeterRoute,
    readings: Mapping[str, MeterReadingValue],
    available: bool,
    last_successful_update: datetime | None,
) -> MeterRuntimeData:
    """Build the canonical meter runtime model."""
    return MeterRuntimeData.from_readings(
        profile=profile,
        route=route,
        readings=readings,
        available=available,
        last_successful_update=last_successful_update,
    )
