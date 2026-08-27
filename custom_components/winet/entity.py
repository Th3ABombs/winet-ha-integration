"""Shared entity base for the WiNET integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL_NAME
from .coordinator import WinetCoordinator


class WinetEntity(CoordinatorEntity[WinetCoordinator]):
    """Base entity tying every platform to the same device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: WinetCoordinator, key: str) -> None:
        """Attach to the coordinator and derive the unique ID from ``key``."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.unique_id or entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
            manufacturer=MANUFACTURER,
            model=MODEL_NAME,
            name=entry.title,
            sw_version=coordinator.firmware_version,
            configuration_url=f"http://{coordinator.client.host}/management.html",
        )
