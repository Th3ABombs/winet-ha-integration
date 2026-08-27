"""The WiNET pellet stove integration."""

from __future__ import annotations

import logging

from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import voluptuous as vol

from .api import WinetClient
from .const import (
    ATTR_MEMORY,
    ATTR_REGISTER,
    ATTR_VALUE,
    CONF_IDENTIFIER,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    IDENTIFIER_HOST,
    MAX_SCAN_INTERVAL,
    MEMORY_PERSISTENT,
    MEMORY_VOLATILE,
    MIN_SCAN_INTERVAL,
    SERVICE_SET_REGISTER,
)
from .coordinator import WinetConfigEntry, WinetCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SENSOR,
]

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SET_REGISTER_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
        vol.Required(ATTR_REGISTER): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=511)
        ),
        vol.Required(ATTR_VALUE): vol.All(vol.Coerce(int), vol.Range(min=0, max=65535)),
        vol.Optional(ATTR_MEMORY, default=MEMORY_PERSISTENT): vol.All(
            vol.Coerce(int), vol.In([MEMORY_VOLATILE, MEMORY_PERSISTENT])
        ),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: WinetConfigEntry) -> bool:
    """Set up one WiNET module from a config entry."""
    client = WinetClient(async_get_clientsession(hass), entry.data[CONF_HOST])
    scan_interval = min(
        MAX_SCAN_INTERVAL,
        max(
            MIN_SCAN_INTERVAL,
            entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        ),
    )
    coordinator = WinetCoordinator(hass, entry, client, scan_interval)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    _async_register_services(hass)
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: WinetConfigEntry) -> bool:
    """Bring a v1 entry up to v2 **without changing how it is identified**.

    v1 keyed the module on its host. v2 can key it on the MAC instead, but an existing
    install is deliberately left where it is: re-keying would rewrite every entity's
    unique id *and* change the device registry identifier, which silently orphans the
    device and breaks anything referencing its id — including `winet.set_register`
    calls and area assignments. That is not a trade worth making automatically on a
    working system.

    So this records the identity the entry already had and moves on. To switch an
    existing install to the MAC, remove the integration and add it again choosing
    "MAC address"; that is an explicit, visible action with an obvious cost.
    """
    if entry.version > 2:
        # A newer version wrote this entry; downgrading is not supported.
        return False
    if entry.version == 2:
        return True

    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, CONF_IDENTIFIER: IDENTIFIER_HOST},
        version=2,
    )
    _LOGGER.debug("Migrated WiNET entry to version 2, keeping its host-based identity")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WinetConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(hass: HomeAssistant, entry: WinetConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _async_register_services(hass: HomeAssistant) -> None:
    """Register the domain-level services once."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_REGISTER):
        return

    async def _handle_set_register(call: ServiceCall) -> None:
        """Write an arbitrary stove register."""
        device = dr.async_get(hass).async_get(call.data["device_id"])
        if device is None:
            raise ServiceValidationError("Unknown device")

        for entry_id in device.config_entries:
            entry = hass.config_entries.async_get_entry(entry_id)
            if entry is not None and entry.domain == DOMAIN:
                coordinator: WinetCoordinator = entry.runtime_data
                await coordinator.async_write_register(
                    call.data[ATTR_MEMORY],
                    call.data[ATTR_REGISTER],
                    call.data[ATTR_VALUE],
                )
                return

        raise ServiceValidationError("That device does not belong to a WiNET entry")

    hass.services.async_register(
        DOMAIN, SERVICE_SET_REGISTER, _handle_set_register, schema=SET_REGISTER_SCHEMA
    )
