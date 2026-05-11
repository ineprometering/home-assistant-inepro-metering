"""Register grouping and decoding helpers for Inepro Metering."""

from __future__ import annotations

from dataclasses import dataclass
import struct

from .const import MAX_REGISTERS_PER_READ
from .models import MeterSensorDescription, RegisterType, RegisterValueType


@dataclass(frozen=True, slots=True)
class RegisterBlock:
    """A contiguous range of registers to read in one call."""

    register_type: RegisterType
    start_address: int
    count: int
    sensors: tuple[MeterSensorDescription, ...]


def build_register_blocks(
    sensors: tuple[MeterSensorDescription, ...],
) -> tuple[RegisterBlock, ...]:
    """Group sensor registers into contiguous Modbus reads."""
    if not sensors:
        return ()

    sorted_sensors = sorted(sensors, key=lambda item: (item.register_type, item.address))
    blocks: list[RegisterBlock] = []

    current_type = sorted_sensors[0].register_type
    current_start = sorted_sensors[0].address
    current_end = sorted_sensors[0].address + sorted_sensors[0].count
    current_sensors: list[MeterSensorDescription] = [sorted_sensors[0]]

    for sensor in sorted_sensors[1:]:
        sensor_end = sensor.address + sensor.count
        can_extend_same_type = sensor.register_type == current_type
        is_contiguous = sensor.address <= current_end
        fits_limit = sensor_end - current_start <= MAX_REGISTERS_PER_READ

        if can_extend_same_type and is_contiguous and fits_limit:
            current_end = max(current_end, sensor_end)
            current_sensors.append(sensor)
            continue

        blocks.append(
            RegisterBlock(
                register_type=current_type,
                start_address=current_start,
                count=current_end - current_start,
                sensors=tuple(current_sensors),
            )
        )
        current_type = sensor.register_type
        current_start = sensor.address
        current_end = sensor_end
        current_sensors = [sensor]

    blocks.append(
        RegisterBlock(
            register_type=current_type,
            start_address=current_start,
            count=current_end - current_start,
            sensors=tuple(current_sensors),
        )
    )
    return tuple(blocks)


def decode_sensor_value(
    sensor: MeterSensorDescription,
    registers: list[int],
) -> str | int | float:
    """Decode raw Modbus registers into a sensor value."""
    if sensor.value_type is RegisterValueType.UINT16:
        value: int | float = registers[0]
    elif sensor.value_type is RegisterValueType.INT16:
        value = struct.unpack(">h", struct.pack(">H", registers[0]))[0]
    elif sensor.value_type is RegisterValueType.BCD16:
        return f"{registers[0]:04X}"
    elif sensor.value_type is RegisterValueType.HEX16:
        return f"{registers[0]:04X}"
    else:
        raw = b"".join(struct.pack(">H", register) for register in registers)
        if sensor.value_type is RegisterValueType.UINT32:
            value = struct.unpack(">I", raw)[0]
        elif sensor.value_type is RegisterValueType.INT32:
            value = struct.unpack(">i", raw)[0]
        elif sensor.value_type is RegisterValueType.BCD32:
            return "".join(f"{register:04X}" for register in registers)
        elif sensor.value_type is RegisterValueType.HEX32:
            return f"{struct.unpack('>I', raw)[0]:08X}"
        else:
            value = struct.unpack(">f", raw)[0]

    if sensor.options is not None:
        return sensor.options.get(int(value), str(int(value)))

    scaled_value = value * sensor.scale
    if sensor.suggested_display_precision is not None:
        return round(scaled_value, sensor.suggested_display_precision)

    return scaled_value
