"""Shared exceptions for the Inepro Metering library."""

from __future__ import annotations


class IneproMeteringError(Exception):
    """Base exception for the library."""


class IneproConnectionError(IneproMeteringError):
    """Raised when the Modbus transport cannot be reached."""


class IneproBluetoothNotPairedError(IneproConnectionError):
    """Raised when a BLE meter requires host-level pairing before Modbus writes."""


class IneproReadError(IneproMeteringError):
    """Raised when a Modbus read fails."""


class IneproWriteError(IneproMeteringError):
    """Raised when a Modbus write fails."""
