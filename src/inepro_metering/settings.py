"""Shared writable-setting definitions for Inepro Metering."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from .commands import RegisterWrite
from .const import TransportType
from .models import MeterProfile, MeterSensorDescription

EntityPlatform = Literal["switch", "select", "number"]
MeterReadingValue = str | int | float
WritableSettingValue = bool | float | str | None

WIFI_SUPPORT_SETTING_KEY = "wifi_support"


@dataclass(frozen=True, slots=True)
class WritableSettingDescription:
    """Canonical metadata and write semantics for one writable setting.

    This is the main shared-library API consumed by the Home Assistant wrapper:
    it defines how a setting is exposed, decoded, validated, and converted back
    into Modbus register writes.
    """

    key: str
    name: str
    entity_platform: EntityPlatform
    read_key: str
    required_profile_transports: tuple[TransportType, ...] = ()
    native_min_value: float | None = None
    native_max_value: float | None = None
    native_step: float | None = None
    native_unit_of_measurement: str | None = None
    options_by_value: Mapping[int, str] | None = None

    def resolve_sensor(self, profile: MeterProfile) -> MeterSensorDescription:
        """Return the shared sensor metadata that backs this writable setting."""
        for sensor in profile.all_sensors:
            if sensor.key == self.read_key:
                return sensor
        raise KeyError(
            f"Writable setting {self.key!r} is not available for profile {profile.variant}"
        )

    def supports_profile(self, profile: MeterProfile) -> bool:
        """Return whether this setting applies to the supplied profile."""
        try:
            self.resolve_sensor(profile)
        except KeyError:
            return False
        return all(
            transport in profile.supported_transports
            for transport in self.required_profile_transports
        )

    def resolved_options_by_value(self, profile: MeterProfile) -> dict[int, str]:
        """Return the option map used for select-style writable settings."""
        if self.options_by_value is not None:
            return dict(self.options_by_value)

        sensor = self.resolve_sensor(profile)
        if sensor.options is None:
            raise ValueError(f"Writable setting {self.key!r} does not define options")
        return dict(sensor.options)

    def value_by_option(self, profile: MeterProfile) -> dict[str, int]:
        """Return the reverse option lookup used when writing back to the meter."""
        return {
            label: value
            for value, label in self.resolved_options_by_value(profile).items()
        }

    def native_unit_of_measurement_for_profile(self, profile: MeterProfile) -> str | None:
        """Return the user-facing number unit for this setting."""
        if self.native_unit_of_measurement is not None:
            return self.native_unit_of_measurement
        return self.resolve_sensor(profile).native_unit_of_measurement

    def normalize_value(
        self,
        profile: MeterProfile,
        value: bool | float | str,
    ) -> bool | float | str:
        """Validate and normalize one logical setting value before writing."""
        if self.entity_platform == "switch":
            return bool(value)

        if self.entity_platform == "select":
            if not isinstance(value, str):
                raise ValueError(f"Unsupported option for {self.key}: {value!r}")
            if value not in self.value_by_option(profile):
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

        raise ValueError(f"Unsupported entity platform {self.entity_platform!r}")

    def decode_value(
        self,
        profile: MeterProfile,
        readings: Mapping[str, MeterReadingValue],
    ) -> WritableSettingValue:
        """Decode the current logical setting state from decoded meter readings."""
        value = readings.get(self.read_key)
        if value is None:
            return None

        if self.entity_platform == "switch":
            if isinstance(value, str):
                return value.strip().lower() in {
                    "enabled",
                    "supported",
                    "on",
                    "true",
                    "1",
                }
            return bool(int(value))

        if self.entity_platform == "select":
            if isinstance(value, str):
                return value
            return self.resolved_options_by_value(profile).get(int(value))

        if self.entity_platform == "number":
            return float(value)

        raise ValueError(f"Unsupported entity platform {self.entity_platform!r}")

    def build_writes(
        self,
        profile: MeterProfile,
        value: bool | float | str,
    ) -> tuple[RegisterWrite, ...]:
        """Build the register write plan for one logical setting update."""
        sensor = self.resolve_sensor(profile)
        normalized_value = self.normalize_value(profile, value)

        if self.entity_platform == "switch":
            register_value = 1 if bool(normalized_value) else 0
        elif self.entity_platform == "select":
            register_value = self.value_by_option(profile)[str(normalized_value)]
        elif self.entity_platform == "number":
            register_value = int(float(normalized_value))
        else:
            raise ValueError(f"Unsupported entity platform {self.entity_platform!r}")

        return (
            RegisterWrite(
                address=sensor.address,
                values=(register_value,),
                multiple=False,
            ),
        )


@dataclass(frozen=True, slots=True)
class WritableSettingState:
    """Current logical state for one supported writable setting."""

    description: WritableSettingDescription
    value: WritableSettingValue


WIFI_SUPPORT_SETTING = WritableSettingDescription(
    key=WIFI_SUPPORT_SETTING_KEY,
    name="Wi-Fi Support",
    entity_platform="switch",
    read_key=WIFI_SUPPORT_SETTING_KEY,
    required_profile_transports=(TransportType.TCP_WIFI,),
)

LEGAL_LCD_OBIS_CODES_SETTING = WritableSettingDescription(
    key="legal_lcd_obis_codes",
    name="Legal LCD OBIS Codes",
    entity_platform="switch",
    read_key="legal_lcd_obis_codes",
)

NON_LEGAL_LCD_OBIS_CODES_SETTING = WritableSettingDescription(
    key="non_legal_lcd_obis_codes",
    name="Non-Legal LCD OBIS Codes",
    entity_platform="switch",
    read_key="non_legal_lcd_obis_codes",
)

BACKLIGHT_MODE_SETTING = WritableSettingDescription(
    key="backlight_mode",
    name="Backlight Mode",
    entity_platform="select",
    read_key="backlight_mode",
)

BACKLIGHT_LEVEL_SETTING = WritableSettingDescription(
    key="backlight_level",
    name="Backlight Level",
    entity_platform="select",
    read_key="backlight_level",
)

LEGAL_LCD_TARIFF_MODE_SETTING = WritableSettingDescription(
    key="legal_lcd_tariff_mode",
    name="Display Tariff Mode",
    entity_platform="select",
    read_key="legal_lcd_tariff_mode",
)

LCD_ORIENTATION_SETTING = WritableSettingDescription(
    key="lcd_orientation",
    name="LCD Orientation",
    entity_platform="select",
    read_key="lcd_orientation",
)

BACKLIGHT_TIMEOUT_SETTING = WritableSettingDescription(
    key="backlight_timeout",
    name="Backlight Timeout",
    entity_platform="number",
    read_key="backlight_timeout",
    native_min_value=0,
    native_max_value=30,
    native_step=1,
)

LEGAL_LCD_CYCLE_TIME_SETTING = WritableSettingDescription(
    key="legal_lcd_cycle_time",
    name="Legal LCD Cycle Time",
    entity_platform="number",
    read_key="legal_lcd_cycle_time",
    native_min_value=5,
    native_max_value=30,
    native_step=1,
)

NON_LEGAL_LCD_CYCLE_TIME_SETTING = WritableSettingDescription(
    key="non_legal_lcd_cycle_time",
    name="Non-Legal LCD Cycle Time",
    entity_platform="number",
    read_key="non_legal_lcd_cycle_time",
    native_min_value=5,
    native_max_value=30,
    native_step=1,
)

WRITABLE_SETTINGS: tuple[WritableSettingDescription, ...] = (
    WIFI_SUPPORT_SETTING,
    LEGAL_LCD_OBIS_CODES_SETTING,
    NON_LEGAL_LCD_OBIS_CODES_SETTING,
    BACKLIGHT_MODE_SETTING,
    BACKLIGHT_LEVEL_SETTING,
    LEGAL_LCD_TARIFF_MODE_SETTING,
    LCD_ORIENTATION_SETTING,
    BACKLIGHT_TIMEOUT_SETTING,
    LEGAL_LCD_CYCLE_TIME_SETTING,
    NON_LEGAL_LCD_CYCLE_TIME_SETTING,
)


def get_writable_settings(
    profile: MeterProfile,
    *,
    entity_platform: EntityPlatform | None = None,
) -> tuple[WritableSettingDescription, ...]:
    """Return the shared writable settings supported by one meter profile."""
    return tuple(
        setting
        for setting in WRITABLE_SETTINGS
        if setting.supports_profile(profile)
        and (entity_platform is None or setting.entity_platform == entity_platform)
    )


def get_writable_setting(
    profile: MeterProfile,
    key: str,
) -> WritableSettingDescription:
    """Return one supported writable setting for the supplied profile."""
    for setting in get_writable_settings(profile):
        if setting.key == key:
            return setting
    raise KeyError(f"Unknown writable setting {key!r} for profile {profile.variant}")


def build_writable_setting_states(
    profile: MeterProfile,
    readings: Mapping[str, MeterReadingValue],
) -> dict[str, WritableSettingState]:
    """Build the current logical writable-setting state map for one meter."""
    return {
        setting.key: WritableSettingState(
            description=setting,
            value=setting.decode_value(profile, readings),
        )
        for setting in get_writable_settings(profile)
    }
