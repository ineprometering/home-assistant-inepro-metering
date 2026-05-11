"""BlueZ pairing agent used for GROW encrypted BLE writes."""

import asyncio
import inspect
import logging

from dbus_fast.errors import DBusError
from dbus_fast.service import ServiceInterface, method

LOGGER = logging.getLogger(__name__)


class IneproBlueZPairingAgent(ServiceInterface):
    """Temporary Agent1 implementation that supplies the meter LCD PIN."""

    def __init__(
        self,
        name,
        pairing_timeout,
        pairing_pin,
        pairing_pin_provider,
        normalize_pairing_pin,
        pairing_request_callback=None,
    ):
        super().__init__("org.bluez.Agent1")
        self._name = name
        self._pairing_timeout = pairing_timeout
        self._pairing_pin = pairing_pin
        self._pairing_pin_provider = pairing_pin_provider
        self._normalize_pairing_pin = normalize_pairing_pin
        self._pairing_request_callback = pairing_request_callback

    def _notify_pairing_request(self):
        if self._pairing_request_callback is not None:
            self._pairing_request_callback()

    async def _pin(self):
        pin = self._pairing_pin
        if self._pairing_pin_provider is not None:
            provided = self._pairing_pin_provider()
            if inspect.isawaitable(provided):
                provided = await asyncio.wait_for(
                    provided,
                    timeout=float(self._pairing_timeout),
                )
            pin = provided
        normalized = self._normalize_pairing_pin(pin)
        if normalized is None:
            raise DBusError(
                "org.bluez.Error.Rejected",
                "A 6-digit meter Bluetooth PIN is required",
            )
        return normalized

    @method()
    def Release(self) -> None:
        """Handle BlueZ releasing the temporary agent."""
        pass

    @method()
    async def RequestPinCode(self, device: "o") -> "s":
        """Return the PIN shown on the meter LCD."""
        self._notify_pairing_request()
        LOGGER.warning(
            "ble_bluez_pairing_pin_requested name=%s device=%s",
            self._name,
            device,
        )
        return await self._pin()

    @method()
    async def RequestPasskey(self, device: "o") -> "u":
        """Return the passkey shown on the meter LCD."""
        self._notify_pairing_request()
        LOGGER.warning(
            "ble_bluez_pairing_passkey_requested name=%s device=%s",
            self._name,
            device,
        )
        return int(await self._pin())

    @method()
    def DisplayPasskey(self, device: "o", passkey: "u", entered: "q") -> None:
        """Accept display-passkey callbacks from BlueZ."""
        LOGGER.debug(
            "ble_bluez_display_passkey name=%s device=%s entered=%s",
            self._name,
            device,
            entered,
        )

    @method()
    async def RequestConfirmation(self, device: "o", passkey: "u") -> None:
        """Accept numeric-comparison confirmation requests."""
        LOGGER.debug(
            "ble_bluez_confirm_passkey name=%s device=%s",
            self._name,
            device,
        )

    @method()
    async def RequestAuthorization(self, device: "o") -> None:
        """Accept authorization requests for the temporary pairing."""
        LOGGER.debug("ble_bluez_authorize_pairing name=%s device=%s", self._name, device)

    @method()
    async def AuthorizeService(self, device: "o", uuid: "s") -> None:
        """Accept service authorization requests for the temporary pairing."""
        LOGGER.debug(
            "ble_bluez_authorize_service name=%s device=%s uuid=%s",
            self._name,
            device,
            uuid,
        )

    @method()
    def Cancel(self) -> None:
        """Handle BlueZ cancelling the pairing request."""
        LOGGER.debug("ble_bluez_pairing_cancelled name=%s", self._name)
