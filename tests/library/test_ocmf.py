"""Tests for the dedicated GROW OCMF register definitions."""

from inepro_metering.ocmf import GROW_OCMF_REGISTERS


def test_grow_ocmf_command_registers_match_confirmed_mapping() -> None:
    """The dedicated OCMF mapping should preserve the confirmed command layout."""
    assert GROW_OCMF_REGISTERS["billing_command"].address == 0x1101
    assert GROW_OCMF_REGISTERS["billing_command_status"].address == 0x1102
    assert GROW_OCMF_REGISTERS["billing_journal_rewind_command"].address == 0x1103
    assert GROW_OCMF_REGISTERS["billing_journal_rotate_command"].address == 0x1104
