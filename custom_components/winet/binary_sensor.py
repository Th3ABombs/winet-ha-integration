"""Binary sensor platform for the WiNET integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import WinetConfigEntry, WinetCoordinator
from .entity import WinetEntity
from .model import WinetData


@dataclass(frozen=True, kw_only=True)
class WinetBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a WiNET binary sensor."""

    value_fn: Callable[[WinetData], bool | None]


BINARY_SENSORS: tuple[WinetBinarySensorDescription, ...] = (
    WinetBinarySensorDescription(
        key="alarm",
        translation_key="alarm",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda data: data.has_alarm,
    ),
    WinetBinarySensorDescription(
        key="running",
        translation_key="running",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda data: data.is_on,
    ),
    WinetBinarySensorDescription(
        key="firmware_update",
        translation_key="firmware_update",
        device_class=BinarySensorDeviceClass.UPDATE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: bool(data.module.get("fwUpdate")),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WinetConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors."""
    async_add_entities(
        WinetBinarySensor(entry.runtime_data, desc) for desc in BINARY_SENSORS
    )


class WinetBinarySensor(WinetEntity, BinarySensorEntity):
    """A binary sensor derived from the snapshot."""

    entity_description: WinetBinarySensorDescription

    def __init__(
        self, coordinator: WinetCoordinator, description: WinetBinarySensorDescription
    ) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return the binary state."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, list[str]] | None:
        """List the active alarm bits on the alarm sensor."""
        if self.entity_description.key != "alarm":
            return None
        return {"active_alarms": self.coordinator.data.active_alarms}
