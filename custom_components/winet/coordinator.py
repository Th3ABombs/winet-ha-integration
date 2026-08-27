"""Polling coordinator for the WiNET integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import WinetClient, WinetError
from .const import (
    DOMAIN,
    MEMORY_PERSISTENT,
    OPTIMISTIC_POWER_WINDOW,
    POST_WRITE_REFRESH_DELAY,
    REG_TARGET_POWER,
    REG_TARGET_TEMP,
    STATUS_FINAL_CLEANING,
    STATUS_IGNITION,
)
from .model import PowerAction, WinetData, decide_power_action, decode

_LOGGER = logging.getLogger(__name__)

type WinetConfigEntry = ConfigEntry[WinetCoordinator]


class WinetCoordinator(DataUpdateCoordinator[WinetData]):
    """Poll the module and serialise the commands sent back to it."""

    config_entry: WinetConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: WinetConfigEntry,
        client: WinetClient,
        scan_interval: float,
    ) -> None:
        """Set up the coordinator for one module."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"{DOMAIN} {client.host}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self._command_lock = asyncio.Lock()
        #: Set to False after /api/global first fails, so older modules are not polled
        #: for an interface they do not have on every single cycle.
        self._api_available = True
        self._optimistic_on: bool | None = None
        self._optimistic_until: float = 0.0
        #: Reported by ``/ajax/get-status`` on every poll; kept for the device entry.
        self.firmware_version: str | None = None

    # --- polling ----------------------------------------------------------

    async def _async_update_data(self) -> WinetData:
        """Fetch and decode one snapshot."""
        try:
            runtime = await self.client.async_get_runtime()
            module = await self.client.async_get_module_status()
        except WinetError as err:
            raise UpdateFailed(str(err)) from err

        api_global: dict | None = None
        if self._api_available:
            try:
                api_global = await self.client.async_get_api_global()
            except WinetError as err:
                # The /api interface is absent on some firmwares. Losing it costs a few
                # readings, not the integration, so degrade instead of failing.
                self._api_available = False
                _LOGGER.info(
                    "WiNET at %s has no usable /api interface (%s); continuing without "
                    "the extractor and hydronic readings",
                    self.client.host,
                    err,
                )

        data = decode(runtime, module, api_global)
        self.firmware_version = module.get("fwVer") or self.firmware_version

        if self._optimistic_on is not None:
            expired = time.monotonic() >= self._optimistic_until
            if data.is_heat_on == self._optimistic_on or expired:
                if expired and data.is_heat_on != self._optimistic_on:
                    _LOGGER.warning(
                        "WiNET at %s did not reach the requested power "
                        "state within %.0fs; falling back to the reported status",
                        self.client.host,
                        OPTIMISTIC_POWER_WINDOW,
                    )
                self._optimistic_on = None
            else:
                # Show the state the stove is transitioning into, not a made-up one.
                data.status = (
                    STATUS_IGNITION if self._optimistic_on else STATUS_FINAL_CLEANING
                )

        return data

    # --- commands ---------------------------------------------------------

    async def async_set_power(self, turn_on: bool) -> None:
        """Bring the stove to ``turn_on``, sending the toggle only if needed."""
        async with self._command_lock:
            status = self.data.status if self.data is not None else None
            action = decide_power_action(status, turn_on)

            if action is PowerAction.REFUSE_UNKNOWN:
                raise HomeAssistantError(
                    "The stove status is unknown; refusing to send a blind "
                    "on/off toggle"
                )
            if action is PowerAction.REFUSE_WAIT_FOR_OFF:
                raise HomeAssistantError(
                    "The stove is running its final cleaning cycle; "
                    "wait for it to reach OFF before turning it on again"
                )
            if action is PowerAction.NOTHING:
                _LOGGER.debug(
                    "No toggle needed: status %s, requested %s",
                    status,
                    "on" if turn_on else "off",
                )
                return

            if self._api_available:
                # Absolute command: says what the stove should be, not "flip it".
                await self.client.async_set_power(turn_on)
            else:
                await self.client.async_toggle_power()
            self._optimistic_on = turn_on
            self._optimistic_until = time.monotonic() + OPTIMISTIC_POWER_WINDOW

        self._set_optimistic_status(
            STATUS_IGNITION if turn_on else STATUS_FINAL_CLEANING
        )
        await self._async_delayed_refresh()

    async def async_set_target_temperature(self, temperature: float) -> None:
        """Write the temperature setpoint."""
        data = self.data
        div = data.set_temp_div if data else 1.0
        raw = round(temperature / div) if div else round(temperature)
        await self._async_write(MEMORY_PERSISTENT, REG_TARGET_TEMP, raw)

    async def async_set_target_power(self, power: int) -> None:
        """Write the power setpoint."""
        await self._async_write(MEMORY_PERSISTENT, REG_TARGET_POWER, int(power))

    async def async_write_register(self, memory: int, reg_id: int, value: int) -> None:
        """Write an arbitrary register (exposed as a service)."""
        await self._async_write(memory, reg_id, value)

    async def _async_write(self, memory: int, reg_id: int, raw: int) -> None:
        """Write one register, then refresh."""
        if not 0 <= raw <= 0xFFFF:
            raise ServiceValidationError(f"Register value {raw} is out of range")
        async with self._command_lock:
            await self.client.async_set_register(memory, reg_id, raw)
            if self.data is not None:
                self.data.registers[reg_id] = raw
                self.async_update_listeners()
        await self._async_delayed_refresh()

    def _set_optimistic_status(self, status: int) -> None:
        """Show ``status`` immediately, before the module has re-read the board.

        ``raw_status`` is left alone so the diagnostic sensors keep telling the truth.
        """
        if self.data is not None:
            self.data.status = status
            self.async_update_listeners()

    async def _async_delayed_refresh(self) -> None:
        """Give the module time to talk to the stove board, then poll."""
        await asyncio.sleep(POST_WRITE_REFRESH_DELAY)
        await self.async_request_refresh()
