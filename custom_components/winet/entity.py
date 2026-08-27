"""Shared entity base for the WiNET integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
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
        identity = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{identity}_{key}"
        # A host-keyed entry (older firmware, no /api/id) is not a MAC, so only claim
        # the connection when the id actually looks like one.
        connections = (
            {(CONNECTION_NETWORK_MAC, identity)} if _is_mac(identity) else set()
        )
        self._attr_device_info = DeviceInfo(
            connections=connections,
            identifiers={(DOMAIN, identity)},
            manufacturer=MANUFACTURER,
            model=MODEL_NAME,
            name=entry.title,
            sw_version=coordinator.firmware_version,
            configuration_url=f"http://{coordinator.client.host}/management.html",
        )


def _is_mac(value: str) -> bool:
    """Return whether ``value`` is a formatted MAC address."""
    parts = value.split(":")
    return len(parts) == 6 and all(
        len(p) == 2 and all(c in "0123456789abcdef" for c in p) for p in parts
    )
