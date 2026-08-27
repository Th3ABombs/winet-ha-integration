"""The WiNET pellet stove integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)
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
    """Migrate a v1 entry, which was keyed by host, to a MAC-keyed v2 entry.

    v1 identified the module by host because the MAC was not known to be available
    anywhere locally. It is, from ``/api/id``. Re-keying the entry would orphan every
    entity — their unique ids embed the entry's — so the entity registry is rewritten in
    the same step and history survives.

    A module that does not serve ``/api/id`` keeps its host-based id; nothing is lost
    but nothing improves either. Either way the entry records which one it ended up
    using, so it is visible rather than inferred.
    """
    if entry.version > 2:
        # Downgrades are not supported: a newer version wrote this entry.
        return False
    if entry.version == 2:
        return True

    from .config_flow import async_resolve_unique_id

    client = WinetClient(async_get_clientsession(hass), entry.data[CONF_HOST])
    try:
        new_unique_id, identifier = await async_resolve_unique_id(client)
    except Exception:  # noqa: BLE001  a failed migration must be retried, not crash
        _LOGGER.warning("Could not reach %s to migrate its id", entry.data[CONF_HOST])
        return False

    new_data = {**entry.data, CONF_IDENTIFIER: identifier}
    old_unique_id = entry.unique_id or entry.entry_id
    if new_unique_id == old_unique_id:
        hass.config_entries.async_update_entry(entry, data=new_data, version=2)
        return True

    @callback
    def _migrate_entity(registry_entry: er.RegistryEntry) -> dict[str, Any] | None:
        """Re-prefix one entity's unique id, leaving anything unexpected alone."""
        if not registry_entry.unique_id.startswith(f"{old_unique_id}_"):
            return None
        suffix = registry_entry.unique_id[len(old_unique_id) + 1 :]
        return {"new_unique_id": f"{new_unique_id}_{suffix}"}

    await er.async_migrate_entries(hass, entry.entry_id, _migrate_entity)
    hass.config_entries.async_update_entry(entry, unique_id=new_unique_id, version=2)
    _LOGGER.info("Migrated WiNET entry from %s to %s", old_unique_id, new_unique_id)
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
