"""The WiNET pellet stove integration."""

from __future__ import annotations

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
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
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
