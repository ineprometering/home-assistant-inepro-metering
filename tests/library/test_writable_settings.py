"""Tests for shared writable-setting definitions."""

from inepro_metering.const import MeterFamily
from inepro_metering.models import get_profile
from inepro_metering.settings import (
    WIFI_SUPPORT_SETTING_KEY,
    build_writable_setting_states,
    get_writable_setting,
    get_writable_settings,
)


def test_grow_profiles_expose_shared_writable_settings_by_platform() -> None:
    """Switch, select, and number settings should all come from shared definitions."""
    grow_750 = get_profile(MeterFamily.GROW, "grow_750")
    grow_850 = get_profile(MeterFamily.GROW, "grow_850")

    assert [setting.key for setting in get_writable_settings(grow_750, entity_platform="switch")] == [
        WIFI_SUPPORT_SETTING_KEY,
        "legal_lcd_obis_codes",
        "non_legal_lcd_obis_codes",
    ]
    assert [setting.key for setting in get_writable_settings(grow_850, entity_platform="switch")] == [
        "legal_lcd_obis_codes",
        "non_legal_lcd_obis_codes",
    ]
    assert [setting.key for setting in get_writable_settings(grow_850, entity_platform="select")] == [
        "backlight_mode",
        "backlight_level",
        "legal_lcd_tariff_mode",
        "lcd_orientation",
    ]
    assert [setting.key for setting in get_writable_settings(grow_850, entity_platform="number")] == [
        "backlight_timeout",
        "legal_lcd_cycle_time",
        "non_legal_lcd_cycle_time",
    ]


def test_wifi_support_setting_uses_shared_decode_and_write_rules() -> None:
    """The shared Wi-Fi setting should own both logical decode and write semantics."""
    profile = get_profile(MeterFamily.GROW, "grow_701")
    setting = get_writable_setting(profile, WIFI_SUPPORT_SETTING_KEY)

    assert setting.decode_value(profile, {WIFI_SUPPORT_SETTING_KEY: "supported"}) is True
    assert setting.decode_value(profile, {WIFI_SUPPORT_SETTING_KEY: 0}) is False
    assert setting.decode_value(profile, {}) is None
    assert setting.build_writes(profile, True)[0].address == 0x4C06
    assert setting.build_writes(profile, True)[0].values == (1,)
    assert setting.build_writes(profile, False)[0].values == (0,)


def test_select_setting_uses_shared_option_map_and_reverse_lookup() -> None:
    """Select settings should derive both option maps and write values from shared metadata."""
    profile = get_profile(MeterFamily.GROW, "grow_850")
    setting = get_writable_setting(profile, "backlight_mode")

    assert setting.resolved_options_by_value(profile) == {
        0: "Always On",
        1: "Always Off",
        2: "Button Activated",
    }
    assert setting.value_by_option(profile)["Always Off"] == 1
    assert setting.decode_value(profile, {"backlight_mode": "Button Activated"}) == (
        "Button Activated"
    )
    assert setting.build_writes(profile, "Always Off")[0].address == 0x4C02
    assert setting.build_writes(profile, "Always Off")[0].values == (1,)


def test_number_setting_uses_shared_numeric_validation_and_write_rules() -> None:
    """Number settings should centralize their ranges, step metadata, and write semantics."""
    profile = get_profile(MeterFamily.GROW, "grow_850")
    setting = get_writable_setting(profile, "backlight_timeout")

    assert setting.native_min_value == 0
    assert setting.native_max_value == 30
    assert setting.native_step == 1
    assert setting.native_unit_of_measurement_for_profile(profile) == "min"
    assert setting.decode_value(profile, {"backlight_timeout": 12}) == 12.0
    assert setting.build_writes(profile, 12)[0].address == 0x4C04
    assert setting.build_writes(profile, 12)[0].values == (12,)

    try:
        setting.normalize_value(profile, 31)
    except ValueError as err:
        assert str(err) == "backlight_timeout must stay between 0 and 30"
    else:
        raise AssertionError("Expected out-of-range numeric value to be rejected")


def test_runtime_state_builder_includes_display_settings() -> None:
    """Runtime writable-setting state should include the extracted display settings."""
    profile = get_profile(MeterFamily.GROW, "grow_850")
    states = build_writable_setting_states(
        profile,
        {
            "backlight_mode": "Button Activated",
            "backlight_timeout": 9,
            "legal_lcd_obis_codes": "enabled",
        },
    )

    assert states["backlight_mode"].value == "Button Activated"
    assert states["backlight_timeout"].value == 9.0
    assert states["legal_lcd_obis_codes"].value is True
