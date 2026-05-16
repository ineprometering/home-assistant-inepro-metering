"""Pure Python meter family and register models for Inepro Metering."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .const import MeterFamily, TransportType

MODEL_701 = "701"
MODEL_750 = "750"
MODEL_800 = "800"
MODEL_850 = "850"
MODEL_PRO1 = "pro1"
MODEL_PRO2 = "pro2"
MODEL_PRO380 = "pro380"
MODEL_PRO380CT = "pro380ct"
MODEL_PRO1_SOLARE = "pro1_solare"
MODEL_PRO2_SOLARE = "pro2_solare"
MODEL_PRO380_SOLARE = "pro380_solare"
MODEL_PRO380CT_SOLARE = "pro380ct_solare"
MODEL_N1 = "n1"
MODEL_N380_40A = "n380_40a"
MODEL_N380CT = "n380ct"

ALL_MODELS = frozenset({MODEL_701, MODEL_750, MODEL_800, MODEL_850})
THREE_PHASE_MODELS = frozenset({MODEL_701, MODEL_750})
OCMF_MODELS = frozenset({MODEL_701, MODEL_750, MODEL_800})
THD_MODELS = frozenset({MODEL_701, MODEL_750, MODEL_800})
NETWORKED_MODELS = frozenset({MODEL_701, MODEL_750, MODEL_800})
ETHERNET_MODELS = frozenset({MODEL_701, MODEL_750})
PRO_ALL_MODELS = frozenset(
    {
        MODEL_PRO1,
        MODEL_PRO2,
        MODEL_PRO380,
        MODEL_PRO380CT,
        MODEL_PRO1_SOLARE,
        MODEL_PRO2_SOLARE,
        MODEL_PRO380_SOLARE,
        MODEL_PRO380CT_SOLARE,
        MODEL_N1,
        MODEL_N380_40A,
        MODEL_N380CT,
    }
)
PRO_SINGLE_PHASE_MODELS = frozenset(
    {MODEL_PRO1, MODEL_PRO2, MODEL_PRO1_SOLARE, MODEL_PRO2_SOLARE, MODEL_N1}
)
PRO_THREE_PHASE_MODELS = frozenset(
    {
        MODEL_PRO380,
        MODEL_PRO380CT,
        MODEL_PRO380_SOLARE,
        MODEL_PRO380CT_SOLARE,
        MODEL_N380_40A,
        MODEL_N380CT,
    }
)
PRO_CT_MODELS = frozenset({MODEL_PRO380CT, MODEL_PRO380CT_SOLARE, MODEL_N380CT})

SUPPORT_STATE_OPTIONS = {
    0: "not supported",
    1: "supported",
}

ENABLE_STATE_OPTIONS = {
    0: "disabled",
    1: "enabled",
}

BLUETOOTH_MODE_OPTIONS = {
    0: "off",
    1: "auto",
    2: "on",
}

ON_OFF_OPTIONS = {
    0: "off",
    1: "on",
}

BACKLIGHT_LEVEL_OPTIONS = {
    0: "0%",
    20: "20%",
    40: "40%",
    60: "60%",
    100: "100%",
}

BACKLIGHT_MODE_OPTIONS = {
    0: "Always On",
    1: "Always Off",
    2: "Button Activated",
}

LCD_TARIFF_MODE_OPTIONS = {
    0: "Automatic (Show Used Tariffs)",
    1: "Show 1-2 Always, Others When Used",
    2: "Show All Tariffs",
}

LCD_ORIENTATION_OPTIONS = {
    0: "Standard",
    1: "Turn 180 degrees",
}

PRO_PARITY_OPTIONS = {
    1: "even",
    2: "none",
    3: "odd",
}

PRO_TARIFF_OPTIONS = {
    1: "T1",
    2: "T2",
    11: "T1 not saved",
    12: "T2 not saved",
}

GROW_TARIFF_OPTIONS = {
    1: "T1",
    2: "T2",
    3: "T3",
    4: "T4",
}


GROW_ERROR_BIT_MESSAGES: tuple[tuple[int, str], ...] = (
    (0x0001, "legal software CRC error"),
    (0x0002, "EEPROM communication error"),
    (0x0004, "calibration data corruption"),
    (0x0008, "measuring hardware communication error"),
    (0x0010, "production completed flag is not set"),
    (0x0020, "meter failed to calibrate successfully"),
    (0x0040, "counter journal corruption"),
    (0x0080, "provisioning data invalid"),
)

_GROW_ERROR_MASK = sum(bit for bit, _ in GROW_ERROR_BIT_MESSAGES)


class RegisterType(StrEnum):
    """Supported Modbus register types."""

    HOLDING = "holding"
    INPUT = "input"


class RegisterValueType(StrEnum):
    """Supported register value encodings."""

    UINT16 = "uint16"
    INT16 = "int16"
    UINT32 = "uint32"
    INT32 = "int32"
    FLOAT32 = "float32"
    BCD16 = "bcd16"
    BCD32 = "bcd32"
    HEX16 = "hex16"
    HEX32 = "hex32"


class RegisterFormatType(StrEnum):
    """Supported raw register format labels from the Inepro register map."""

    TIMESTAMP = "timestamp"
    DEC = "dec"
    HEX = "hex"
    FLOAT = "float"
    ENUM = "enum"
    ASCII = "ascii"
    BIN = "bin"
    BOOL = "bool"
    WAIT = "wait"
    CMD = "cmd"
    IPADDRESS = "ipaddress"


@dataclass(frozen=True, kw_only=True)
class MeterSensorDescription:
    """Pure Python sensor description for one Modbus register-backed value."""

    key: str
    name: str
    register_type: RegisterType
    address: int
    count: int
    value_type: RegisterValueType
    supported_models: frozenset[str]
    scale: float = 1.0
    native_unit_of_measurement: str | None = None
    device_class: str | None = None
    state_class: str | None = "measurement"
    suggested_display_precision: int | None = None
    entity_registry_enabled_default: bool = True
    entity_category: str | None = None
    options: dict[int, str] | None = None
    register_unit: str | None = None
    register_format: RegisterFormatType | None = None


@dataclass(frozen=True, slots=True)
class MeterProfile:
    """A selectable Inepro meter profile."""

    family: MeterFamily
    variant: str
    title: str
    model_code: str
    device_model: str
    supported_transports: tuple[TransportType, ...]
    measurement_sensors: tuple[MeterSensorDescription, ...]
    diagnostic_sensors: tuple[MeterSensorDescription, ...]
    config_sensors: tuple[MeterSensorDescription, ...]

    @property
    def all_sensors(self) -> tuple[MeterSensorDescription, ...]:
        """Return all sensor descriptions for one profile."""
        return self.measurement_sensors + self.diagnostic_sensors + self.config_sensors


def _count_for(value_type: RegisterValueType) -> int:
    """Return the register count for a value type."""
    if value_type in {
        RegisterValueType.UINT16,
        RegisterValueType.INT16,
        RegisterValueType.BCD16,
        RegisterValueType.HEX16,
    }:
        return 1
    return 2


def _sensor(
    *,
    key: str,
    name: str,
    address: int,
    value_type: RegisterValueType,
    supported_models: frozenset[str],
    unit: str | None = None,
    device_class: str | None = None,
    state_class: str | None = "measurement",
    precision: int | None = None,
    scale: float = 1.0,
    enabled_by_default: bool = True,
    entity_category: str | None = None,
    options: dict[int, str] | None = None,
    register_unit: str | None = None,
    register_format: RegisterFormatType | None = None,
) -> MeterSensorDescription:
    """Build a sensor description."""
    return MeterSensorDescription(
        key=key,
        name=name,
        register_type=RegisterType.HOLDING,
        address=address,
        count=_count_for(value_type),
        value_type=value_type,
        scale=scale,
        supported_models=supported_models,
        native_unit_of_measurement=unit,
        device_class=device_class,
        state_class=state_class,
        suggested_display_precision=precision,
        entity_registry_enabled_default=enabled_by_default,
        entity_category=entity_category,
        options=options,
        register_unit=register_unit if register_unit is not None else unit,
        register_format=(
            register_format
            if register_format is not None
            else _default_register_format(value_type)
        ),
    )


def _diagnostic_sensor(
    *,
    key: str,
    name: str,
    address: int,
    value_type: RegisterValueType,
    supported_models: frozenset[str],
    unit: str | None = None,
    device_class: str | None = None,
    precision: int | None = None,
    scale: float = 1.0,
    enabled_by_default: bool = True,
    options: dict[int, str] | None = None,
    register_unit: str | None = None,
    register_format: RegisterFormatType | None = None,
) -> MeterSensorDescription:
    """Build a diagnostic sensor description."""
    return _sensor(
        key=key,
        name=name,
        address=address,
        value_type=value_type,
        supported_models=supported_models,
        unit=unit,
        device_class=device_class,
        state_class=None,
        precision=precision,
        scale=scale,
        enabled_by_default=enabled_by_default,
        entity_category="diagnostic",
        options=options,
        register_unit=register_unit,
        register_format=register_format,
    )


def _config_sensor(
    *,
    key: str,
    name: str,
    address: int,
    value_type: RegisterValueType,
    supported_models: frozenset[str],
    unit: str | None = None,
    precision: int | None = None,
    scale: float = 1.0,
    options: dict[int, str] | None = None,
    register_unit: str | None = None,
    register_format: RegisterFormatType | None = None,
) -> MeterSensorDescription:
    """Build a register-backed configuration value description."""
    return _sensor(
        key=key,
        name=name,
        address=address,
        value_type=value_type,
        supported_models=supported_models,
        unit=unit,
        state_class=None,
        precision=precision,
        scale=scale,
        enabled_by_default=False,
        entity_category="config",
        options=options,
        register_unit=register_unit,
        register_format=register_format,
    )


def _default_register_format(value_type: RegisterValueType) -> RegisterFormatType:
    """Return the default raw format label for one register data type."""
    if value_type is RegisterValueType.FLOAT32:
        return RegisterFormatType.FLOAT
    if value_type in {RegisterValueType.HEX16, RegisterValueType.HEX32}:
        return RegisterFormatType.HEX
    return RegisterFormatType.DEC


GROW_MEASUREMENT_SENSORS: tuple[MeterSensorDescription, ...] = (
    _sensor(
        key="average_voltage_ln",
        name="Average Voltage LN",
        address=0x5000,
        value_type=RegisterValueType.FLOAT32,
        supported_models=ALL_MODELS,
        unit="V",
        device_class="voltage",
        precision=1,
    ),
    _sensor(
        key="grid_frequency",
        name="Grid Frequency",
        address=0x5008,
        value_type=RegisterValueType.FLOAT32,
        supported_models=ALL_MODELS,
        unit="Hz",
        device_class="frequency",
        precision=2,
    ),
    _sensor(
        key="total_current",
        name="Total Current",
        address=0x500A,
        value_type=RegisterValueType.FLOAT32,
        supported_models=ALL_MODELS,
        unit="A",
        device_class="current",
        precision=2,
    ),
    _sensor(
        key="total_active_power",
        name="Total Active Power",
        address=0x5012,
        value_type=RegisterValueType.FLOAT32,
        supported_models=ALL_MODELS,
        unit="kW",
        device_class="power",
        precision=3,
    ),
    _sensor(
        key="total_reactive_power",
        name="Total Reactive Power",
        address=0x501A,
        value_type=RegisterValueType.FLOAT32,
        supported_models=ALL_MODELS,
        unit="kvar",
        device_class="reactive_power",
        precision=3,
    ),
    _sensor(
        key="total_apparent_power",
        name="Total Apparent Power",
        address=0x5022,
        value_type=RegisterValueType.FLOAT32,
        supported_models=ALL_MODELS,
        unit="kVA",
        device_class="apparent_power",
        precision=3,
    ),
    _sensor(
        key="total_power_factor",
        name="Total Power Factor",
        address=0x502A,
        value_type=RegisterValueType.FLOAT32,
        supported_models=ALL_MODELS,
        device_class="power_factor",
        precision=3,
    ),
    _sensor(
        key="neutral_current",
        name="Neutral Current",
        address=0x503A,
        value_type=RegisterValueType.FLOAT32,
        supported_models=ALL_MODELS,
        unit="A",
        device_class="current",
        precision=2,
        enabled_by_default=False,
    ),
    _sensor(
        key="temperature",
        name="Temperature",
        address=0x503C,
        value_type=RegisterValueType.FLOAT32,
        supported_models=ALL_MODELS,
        unit="°C",
        device_class="temperature",
        precision=1,
        enabled_by_default=False,
    ),
    _sensor(
        key="forward_active_energy",
        name="Forward Active Energy",
        address=0x600C,
        value_type=RegisterValueType.UINT32,
        supported_models=ALL_MODELS,
        unit="kWh",
        register_unit="Wh",
        device_class="energy",
        state_class="total_increasing",
        scale=0.001,
        precision=3,
    ),
    _sensor(
        key="reverse_active_energy",
        name="Reverse Active Energy",
        address=0x6018,
        value_type=RegisterValueType.UINT32,
        supported_models=ALL_MODELS,
        unit="kWh",
        register_unit="Wh",
        device_class="energy",
        state_class="total_increasing",
        scale=0.001,
        precision=3,
    ),
    _sensor(
        key="forward_reactive_energy",
        name="Forward Reactive Energy",
        address=0x6030,
        value_type=RegisterValueType.UINT32,
        supported_models=ALL_MODELS,
        unit="kvarh",
        register_unit="varh",
        device_class="reactive_energy",
        state_class="total_increasing",
        scale=0.001,
        precision=3,
        enabled_by_default=False,
    ),
    _sensor(
        key="reverse_reactive_energy",
        name="Reverse Reactive Energy",
        address=0x603C,
        value_type=RegisterValueType.UINT32,
        supported_models=ALL_MODELS,
        unit="kvarh",
        register_unit="varh",
        device_class="reactive_energy",
        state_class="total_increasing",
        scale=0.001,
        precision=3,
        enabled_by_default=False,
    ),
    _sensor(
        key="total_active_energy",
        name="Total Active Energy",
        address=0x6000,
        value_type=RegisterValueType.INT32,
        supported_models=ALL_MODELS,
        unit="kWh",
        register_unit="Wh",
        device_class="energy",
        state_class="total",
        scale=0.001,
        precision=3,
        enabled_by_default=False,
    ),
    _sensor(
        key="voltage_l1",
        name="Voltage L1",
        address=0x5002,
        value_type=RegisterValueType.FLOAT32,
        supported_models=THREE_PHASE_MODELS,
        unit="V",
        device_class="voltage",
        precision=1,
    ),
    _sensor(
        key="voltage_l2",
        name="Voltage L2",
        address=0x5004,
        value_type=RegisterValueType.FLOAT32,
        supported_models=THREE_PHASE_MODELS,
        unit="V",
        device_class="voltage",
        precision=1,
    ),
    _sensor(
        key="voltage_l3",
        name="Voltage L3",
        address=0x5006,
        value_type=RegisterValueType.FLOAT32,
        supported_models=THREE_PHASE_MODELS,
        unit="V",
        device_class="voltage",
        precision=1,
    ),
    _sensor(
        key="current_l1",
        name="Current L1",
        address=0x500C,
        value_type=RegisterValueType.FLOAT32,
        supported_models=THREE_PHASE_MODELS,
        unit="A",
        device_class="current",
        precision=2,
    ),
    _sensor(
        key="current_l2",
        name="Current L2",
        address=0x500E,
        value_type=RegisterValueType.FLOAT32,
        supported_models=THREE_PHASE_MODELS,
        unit="A",
        device_class="current",
        precision=2,
    ),
    _sensor(
        key="current_l3",
        name="Current L3",
        address=0x5010,
        value_type=RegisterValueType.FLOAT32,
        supported_models=THREE_PHASE_MODELS,
        unit="A",
        device_class="current",
        precision=2,
    ),
    _sensor(
        key="active_power_l1",
        name="Active Power L1",
        address=0x5014,
        value_type=RegisterValueType.FLOAT32,
        supported_models=THREE_PHASE_MODELS,
        unit="kW",
        device_class="power",
        precision=3,
    ),
    _sensor(
        key="active_power_l2",
        name="Active Power L2",
        address=0x5016,
        value_type=RegisterValueType.FLOAT32,
        supported_models=THREE_PHASE_MODELS,
        unit="kW",
        device_class="power",
        precision=3,
    ),
    _sensor(
        key="active_power_l3",
        name="Active Power L3",
        address=0x5018,
        value_type=RegisterValueType.FLOAT32,
        supported_models=THREE_PHASE_MODELS,
        unit="kW",
        device_class="power",
        precision=3,
    ),
    _sensor(
        key="power_factor_l1",
        name="Power Factor L1",
        address=0x502C,
        value_type=RegisterValueType.FLOAT32,
        supported_models=THREE_PHASE_MODELS,
        device_class="power_factor",
        precision=3,
    ),
    _sensor(
        key="power_factor_l2",
        name="Power Factor L2",
        address=0x502E,
        value_type=RegisterValueType.FLOAT32,
        supported_models=THREE_PHASE_MODELS,
        device_class="power_factor",
        precision=3,
    ),
    _sensor(
        key="power_factor_l3",
        name="Power Factor L3",
        address=0x5030,
        value_type=RegisterValueType.FLOAT32,
        supported_models=THREE_PHASE_MODELS,
        device_class="power_factor",
        precision=3,
    ),
    _sensor(
        key="reactive_power_l1",
        name="Reactive Power L1",
        address=0x501C,
        value_type=RegisterValueType.FLOAT32,
        supported_models=THREE_PHASE_MODELS,
        unit="kvar",
        device_class="reactive_power",
        precision=3,
        enabled_by_default=False,
    ),
    _sensor(
        key="reactive_power_l2",
        name="Reactive Power L2",
        address=0x501E,
        value_type=RegisterValueType.FLOAT32,
        supported_models=THREE_PHASE_MODELS,
        unit="kvar",
        device_class="reactive_power",
        precision=3,
        enabled_by_default=False,
    ),
    _sensor(
        key="reactive_power_l3",
        name="Reactive Power L3",
        address=0x5020,
        value_type=RegisterValueType.FLOAT32,
        supported_models=THREE_PHASE_MODELS,
        unit="kvar",
        device_class="reactive_power",
        precision=3,
        enabled_by_default=False,
    ),
    _sensor(
        key="apparent_power_l1",
        name="Apparent Power L1",
        address=0x5024,
        value_type=RegisterValueType.FLOAT32,
        supported_models=THREE_PHASE_MODELS,
        unit="kVA",
        device_class="apparent_power",
        precision=3,
        enabled_by_default=False,
    ),
    _sensor(
        key="apparent_power_l2",
        name="Apparent Power L2",
        address=0x5026,
        value_type=RegisterValueType.FLOAT32,
        supported_models=THREE_PHASE_MODELS,
        unit="kVA",
        device_class="apparent_power",
        precision=3,
        enabled_by_default=False,
    ),
    _sensor(
        key="apparent_power_l3",
        name="Apparent Power L3",
        address=0x5028,
        value_type=RegisterValueType.FLOAT32,
        supported_models=THREE_PHASE_MODELS,
        unit="kVA",
        device_class="apparent_power",
        precision=3,
        enabled_by_default=False,
    ),
    _sensor(
        key="voltage_l1_l2",
        name="Voltage L1-L2",
        address=0x5032,
        value_type=RegisterValueType.FLOAT32,
        supported_models=THREE_PHASE_MODELS,
        unit="V",
        device_class="voltage",
        precision=1,
        enabled_by_default=False,
    ),
    _sensor(
        key="voltage_l1_l3",
        name="Voltage L1-L3",
        address=0x5034,
        value_type=RegisterValueType.FLOAT32,
        supported_models=THREE_PHASE_MODELS,
        unit="V",
        device_class="voltage",
        precision=1,
        enabled_by_default=False,
    ),
    _sensor(
        key="voltage_l2_l3",
        name="Voltage L2-L3",
        address=0x5036,
        value_type=RegisterValueType.FLOAT32,
        supported_models=THREE_PHASE_MODELS,
        unit="V",
        device_class="voltage",
        precision=1,
        enabled_by_default=False,
    ),
    _sensor(
        key="average_voltage_ll",
        name="Average Voltage LL",
        address=0x5038,
        value_type=RegisterValueType.FLOAT32,
        supported_models=THREE_PHASE_MODELS,
        unit="V",
        device_class="voltage",
        precision=1,
        enabled_by_default=False,
    ),
    _sensor(
        key="average_voltage_thd",
        name="Average Voltage THD",
        address=0x504A,
        value_type=RegisterValueType.FLOAT32,
        supported_models=THD_MODELS,
        unit="%",
        precision=2,
        enabled_by_default=False,
    ),
    _sensor(
        key="average_current_thd",
        name="Average Current THD",
        address=0x504C,
        value_type=RegisterValueType.FLOAT32,
        supported_models=THD_MODELS,
        unit="%",
        precision=2,
        enabled_by_default=False,
    ),
    _sensor(
        key="voltage_l1_thd",
        name="Voltage L1 THD",
        address=0x503E,
        value_type=RegisterValueType.FLOAT32,
        supported_models=THREE_PHASE_MODELS,
        unit="%",
        precision=2,
        enabled_by_default=False,
    ),
    _sensor(
        key="voltage_l2_thd",
        name="Voltage L2 THD",
        address=0x5040,
        value_type=RegisterValueType.FLOAT32,
        supported_models=THREE_PHASE_MODELS,
        unit="%",
        precision=2,
        enabled_by_default=False,
    ),
    _sensor(
        key="voltage_l3_thd",
        name="Voltage L3 THD",
        address=0x5042,
        value_type=RegisterValueType.FLOAT32,
        supported_models=THREE_PHASE_MODELS,
        unit="%",
        precision=2,
        enabled_by_default=False,
    ),
    _sensor(
        key="current_l1_thd",
        name="Current L1 THD",
        address=0x5044,
        value_type=RegisterValueType.FLOAT32,
        supported_models=THREE_PHASE_MODELS,
        unit="%",
        precision=2,
        enabled_by_default=False,
    ),
    _sensor(
        key="current_l2_thd",
        name="Current L2 THD",
        address=0x5046,
        value_type=RegisterValueType.FLOAT32,
        supported_models=THREE_PHASE_MODELS,
        unit="%",
        precision=2,
        enabled_by_default=False,
    ),
    _sensor(
        key="current_l3_thd",
        name="Current L3 THD",
        address=0x5048,
        value_type=RegisterValueType.FLOAT32,
        supported_models=THREE_PHASE_MODELS,
        unit="%",
        precision=2,
        enabled_by_default=False,
    ),
)


def _energy_sensor(
    *,
    key: str,
    name: str,
    address: int,
    value_type: RegisterValueType,
    supported_models: frozenset[str],
    unit: str,
    register_unit: str,
    state_class: str = "total_increasing",
    device_class: str | None = None,
    enabled_by_default: bool = False,
    entity_category: str | None = None,
) -> MeterSensorDescription:
    """Build one GROW energy register description."""
    return MeterSensorDescription(
        key=key,
        name=name,
        register_type=RegisterType.HOLDING,
        address=address,
        count=_count_for(value_type),
        value_type=value_type,
        scale=0.001,
        supported_models=supported_models,
        native_unit_of_measurement=unit,
        device_class=device_class,
        state_class=state_class,
        suggested_display_precision=3,
        entity_registry_enabled_default=enabled_by_default,
        entity_category=entity_category,
        register_unit=register_unit,
        register_format=RegisterFormatType.DEC,
    )


def _active_energy_sensor(
    *,
    key: str,
    name: str,
    address: int,
    value_type: RegisterValueType,
    supported_models: frozenset[str] = ALL_MODELS,
    state_class: str = "total_increasing",
    enabled_by_default: bool = False,
) -> MeterSensorDescription:
    """Build one active-energy register description."""
    return _energy_sensor(
        key=key,
        name=name,
        address=address,
        value_type=value_type,
        supported_models=supported_models,
        unit="kWh",
        register_unit="Wh",
        state_class=state_class,
        device_class="energy",
        enabled_by_default=enabled_by_default,
    )


def _reactive_energy_sensor(
    *,
    key: str,
    name: str,
    address: int,
    value_type: RegisterValueType,
    supported_models: frozenset[str] = ALL_MODELS,
) -> MeterSensorDescription:
    """Build one disabled-by-default reactive-energy register description."""
    return _energy_sensor(
        key=key,
        name=name,
        address=address,
        value_type=value_type,
        supported_models=supported_models,
        unit="kvarh",
        register_unit="varh",
    )


def _apparent_energy_sensor(
    *,
    key: str,
    name: str,
    address: int,
    value_type: RegisterValueType,
    supported_models: frozenset[str] = ALL_MODELS,
) -> MeterSensorDescription:
    """Build one disabled-by-default apparent-energy register description."""
    return _energy_sensor(
        key=key,
        name=name,
        address=address,
        value_type=value_type,
        supported_models=supported_models,
        unit="kVAh",
        register_unit="VAh",
    )


def _resettable_energy_sensor(
    *,
    key: str,
    name: str,
    address: int,
    supported_models: frozenset[str] = ALL_MODELS,
) -> MeterSensorDescription:
    """Build one disabled diagnostic resettable energy counter."""
    return _energy_sensor(
        key=key,
        name=name,
        address=address,
        value_type=RegisterValueType.INT32,
        supported_models=supported_models,
        unit="kWh",
        register_unit="Wh",
        state_class="total",
        device_class="energy",
        entity_category="diagnostic",
    )


GROW_ENERGY_MEASUREMENT_SENSORS: tuple[MeterSensorDescription, ...] = (
    _active_energy_sensor(
        key="active_energy_total",
        name="Active Energy Total",
        address=0x6000,
        value_type=RegisterValueType.INT32,
        state_class="total",
    ),
    _active_energy_sensor(
        key="active_energy_t1",
        name="Active Energy T1",
        address=0x6002,
        value_type=RegisterValueType.INT32,
    ),
    _active_energy_sensor(
        key="active_energy_t2",
        name="Active Energy T2",
        address=0x6004,
        value_type=RegisterValueType.INT32,
    ),
    _active_energy_sensor(
        key="active_energy_l1",
        name="Active Energy L1",
        address=0x6006,
        value_type=RegisterValueType.INT32,
        supported_models=THREE_PHASE_MODELS,
        state_class="total",
    ),
    _active_energy_sensor(
        key="active_energy_l2",
        name="Active Energy L2",
        address=0x6008,
        value_type=RegisterValueType.INT32,
        supported_models=THREE_PHASE_MODELS,
        state_class="total",
    ),
    _active_energy_sensor(
        key="active_energy_l3",
        name="Active Energy L3",
        address=0x600A,
        value_type=RegisterValueType.INT32,
        supported_models=THREE_PHASE_MODELS,
        state_class="total",
    ),
    _active_energy_sensor(
        key="active_energy_import_total",
        name="Active Energy Import Total",
        address=0x600C,
        value_type=RegisterValueType.UINT32,
        enabled_by_default=True,
    ),
    _active_energy_sensor(
        key="active_energy_import_t1",
        name="Active Energy Import T1",
        address=0x600E,
        value_type=RegisterValueType.UINT32,
    ),
    _active_energy_sensor(
        key="active_energy_import_t2",
        name="Active Energy Import T2",
        address=0x6010,
        value_type=RegisterValueType.UINT32,
    ),
    _active_energy_sensor(
        key="active_energy_import_l1",
        name="Active Energy Import L1",
        address=0x6012,
        value_type=RegisterValueType.UINT32,
        supported_models=THREE_PHASE_MODELS,
        enabled_by_default=True,
    ),
    _active_energy_sensor(
        key="active_energy_import_l2",
        name="Active Energy Import L2",
        address=0x6014,
        value_type=RegisterValueType.UINT32,
        supported_models=THREE_PHASE_MODELS,
        enabled_by_default=True,
    ),
    _active_energy_sensor(
        key="active_energy_import_l3",
        name="Active Energy Import L3",
        address=0x6016,
        value_type=RegisterValueType.UINT32,
        supported_models=THREE_PHASE_MODELS,
        enabled_by_default=True,
    ),
    _active_energy_sensor(
        key="active_energy_export_total",
        name="Active Energy Export Total",
        address=0x6018,
        value_type=RegisterValueType.UINT32,
        enabled_by_default=True,
    ),
    _active_energy_sensor(
        key="active_energy_export_t1",
        name="Active Energy Export T1",
        address=0x601A,
        value_type=RegisterValueType.UINT32,
    ),
    _active_energy_sensor(
        key="active_energy_export_t2",
        name="Active Energy Export T2",
        address=0x601C,
        value_type=RegisterValueType.UINT32,
    ),
    _active_energy_sensor(
        key="active_energy_export_l1",
        name="Active Energy Export L1",
        address=0x601E,
        value_type=RegisterValueType.UINT32,
        supported_models=THREE_PHASE_MODELS,
        enabled_by_default=True,
    ),
    _active_energy_sensor(
        key="active_energy_export_l2",
        name="Active Energy Export L2",
        address=0x6020,
        value_type=RegisterValueType.UINT32,
        supported_models=THREE_PHASE_MODELS,
        enabled_by_default=True,
    ),
    _active_energy_sensor(
        key="active_energy_export_l3",
        name="Active Energy Export L3",
        address=0x6022,
        value_type=RegisterValueType.UINT32,
        supported_models=THREE_PHASE_MODELS,
        enabled_by_default=True,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_total",
        name="Reactive Energy Total",
        address=0x6024,
        value_type=RegisterValueType.INT32,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_t1",
        name="Reactive Energy T1",
        address=0x6026,
        value_type=RegisterValueType.INT32,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_t2",
        name="Reactive Energy T2",
        address=0x6028,
        value_type=RegisterValueType.INT32,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_l1",
        name="Reactive Energy L1",
        address=0x602A,
        value_type=RegisterValueType.INT32,
        supported_models=THREE_PHASE_MODELS,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_l2",
        name="Reactive Energy L2",
        address=0x602C,
        value_type=RegisterValueType.INT32,
        supported_models=THREE_PHASE_MODELS,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_l3",
        name="Reactive Energy L3",
        address=0x602E,
        value_type=RegisterValueType.INT32,
        supported_models=THREE_PHASE_MODELS,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_import_total",
        name="Reactive Energy Import Total",
        address=0x6030,
        value_type=RegisterValueType.UINT32,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_import_t1",
        name="Reactive Energy Import T1",
        address=0x6032,
        value_type=RegisterValueType.UINT32,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_import_t2",
        name="Reactive Energy Import T2",
        address=0x6034,
        value_type=RegisterValueType.UINT32,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_import_l1",
        name="Reactive Energy Import L1",
        address=0x6036,
        value_type=RegisterValueType.UINT32,
        supported_models=THREE_PHASE_MODELS,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_import_l2",
        name="Reactive Energy Import L2",
        address=0x6038,
        value_type=RegisterValueType.UINT32,
        supported_models=THREE_PHASE_MODELS,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_import_l3",
        name="Reactive Energy Import L3",
        address=0x603A,
        value_type=RegisterValueType.UINT32,
        supported_models=THREE_PHASE_MODELS,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_export_total",
        name="Reactive Energy Export Total",
        address=0x603C,
        value_type=RegisterValueType.UINT32,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_export_t1",
        name="Reactive Energy Export T1",
        address=0x603E,
        value_type=RegisterValueType.UINT32,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_export_t2",
        name="Reactive Energy Export T2",
        address=0x6040,
        value_type=RegisterValueType.UINT32,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_export_l1",
        name="Reactive Energy Export L1",
        address=0x6042,
        value_type=RegisterValueType.UINT32,
        supported_models=THREE_PHASE_MODELS,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_export_l2",
        name="Reactive Energy Export L2",
        address=0x6044,
        value_type=RegisterValueType.UINT32,
        supported_models=THREE_PHASE_MODELS,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_export_l3",
        name="Reactive Energy Export L3",
        address=0x6046,
        value_type=RegisterValueType.UINT32,
        supported_models=THREE_PHASE_MODELS,
    ),
    _resettable_energy_sensor(
        key="resettable_day_counter_total",
        name="Resettable Day Counter Total",
        address=0x6049,
    ),
    _active_energy_sensor(
        key="active_energy_t3",
        name="Active Energy T3",
        address=0x604B,
        value_type=RegisterValueType.INT32,
    ),
    _active_energy_sensor(
        key="active_energy_t4",
        name="Active Energy T4",
        address=0x604D,
        value_type=RegisterValueType.INT32,
    ),
    _active_energy_sensor(
        key="active_energy_import_t3",
        name="Active Energy Import T3",
        address=0x604F,
        value_type=RegisterValueType.INT32,
    ),
    _active_energy_sensor(
        key="active_energy_import_t4",
        name="Active Energy Import T4",
        address=0x6051,
        value_type=RegisterValueType.INT32,
    ),
    _active_energy_sensor(
        key="active_energy_export_t3",
        name="Active Energy Export T3",
        address=0x6053,
        value_type=RegisterValueType.INT32,
    ),
    _active_energy_sensor(
        key="active_energy_export_t4",
        name="Active Energy Export T4",
        address=0x6055,
        value_type=RegisterValueType.INT32,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_t3",
        name="Reactive Energy T3",
        address=0x6057,
        value_type=RegisterValueType.INT32,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_t4",
        name="Reactive Energy T4",
        address=0x6059,
        value_type=RegisterValueType.INT32,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_import_t3",
        name="Reactive Energy Import T3",
        address=0x605B,
        value_type=RegisterValueType.INT32,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_import_t4",
        name="Reactive Energy Import T4",
        address=0x605D,
        value_type=RegisterValueType.INT32,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_export_t3",
        name="Reactive Energy Export T3",
        address=0x605F,
        value_type=RegisterValueType.INT32,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_export_t4",
        name="Reactive Energy Export T4",
        address=0x6061,
        value_type=RegisterValueType.INT32,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_q1_total",
        name="Reactive Energy Q1 Total",
        address=0x6063,
        value_type=RegisterValueType.INT32,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_q1_t1",
        name="Reactive Energy Q1 T1",
        address=0x6065,
        value_type=RegisterValueType.INT32,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_q1_t2",
        name="Reactive Energy Q1 T2",
        address=0x6067,
        value_type=RegisterValueType.INT32,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_q1_t3",
        name="Reactive Energy Q1 T3",
        address=0x6069,
        value_type=RegisterValueType.INT32,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_q1_t4",
        name="Reactive Energy Q1 T4",
        address=0x606B,
        value_type=RegisterValueType.INT32,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_q2_total",
        name="Reactive Energy Q2 Total",
        address=0x606D,
        value_type=RegisterValueType.INT32,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_q2_t1",
        name="Reactive Energy Q2 T1",
        address=0x606F,
        value_type=RegisterValueType.INT32,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_q2_t2",
        name="Reactive Energy Q2 T2",
        address=0x6071,
        value_type=RegisterValueType.INT32,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_q2_t3",
        name="Reactive Energy Q2 T3",
        address=0x6073,
        value_type=RegisterValueType.INT32,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_q2_t4",
        name="Reactive Energy Q2 T4",
        address=0x6075,
        value_type=RegisterValueType.INT32,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_q3_total",
        name="Reactive Energy Q3 Total",
        address=0x6077,
        value_type=RegisterValueType.INT32,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_q3_t1",
        name="Reactive Energy Q3 T1",
        address=0x6079,
        value_type=RegisterValueType.INT32,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_q3_t2",
        name="Reactive Energy Q3 T2",
        address=0x607B,
        value_type=RegisterValueType.INT32,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_q3_t3",
        name="Reactive Energy Q3 T3",
        address=0x607D,
        value_type=RegisterValueType.INT32,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_q3_t4",
        name="Reactive Energy Q3 T4",
        address=0x607F,
        value_type=RegisterValueType.INT32,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_q4_total",
        name="Reactive Energy Q4 Total",
        address=0x6081,
        value_type=RegisterValueType.INT32,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_q4_t1",
        name="Reactive Energy Q4 T1",
        address=0x6083,
        value_type=RegisterValueType.INT32,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_q4_t2",
        name="Reactive Energy Q4 T2",
        address=0x6085,
        value_type=RegisterValueType.INT32,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_q4_t3",
        name="Reactive Energy Q4 T3",
        address=0x6087,
        value_type=RegisterValueType.INT32,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_q4_t4",
        name="Reactive Energy Q4 T4",
        address=0x6089,
        value_type=RegisterValueType.INT32,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_q1_l1",
        name="Reactive Energy Q1 L1",
        address=0x6091,
        value_type=RegisterValueType.INT32,
        supported_models=THREE_PHASE_MODELS,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_q1_l2",
        name="Reactive Energy Q1 L2",
        address=0x6093,
        value_type=RegisterValueType.INT32,
        supported_models=THREE_PHASE_MODELS,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_q1_l3",
        name="Reactive Energy Q1 L3",
        address=0x6095,
        value_type=RegisterValueType.INT32,
        supported_models=THREE_PHASE_MODELS,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_q2_l1",
        name="Reactive Energy Q2 L1",
        address=0x6097,
        value_type=RegisterValueType.INT32,
        supported_models=THREE_PHASE_MODELS,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_q2_l2",
        name="Reactive Energy Q2 L2",
        address=0x6099,
        value_type=RegisterValueType.INT32,
        supported_models=THREE_PHASE_MODELS,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_q2_l3",
        name="Reactive Energy Q2 L3",
        address=0x609B,
        value_type=RegisterValueType.INT32,
        supported_models=THREE_PHASE_MODELS,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_q3_l1",
        name="Reactive Energy Q3 L1",
        address=0x609D,
        value_type=RegisterValueType.INT32,
        supported_models=THREE_PHASE_MODELS,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_q3_l2",
        name="Reactive Energy Q3 L2",
        address=0x609F,
        value_type=RegisterValueType.INT32,
        supported_models=THREE_PHASE_MODELS,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_q3_l3",
        name="Reactive Energy Q3 L3",
        address=0x60A1,
        value_type=RegisterValueType.INT32,
        supported_models=THREE_PHASE_MODELS,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_q4_l1",
        name="Reactive Energy Q4 L1",
        address=0x60A3,
        value_type=RegisterValueType.INT32,
        supported_models=THREE_PHASE_MODELS,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_q4_l2",
        name="Reactive Energy Q4 L2",
        address=0x60A5,
        value_type=RegisterValueType.INT32,
        supported_models=THREE_PHASE_MODELS,
    ),
    _reactive_energy_sensor(
        key="reactive_energy_q4_l3",
        name="Reactive Energy Q4 L3",
        address=0x60A7,
        value_type=RegisterValueType.INT32,
        supported_models=THREE_PHASE_MODELS,
    ),
    _resettable_energy_sensor(
        key="resettable_day_counter_l1",
        name="Resettable Day Counter L1",
        address=0x60AB,
        supported_models=THREE_PHASE_MODELS,
    ),
    _resettable_energy_sensor(
        key="resettable_day_counter_l2",
        name="Resettable Day Counter L2",
        address=0x60AD,
        supported_models=THREE_PHASE_MODELS,
    ),
    _resettable_energy_sensor(
        key="resettable_day_counter_l3",
        name="Resettable Day Counter L3",
        address=0x60AF,
        supported_models=THREE_PHASE_MODELS,
    ),
    _apparent_energy_sensor(
        key="apparent_energy_total",
        name="Apparent Energy Total",
        address=0x60B9,
        value_type=RegisterValueType.INT32,
    ),
    _apparent_energy_sensor(
        key="apparent_energy_t1",
        name="Apparent Energy T1",
        address=0x60BB,
        value_type=RegisterValueType.INT32,
    ),
    _apparent_energy_sensor(
        key="apparent_energy_t2",
        name="Apparent Energy T2",
        address=0x60BD,
        value_type=RegisterValueType.INT32,
    ),
    _apparent_energy_sensor(
        key="apparent_energy_l1",
        name="Apparent Energy L1",
        address=0x60BF,
        value_type=RegisterValueType.INT32,
        supported_models=THREE_PHASE_MODELS,
    ),
    _apparent_energy_sensor(
        key="apparent_energy_l2",
        name="Apparent Energy L2",
        address=0x6101,
        value_type=RegisterValueType.INT32,
        supported_models=THREE_PHASE_MODELS,
    ),
    _apparent_energy_sensor(
        key="apparent_energy_l3",
        name="Apparent Energy L3",
        address=0x6103,
        value_type=RegisterValueType.INT32,
        supported_models=THREE_PHASE_MODELS,
    ),
    _apparent_energy_sensor(
        key="apparent_energy_import_total",
        name="Apparent Energy Import Total",
        address=0x6105,
        value_type=RegisterValueType.UINT32,
    ),
    _apparent_energy_sensor(
        key="apparent_energy_import_t1",
        name="Apparent Energy Import T1",
        address=0x6107,
        value_type=RegisterValueType.UINT32,
    ),
    _apparent_energy_sensor(
        key="apparent_energy_import_t2",
        name="Apparent Energy Import T2",
        address=0x6109,
        value_type=RegisterValueType.UINT32,
    ),
    _apparent_energy_sensor(
        key="apparent_energy_import_l1",
        name="Apparent Energy Import L1",
        address=0x610B,
        value_type=RegisterValueType.UINT32,
        supported_models=THREE_PHASE_MODELS,
    ),
    _apparent_energy_sensor(
        key="apparent_energy_import_l2",
        name="Apparent Energy Import L2",
        address=0x610D,
        value_type=RegisterValueType.UINT32,
        supported_models=THREE_PHASE_MODELS,
    ),
    _apparent_energy_sensor(
        key="apparent_energy_import_l3",
        name="Apparent Energy Import L3",
        address=0x610F,
        value_type=RegisterValueType.UINT32,
        supported_models=THREE_PHASE_MODELS,
    ),
    _apparent_energy_sensor(
        key="apparent_energy_export_total",
        name="Apparent Energy Export Total",
        address=0x6111,
        value_type=RegisterValueType.UINT32,
    ),
    _apparent_energy_sensor(
        key="apparent_energy_export_t1",
        name="Apparent Energy Export T1",
        address=0x6113,
        value_type=RegisterValueType.UINT32,
    ),
    _apparent_energy_sensor(
        key="apparent_energy_export_t2",
        name="Apparent Energy Export T2",
        address=0x6115,
        value_type=RegisterValueType.UINT32,
    ),
    _apparent_energy_sensor(
        key="apparent_energy_export_l1",
        name="Apparent Energy Export L1",
        address=0x6117,
        value_type=RegisterValueType.UINT32,
        supported_models=THREE_PHASE_MODELS,
    ),
    _apparent_energy_sensor(
        key="apparent_energy_export_l2",
        name="Apparent Energy Export L2",
        address=0x6119,
        value_type=RegisterValueType.UINT32,
        supported_models=THREE_PHASE_MODELS,
    ),
    _apparent_energy_sensor(
        key="apparent_energy_export_l3",
        name="Apparent Energy Export L3",
        address=0x611B,
        value_type=RegisterValueType.UINT32,
        supported_models=THREE_PHASE_MODELS,
    ),
    _apparent_energy_sensor(
        key="apparent_energy_t3",
        name="Apparent Energy T3",
        address=0x611D,
        value_type=RegisterValueType.INT32,
    ),
    _apparent_energy_sensor(
        key="apparent_energy_t4",
        name="Apparent Energy T4",
        address=0x611F,
        value_type=RegisterValueType.INT32,
    ),
    _apparent_energy_sensor(
        key="apparent_energy_import_t3",
        name="Apparent Energy Import T3",
        address=0x6121,
        value_type=RegisterValueType.UINT32,
    ),
    _apparent_energy_sensor(
        key="apparent_energy_import_t4",
        name="Apparent Energy Import T4",
        address=0x6123,
        value_type=RegisterValueType.UINT32,
    ),
    _apparent_energy_sensor(
        key="apparent_energy_export_t3",
        name="Apparent Energy Export T3",
        address=0x6125,
        value_type=RegisterValueType.UINT32,
    ),
    _apparent_energy_sensor(
        key="apparent_energy_export_t4",
        name="Apparent Energy Export T4",
        address=0x6127,
        value_type=RegisterValueType.UINT32,
    ),
    _resettable_energy_sensor(
        key="previous_resettable_day_counter",
        name="Previous Resettable Day Counter",
        address=0x6200,
    ),
)

GROW_ENERGY_DIAGNOSTIC_SENSORS: tuple[MeterSensorDescription, ...] = (
    MeterSensorDescription(
        key="active_tariff",
        name="Active Tariff",
        register_type=RegisterType.HOLDING,
        address=0x6048,
        count=1,
        value_type=RegisterValueType.UINT16,
        supported_models=ALL_MODELS,
        state_class=None,
        entity_category="diagnostic",
        options=GROW_TARIFF_OPTIONS,
        register_format=RegisterFormatType.ENUM,
    ),
)

GROW_MEASUREMENT_SENSORS += GROW_ENERGY_MEASUREMENT_SENSORS


GROW_DIAGNOSTIC_SENSORS: tuple[MeterSensorDescription, ...] = (
    _diagnostic_sensor(
        key="serial_number",
        name="Serial Number",
        address=0x4000,
        value_type=RegisterValueType.BCD32,
        supported_models=ALL_MODELS,
        register_format=RegisterFormatType.HEX,
    ),
    _diagnostic_sensor(
        key="meter_code",
        name="Meter Code",
        address=0x4002,
        value_type=RegisterValueType.HEX16,
        supported_models=ALL_MODELS,
    ),
    _diagnostic_sensor(
        key="legal_software_version",
        name="Legal Software Version",
        address=0x4005,
        value_type=RegisterValueType.FLOAT32,
        supported_models=ALL_MODELS,
    ),
    _diagnostic_sensor(
        key="non_legal_software_version",
        name="Non-Legal Software Version",
        address=0x4007,
        value_type=RegisterValueType.FLOAT32,
        supported_models=ALL_MODELS,
    ),
    _diagnostic_sensor(
        key="hardware_version",
        name="Hardware Version",
        address=0x4009,
        value_type=RegisterValueType.FLOAT32,
        supported_models=ALL_MODELS,
        precision=4,
    ),
    _diagnostic_sensor(
        key="error_code",
        name="Error Code",
        address=0x4015,
        value_type=RegisterValueType.HEX16,
        supported_models=ALL_MODELS,
    ),
    _diagnostic_sensor(
        key="legal_software_crc",
        name="Legal Software CRC",
        address=0x401B,
        value_type=RegisterValueType.HEX32,
        supported_models=ALL_MODELS,
        enabled_by_default=False,
    ),
    _diagnostic_sensor(
        key="active_status_word",
        name="Active Status Word",
        address=0x401D,
        value_type=RegisterValueType.HEX32,
        supported_models=ALL_MODELS,
        enabled_by_default=False,
    ),
    _diagnostic_sensor(
        key="non_legal_software_crc",
        name="Non-Legal Software CRC",
        address=0x4023,
        value_type=RegisterValueType.HEX32,
        supported_models=ALL_MODELS,
        enabled_by_default=False,
    ),
    _diagnostic_sensor(
        key="product_code",
        name="Product Code",
        address=0x4025,
        value_type=RegisterValueType.BCD16,
        supported_models=ALL_MODELS,
        register_format=RegisterFormatType.HEX,
    ),
    _diagnostic_sensor(
        key="wifi_support",
        name="Wi-Fi Support",
        address=0x4C06,
        value_type=RegisterValueType.UINT16,
        supported_models=NETWORKED_MODELS,
        options=ENABLE_STATE_OPTIONS,
        register_format=RegisterFormatType.ENUM,
    ),
    _diagnostic_sensor(
        key="bluetooth_mode",
        name="Bluetooth Mode",
        address=0x4C07,
        value_type=RegisterValueType.UINT16,
        supported_models=NETWORKED_MODELS,
        options=BLUETOOTH_MODE_OPTIONS,
        register_format=RegisterFormatType.ENUM,
    ),
    _diagnostic_sensor(
        key="ethernet_support",
        name="Ethernet Support",
        address=0x4C64,
        value_type=RegisterValueType.UINT16,
        supported_models=ETHERNET_MODELS,
        options=SUPPORT_STATE_OPTIONS,
        register_format=RegisterFormatType.ENUM,
    ),
    _diagnostic_sensor(
        key="billing_session_start_energy",
        name="Billing Session Start Energy",
        address=0x1010,
        value_type=RegisterValueType.INT32,
        supported_models=OCMF_MODELS,
        unit="kWh",
        register_unit="Wh",
        device_class="energy",
        scale=0.001,
        precision=3,
        enabled_by_default=False,
    ),
    _diagnostic_sensor(
        key="billing_session_accumulated_energy",
        name="Billing Session Accumulated Energy",
        address=0x1012,
        value_type=RegisterValueType.INT32,
        supported_models=OCMF_MODELS,
        unit="kWh",
        register_unit="Wh",
        device_class="energy",
        scale=0.001,
        precision=3,
        enabled_by_default=False,
    ),
    _diagnostic_sensor(
        key="billing_session_status",
        name="Billing Session Status",
        address=0x1100,
        value_type=RegisterValueType.UINT16,
        supported_models=OCMF_MODELS,
        enabled_by_default=False,
    ),
)


GROW_DIAGNOSTIC_SENSORS += GROW_ENERGY_DIAGNOSTIC_SENSORS


GROW_CONFIG_SENSORS: tuple[MeterSensorDescription, ...] = (
    _config_sensor(
        key="legal_lcd_obis_codes",
        name="Legal LCD OBIS Codes",
        address=0x4C00,
        value_type=RegisterValueType.UINT16,
        supported_models=ALL_MODELS,
        options=ON_OFF_OPTIONS,
        register_format=RegisterFormatType.ENUM,
    ),
    _config_sensor(
        key="legal_lcd_tariff_mode",
        name="Legal LCD Tariff Mode",
        address=0x4C01,
        value_type=RegisterValueType.UINT16,
        supported_models=ALL_MODELS,
        options=LCD_TARIFF_MODE_OPTIONS,
        register_format=RegisterFormatType.ENUM,
    ),
    _config_sensor(
        key="backlight_mode",
        name="Backlight Mode",
        address=0x4C02,
        value_type=RegisterValueType.UINT16,
        supported_models=ALL_MODELS,
        options=BACKLIGHT_MODE_OPTIONS,
        register_format=RegisterFormatType.ENUM,
    ),
    _config_sensor(
        key="backlight_timeout",
        name="Backlight Timeout",
        address=0x4C04,
        value_type=RegisterValueType.UINT16,
        supported_models=ALL_MODELS,
        unit="min",
        register_unit="minutes",
    ),
    _config_sensor(
        key="non_legal_lcd_cycle_time",
        name="Non-Legal LCD Cycle Time",
        address=0x4C05,
        value_type=RegisterValueType.UINT16,
        supported_models=ALL_MODELS,
        unit="s",
        register_unit="seconds",
    ),
    _config_sensor(
        key="backlight_level",
        name="Backlight Level",
        address=0x4171,
        value_type=RegisterValueType.UINT16,
        supported_models=ALL_MODELS,
        options=BACKLIGHT_LEVEL_OPTIONS,
        register_unit="%",
    ),
    _config_sensor(
        key="lcd_orientation",
        name="LCD Orientation",
        address=0x4032,
        value_type=RegisterValueType.UINT16,
        supported_models=ALL_MODELS,
        options=LCD_ORIENTATION_OPTIONS,
        register_format=RegisterFormatType.ENUM,
    ),
    _config_sensor(
        key="non_legal_lcd_obis_codes",
        name="Non-Legal LCD OBIS Codes",
        address=0x4033,
        value_type=RegisterValueType.UINT16,
        supported_models=ALL_MODELS,
        options=ON_OFF_OPTIONS,
        register_format=RegisterFormatType.ENUM,
    ),
    _config_sensor(
        key="legal_lcd_cycle_time",
        name="Legal LCD Cycle Time",
        address=0x4010,
        value_type=RegisterValueType.UINT16,
        supported_models=ALL_MODELS,
        unit="s",
        register_unit="seconds",
    ),
)


PRO_MEASUREMENT_SENSORS: tuple[MeterSensorDescription, ...] = (
    _sensor(
        key="voltage",
        name="Voltage",
        address=0x5000,
        value_type=RegisterValueType.FLOAT32,
        supported_models=PRO_SINGLE_PHASE_MODELS,
        unit="V",
        device_class="voltage",
        precision=1,
    ),
    _sensor(
        key="grid_frequency",
        name="Grid Frequency",
        address=0x5008,
        value_type=RegisterValueType.FLOAT32,
        supported_models=PRO_ALL_MODELS,
        unit="Hz",
        device_class="frequency",
        precision=2,
    ),
    _sensor(
        key="current",
        name="Current",
        address=0x500A,
        value_type=RegisterValueType.FLOAT32,
        supported_models=PRO_SINGLE_PHASE_MODELS,
        unit="A",
        device_class="current",
        precision=2,
    ),
    _sensor(
        key="total_active_power",
        name="Total Active Power",
        address=0x5012,
        value_type=RegisterValueType.FLOAT32,
        supported_models=PRO_ALL_MODELS,
        unit="kW",
        device_class="power",
        precision=3,
    ),
    _sensor(
        key="total_reactive_power",
        name="Total Reactive Power",
        address=0x501A,
        value_type=RegisterValueType.FLOAT32,
        supported_models=PRO_ALL_MODELS,
        unit="kvar",
        device_class="reactive_power",
        precision=3,
    ),
    _sensor(
        key="total_apparent_power",
        name="Total Apparent Power",
        address=0x5022,
        value_type=RegisterValueType.FLOAT32,
        supported_models=PRO_ALL_MODELS,
        unit="kVA",
        device_class="apparent_power",
        precision=3,
    ),
    _sensor(
        key="power_factor",
        name="Power Factor",
        address=0x502A,
        value_type=RegisterValueType.FLOAT32,
        supported_models=PRO_ALL_MODELS,
        device_class="power_factor",
        precision=3,
    ),
    _sensor(
        key="total_active_energy",
        name="Total Active Energy",
        address=0x6000,
        value_type=RegisterValueType.FLOAT32,
        supported_models=PRO_ALL_MODELS,
        unit="kWh",
        device_class="energy",
        state_class="total",
        precision=3,
    ),
    _sensor(
        key="forward_active_energy",
        name="Forward Active Energy",
        address=0x600C,
        value_type=RegisterValueType.FLOAT32,
        supported_models=PRO_ALL_MODELS,
        unit="kWh",
        device_class="energy",
        state_class="total_increasing",
        precision=3,
    ),
    _sensor(
        key="reverse_active_energy",
        name="Reverse Active Energy",
        address=0x6018,
        value_type=RegisterValueType.FLOAT32,
        supported_models=PRO_ALL_MODELS,
        unit="kWh",
        device_class="energy",
        state_class="total_increasing",
        precision=3,
    ),
    _sensor(
        key="total_reactive_energy",
        name="Total Reactive Energy",
        address=0x6024,
        value_type=RegisterValueType.FLOAT32,
        supported_models=PRO_ALL_MODELS,
        unit="kvarh",
        device_class="reactive_energy",
        state_class="total",
        precision=3,
        enabled_by_default=False,
    ),
    _sensor(
        key="forward_reactive_energy",
        name="Forward Reactive Energy",
        address=0x6030,
        value_type=RegisterValueType.FLOAT32,
        supported_models=PRO_ALL_MODELS,
        unit="kvarh",
        device_class="reactive_energy",
        state_class="total_increasing",
        precision=3,
        enabled_by_default=False,
    ),
    _sensor(
        key="reverse_reactive_energy",
        name="Reverse Reactive Energy",
        address=0x603C,
        value_type=RegisterValueType.FLOAT32,
        supported_models=PRO_ALL_MODELS,
        unit="kvarh",
        device_class="reactive_energy",
        state_class="total_increasing",
        precision=3,
        enabled_by_default=False,
    ),
    _sensor(
        key="voltage_l1",
        name="Voltage L1",
        address=0x5002,
        value_type=RegisterValueType.FLOAT32,
        supported_models=PRO_THREE_PHASE_MODELS,
        unit="V",
        device_class="voltage",
        precision=1,
    ),
    _sensor(
        key="voltage_l2",
        name="Voltage L2",
        address=0x5004,
        value_type=RegisterValueType.FLOAT32,
        supported_models=PRO_THREE_PHASE_MODELS,
        unit="V",
        device_class="voltage",
        precision=1,
    ),
    _sensor(
        key="voltage_l3",
        name="Voltage L3",
        address=0x5006,
        value_type=RegisterValueType.FLOAT32,
        supported_models=PRO_THREE_PHASE_MODELS,
        unit="V",
        device_class="voltage",
        precision=1,
    ),
    _sensor(
        key="current_l1",
        name="Current L1",
        address=0x500C,
        value_type=RegisterValueType.FLOAT32,
        supported_models=PRO_THREE_PHASE_MODELS,
        unit="A",
        device_class="current",
        precision=2,
    ),
    _sensor(
        key="current_l2",
        name="Current L2",
        address=0x500E,
        value_type=RegisterValueType.FLOAT32,
        supported_models=PRO_THREE_PHASE_MODELS,
        unit="A",
        device_class="current",
        precision=2,
    ),
    _sensor(
        key="current_l3",
        name="Current L3",
        address=0x5010,
        value_type=RegisterValueType.FLOAT32,
        supported_models=PRO_THREE_PHASE_MODELS,
        unit="A",
        device_class="current",
        precision=2,
    ),
    _sensor(
        key="active_power_l1",
        name="Active Power L1",
        address=0x5014,
        value_type=RegisterValueType.FLOAT32,
        supported_models=PRO_THREE_PHASE_MODELS,
        unit="kW",
        device_class="power",
        precision=3,
        enabled_by_default=False,
    ),
    _sensor(
        key="active_power_l2",
        name="Active Power L2",
        address=0x5016,
        value_type=RegisterValueType.FLOAT32,
        supported_models=PRO_THREE_PHASE_MODELS,
        unit="kW",
        device_class="power",
        precision=3,
        enabled_by_default=False,
    ),
    _sensor(
        key="active_power_l3",
        name="Active Power L3",
        address=0x5018,
        value_type=RegisterValueType.FLOAT32,
        supported_models=PRO_THREE_PHASE_MODELS,
        unit="kW",
        device_class="power",
        precision=3,
        enabled_by_default=False,
    ),
    _sensor(
        key="reactive_power_l1",
        name="Reactive Power L1",
        address=0x501C,
        value_type=RegisterValueType.FLOAT32,
        supported_models=PRO_THREE_PHASE_MODELS,
        unit="kvar",
        device_class="reactive_power",
        precision=3,
        enabled_by_default=False,
    ),
    _sensor(
        key="reactive_power_l2",
        name="Reactive Power L2",
        address=0x501E,
        value_type=RegisterValueType.FLOAT32,
        supported_models=PRO_THREE_PHASE_MODELS,
        unit="kvar",
        device_class="reactive_power",
        precision=3,
        enabled_by_default=False,
    ),
    _sensor(
        key="reactive_power_l3",
        name="Reactive Power L3",
        address=0x5020,
        value_type=RegisterValueType.FLOAT32,
        supported_models=PRO_THREE_PHASE_MODELS,
        unit="kvar",
        device_class="reactive_power",
        precision=3,
        enabled_by_default=False,
    ),
    _sensor(
        key="apparent_power_l1",
        name="Apparent Power L1",
        address=0x5024,
        value_type=RegisterValueType.FLOAT32,
        supported_models=PRO_THREE_PHASE_MODELS,
        unit="kVA",
        device_class="apparent_power",
        precision=3,
        enabled_by_default=False,
    ),
    _sensor(
        key="apparent_power_l2",
        name="Apparent Power L2",
        address=0x5026,
        value_type=RegisterValueType.FLOAT32,
        supported_models=PRO_THREE_PHASE_MODELS,
        unit="kVA",
        device_class="apparent_power",
        precision=3,
        enabled_by_default=False,
    ),
    _sensor(
        key="apparent_power_l3",
        name="Apparent Power L3",
        address=0x5028,
        value_type=RegisterValueType.FLOAT32,
        supported_models=PRO_THREE_PHASE_MODELS,
        unit="kVA",
        device_class="apparent_power",
        precision=3,
        enabled_by_default=False,
    ),
    _sensor(
        key="power_factor_l1",
        name="Power Factor L1",
        address=0x502C,
        value_type=RegisterValueType.FLOAT32,
        supported_models=PRO_THREE_PHASE_MODELS,
        precision=3,
        enabled_by_default=False,
    ),
    _sensor(
        key="power_factor_l2",
        name="Power Factor L2",
        address=0x502E,
        value_type=RegisterValueType.FLOAT32,
        supported_models=PRO_THREE_PHASE_MODELS,
        precision=3,
        enabled_by_default=False,
    ),
    _sensor(
        key="power_factor_l3",
        name="Power Factor L3",
        address=0x5030,
        value_type=RegisterValueType.FLOAT32,
        supported_models=PRO_THREE_PHASE_MODELS,
        precision=3,
        enabled_by_default=False,
    ),
)


PRO_DIAGNOSTIC_SENSORS: tuple[MeterSensorDescription, ...] = (
    _diagnostic_sensor(
        key="serial_number",
        name="Serial Number",
        address=0x4000,
        value_type=RegisterValueType.HEX32,
        supported_models=PRO_ALL_MODELS,
    ),
    _diagnostic_sensor(
        key="meter_code",
        name="Meter Code",
        address=0x4002,
        value_type=RegisterValueType.HEX16,
        supported_models=PRO_ALL_MODELS,
    ),
    _diagnostic_sensor(
        key="protocol_version",
        name="Protocol Version",
        address=0x4005,
        value_type=RegisterValueType.FLOAT32,
        supported_models=PRO_ALL_MODELS,
    ),
    _diagnostic_sensor(
        key="software_version",
        name="Software Version",
        address=0x4007,
        value_type=RegisterValueType.FLOAT32,
        supported_models=PRO_ALL_MODELS,
    ),
    _diagnostic_sensor(
        key="hardware_version",
        name="Hardware Version",
        address=0x4009,
        value_type=RegisterValueType.FLOAT32,
        supported_models=PRO_ALL_MODELS,
        precision=4,
    ),
    _diagnostic_sensor(
        key="meter_amps",
        name="Meter Amps",
        address=0x400B,
        value_type=RegisterValueType.INT16,
        supported_models=PRO_ALL_MODELS,
        unit="A",
    ),
    _diagnostic_sensor(
        key="error_code",
        name="Error Code",
        address=0x4015,
        value_type=RegisterValueType.INT16,
        supported_models=PRO_ALL_MODELS,
    ),
    _diagnostic_sensor(
        key="power_down_counter",
        name="Power Down Counter",
        address=0x4016,
        value_type=RegisterValueType.INT16,
        supported_models=PRO_ALL_MODELS,
        enabled_by_default=False,
    ),
    _diagnostic_sensor(
        key="present_quadrant",
        name="Present Quadrant",
        address=0x4017,
        value_type=RegisterValueType.INT16,
        supported_models=PRO_ALL_MODELS,
        enabled_by_default=False,
    ),
    _diagnostic_sensor(
        key="checksum",
        name="Checksum",
        address=0x401B,
        value_type=RegisterValueType.HEX32,
        supported_models=PRO_ALL_MODELS,
        enabled_by_default=False,
    ),
    _diagnostic_sensor(
        key="active_status_word",
        name="Active Status Word",
        address=0x401D,
        value_type=RegisterValueType.HEX32,
        supported_models=PRO_ALL_MODELS,
        enabled_by_default=False,
    ),
    _diagnostic_sensor(
        key="ct_mode",
        name="CT Mode",
        address=0x401F,
        value_type=RegisterValueType.INT16,
        supported_models=PRO_CT_MODELS,
        enabled_by_default=False,
    ),
)


PRO_CONFIG_SENSORS: tuple[MeterSensorDescription, ...] = (
    _config_sensor(
        key="modbus_id",
        name="Modbus ID",
        address=0x4003,
        value_type=RegisterValueType.INT16,
        supported_models=PRO_ALL_MODELS,
        register_format=RegisterFormatType.DEC,
    ),
    _config_sensor(
        key="baud_rate",
        name="Baud Rate",
        address=0x4004,
        value_type=RegisterValueType.INT16,
        supported_models=PRO_ALL_MODELS,
        unit="bps",
        register_format=RegisterFormatType.DEC,
    ),
    _config_sensor(
        key="s0_output_rate",
        name="S0 Output Rate",
        address=0x400D,
        value_type=RegisterValueType.FLOAT32,
        supported_models=PRO_ALL_MODELS,
        unit="imp/kWh",
    ),
    _config_sensor(
        key="parity_setting",
        name="Parity Setting",
        address=0x4011,
        value_type=RegisterValueType.INT16,
        supported_models=PRO_ALL_MODELS,
        options=PRO_PARITY_OPTIONS,
        register_format=RegisterFormatType.ENUM,
    ),
    _config_sensor(
        key="tariff",
        name="Tariff",
        address=0x6048,
        value_type=RegisterValueType.INT16,
        supported_models=PRO_ALL_MODELS,
        options=PRO_TARIFF_OPTIONS,
        register_format=RegisterFormatType.ENUM,
    ),
)


def _filter_sensors_for_model(
    sensors: tuple[MeterSensorDescription, ...],
    model_code: str,
) -> tuple[MeterSensorDescription, ...]:
    """Return the sensor descriptions supported by one model."""
    return tuple(
        description
        for description in sensors
        if model_code in description.supported_models
    )


def get_grow_measurement_sensors(model_code: str) -> tuple[MeterSensorDescription, ...]:
    """Return the curated GROW measurement sensor list for a model code."""
    return _filter_sensors_for_model(GROW_MEASUREMENT_SENSORS, model_code)


def get_grow_diagnostic_sensors(model_code: str) -> tuple[MeterSensorDescription, ...]:
    """Return the curated GROW diagnostic sensor list for a model code."""
    return _filter_sensors_for_model(GROW_DIAGNOSTIC_SENSORS, model_code)


def get_grow_config_sensors(model_code: str) -> tuple[MeterSensorDescription, ...]:
    """Return the readable GROW configuration register list for a model code."""
    return _filter_sensors_for_model(GROW_CONFIG_SENSORS, model_code)


def get_pro_measurement_sensors(model_code: str) -> tuple[MeterSensorDescription, ...]:
    """Return the curated PRO measurement sensor list for a model code."""
    return _filter_sensors_for_model(PRO_MEASUREMENT_SENSORS, model_code)


def get_pro_diagnostic_sensors(model_code: str) -> tuple[MeterSensorDescription, ...]:
    """Return the curated PRO diagnostic sensor list for a model code."""
    return _filter_sensors_for_model(PRO_DIAGNOSTIC_SENSORS, model_code)


def get_pro_config_sensors(model_code: str) -> tuple[MeterSensorDescription, ...]:
    """Return the readable PRO configuration register list for a model code."""
    return _filter_sensors_for_model(PRO_CONFIG_SENSORS, model_code)


def _build_profile(
    *,
    family: MeterFamily,
    variant: str,
    title: str,
    model_code: str,
    supported_transports: tuple[TransportType, ...],
    measurement_sensors: tuple[MeterSensorDescription, ...],
    diagnostic_sensors: tuple[MeterSensorDescription, ...],
    config_sensors: tuple[MeterSensorDescription, ...],
) -> MeterProfile:
    """Build a meter profile."""
    return MeterProfile(
        family=family,
        variant=variant,
        title=title,
        model_code=model_code,
        device_model=title,
        supported_transports=supported_transports,
        measurement_sensors=measurement_sensors,
        diagnostic_sensors=diagnostic_sensors,
        config_sensors=config_sensors,
    )


def _build_pro_profile(
    *,
    variant: str,
    title: str,
    model_code: str,
) -> MeterProfile:
    """Build a PRO-family profile that is reachable over a shared Modbus bus."""
    return _build_profile(
        family=MeterFamily.PRO,
        variant=variant,
        title=title,
        model_code=model_code,
        supported_transports=(
            TransportType.SERIAL,
            TransportType.TCP_GATEWAY,
        ),
        measurement_sensors=get_pro_measurement_sensors(model_code),
        diagnostic_sensors=get_pro_diagnostic_sensors(model_code),
        config_sensors=get_pro_config_sensors(model_code),
    )


PROFILES_BY_FAMILY: dict[MeterFamily, dict[str, MeterProfile]] = {
    MeterFamily.GROW: {
        "grow_701": _build_profile(
            family=MeterFamily.GROW,
            variant="grow_701",
            title="GROW 3P4U",
            model_code=MODEL_701,
            supported_transports=(
                TransportType.SERIAL,
                TransportType.TCP_GATEWAY,
                TransportType.BLUETOOTH,
                TransportType.BLUETOOTH_PROXY,
                TransportType.TCP_WIFI,
                TransportType.TCP_ETHERNET,
            ),
            measurement_sensors=get_grow_measurement_sensors(MODEL_701),
            diagnostic_sensors=get_grow_diagnostic_sensors(MODEL_701),
            config_sensors=get_grow_config_sensors(MODEL_701),
        ),
        "grow_750": _build_profile(
            family=MeterFamily.GROW,
            variant="grow_750",
            title="GROW 3P4S",
            model_code=MODEL_750,
            supported_transports=(
                TransportType.SERIAL,
                TransportType.TCP_GATEWAY,
                TransportType.BLUETOOTH,
                TransportType.BLUETOOTH_PROXY,
                TransportType.TCP_WIFI,
                TransportType.TCP_ETHERNET,
            ),
            measurement_sensors=get_grow_measurement_sensors(MODEL_750),
            diagnostic_sensors=get_grow_diagnostic_sensors(MODEL_750),
            config_sensors=get_grow_config_sensors(MODEL_750),
        ),
        "grow_800": _build_profile(
            family=MeterFamily.GROW,
            variant="grow_800",
            title="GROW 1P2U",
            model_code=MODEL_800,
            supported_transports=(
                TransportType.SERIAL,
                TransportType.TCP_GATEWAY,
                TransportType.BLUETOOTH,
                TransportType.BLUETOOTH_PROXY,
                TransportType.TCP_WIFI,
            ),
            measurement_sensors=get_grow_measurement_sensors(MODEL_800),
            diagnostic_sensors=get_grow_diagnostic_sensors(MODEL_800),
            config_sensors=get_grow_config_sensors(MODEL_800),
        ),
        "grow_850": _build_profile(
            family=MeterFamily.GROW,
            variant="grow_850",
            title="GROW 1P1U",
            model_code=MODEL_850,
            supported_transports=(
                TransportType.SERIAL,
                TransportType.TCP_GATEWAY,
            ),
            measurement_sensors=get_grow_measurement_sensors(MODEL_850),
            diagnostic_sensors=get_grow_diagnostic_sensors(MODEL_850),
            config_sensors=get_grow_config_sensors(MODEL_850),
        ),
    },
    MeterFamily.PRO: {
        "pro_1": _build_pro_profile(
            variant="pro_1",
            title="PRO1",
            model_code=MODEL_PRO1,
        ),
        "pro_2": _build_pro_profile(
            variant="pro_2",
            title="PRO2",
            model_code=MODEL_PRO2,
        ),
        "pro_380": _build_pro_profile(
            variant="pro_380",
            title="PRO380",
            model_code=MODEL_PRO380,
        ),
        "pro_380ct": _build_pro_profile(
            variant="pro_380ct",
            title="PRO380CT",
            model_code=MODEL_PRO380CT,
        ),
        "pro_1_solare": _build_pro_profile(
            variant="pro_1_solare",
            title="PRO1 Solare",
            model_code=MODEL_PRO1_SOLARE,
        ),
        "pro_2_solare": _build_pro_profile(
            variant="pro_2_solare",
            title="PRO2 Solare",
            model_code=MODEL_PRO2_SOLARE,
        ),
        "pro_380_solare": _build_pro_profile(
            variant="pro_380_solare",
            title="PRO380 Solare",
            model_code=MODEL_PRO380_SOLARE,
        ),
        "pro_380ct_solare": _build_pro_profile(
            variant="pro_380ct_solare",
            title="PRO380CT Solare",
            model_code=MODEL_PRO380CT_SOLARE,
        ),
        "n_1": _build_pro_profile(
            variant="n_1",
            title="N1",
            model_code=MODEL_N1,
        ),
        "n_380_40a": _build_pro_profile(
            variant="n_380_40a",
            title="N380 40A",
            model_code=MODEL_N380_40A,
        ),
        "n_380ct": _build_pro_profile(
            variant="n_380ct",
            title="N380 CT",
            model_code=MODEL_N380CT,
        ),
    },
}


def get_profile(family: str | MeterFamily, variant: str) -> MeterProfile:
    """Return the configured profile."""
    family_enum = MeterFamily(family)
    return PROFILES_BY_FAMILY[family_enum][variant]


def get_profile_for_variant(variant: str) -> MeterProfile:
    """Return the configured profile for a globally unique variant key."""
    for profiles in PROFILES_BY_FAMILY.values():
        profile = profiles.get(variant)
        if profile is not None:
            return profile
    raise KeyError(f"Unknown meter profile variant: {variant}")


def get_profiles_for_family(family: str | MeterFamily) -> dict[str, MeterProfile]:
    """Return all profiles for a family."""
    return PROFILES_BY_FAMILY[MeterFamily(family)]


def get_supported_families() -> tuple[MeterFamily, ...]:
    """Return families that currently expose at least one selectable profile."""
    return tuple(family for family, profiles in PROFILES_BY_FAMILY.items() if profiles)


def _coerce_error_code(value: str | int | float | None) -> int | None:
    """Normalize a raw meter error code into an integer bitfield."""
    if value is None:
        return None

    if isinstance(value, str):
        normalized = value.strip()
        if not normalized or normalized.lower() in {"unknown", "unavailable", "none"}:
            return None
        if normalized.lower().startswith("0x"):
            normalized = normalized[2:]
        try:
            return int(normalized, 16)
        except ValueError:
            try:
                return int(float(normalized))
            except ValueError:
                return None

    if isinstance(value, float):
        return int(value)

    return int(value)


def decode_grow_error_code(value: str | int | float | None) -> tuple[str, ...]:
    """Decode the GROW error-code bitfield into human-readable messages."""
    code = _coerce_error_code(value)
    if code in (None, 0):
        return ()

    decoded = tuple(message for bit, message in GROW_ERROR_BIT_MESSAGES if code & bit)
    unknown_bits = code & ~_GROW_ERROR_MASK
    if unknown_bits:
        return decoded + (f"unknown error bits {unknown_bits:04X}",)
    return decoded


def format_grow_error_summary(value: str | int | float | None) -> str | None:
    """Return a compact user-facing GROW error summary string."""
    code = _coerce_error_code(value)
    if code is None:
        return None
    if code == 0:
        return "No critical errors"
    return ", ".join(decode_grow_error_code(code))
