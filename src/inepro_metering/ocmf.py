"""Dedicated OCMF register definitions for Inepro GROW meters."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OcmfRegisterDefinition:
    """One OCMF-related Modbus register range."""

    address: int
    count: int


GROW_OCMF_REGISTERS: dict[str, OcmfRegisterDefinition] = {
    "current_datetime": OcmfRegisterDefinition(address=0x1000, count=2),
    "timezone": OcmfRegisterDefinition(address=0x1002, count=1),
    "time_status": OcmfRegisterDefinition(address=0x1003, count=1),
    "time_status_timeout": OcmfRegisterDefinition(address=0x1004, count=1),
    "billing_session_start_energy": OcmfRegisterDefinition(address=0x1010, count=2),
    "billing_session_accumulated_energy": OcmfRegisterDefinition(address=0x1012, count=2),
    "billing_session_status": OcmfRegisterDefinition(address=0x1100, count=1),
    "billing_command": OcmfRegisterDefinition(address=0x1101, count=1),
    "billing_command_status": OcmfRegisterDefinition(address=0x1102, count=1),
    "billing_journal_rewind_command": OcmfRegisterDefinition(address=0x1103, count=1),
    "billing_journal_rotate_command": OcmfRegisterDefinition(address=0x1104, count=1),
    "public_key_length": OcmfRegisterDefinition(address=0x1200, count=1),
    "public_key_data": OcmfRegisterDefinition(address=0x1201, count=32),
    "signature_length": OcmfRegisterDefinition(address=0x1281, count=1),
    "signature_data": OcmfRegisterDefinition(address=0x1282, count=32),
    "billing_dataset_length": OcmfRegisterDefinition(address=0x1300, count=1),
    "billing_dataset_data": OcmfRegisterDefinition(address=0x1301, count=512),
    "billing_output_length": OcmfRegisterDefinition(address=0x1600, count=1),
    "billing_output_data": OcmfRegisterDefinition(address=0x1601, count=1024),
}


__all__ = [
    "OcmfRegisterDefinition",
    "GROW_OCMF_REGISTERS",
]
