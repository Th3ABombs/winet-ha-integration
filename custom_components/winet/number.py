"""Number platform: the flame power setpoint."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import WinetConfigEntry, WinetCoordinator
from .entity import WinetEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WinetConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the power number entity."""
    async_add_entities([WinetPowerNumber(entry.runtime_data)])


class WinetPowerNumber(WinetEntity, NumberEntity):
    """The stove's flame power level (register 51)."""

    _attr_translation_key = "target_power"
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = 1
    _attr_native_step = 1

    def __init__(self, coordinator: WinetCoordinator) -> None:
        """Initialise the power entity."""
        super().__init__(coordinator, "target_power")

    @property
    def native_max_value(self) -> float:
        """Return the number of power levels the module reports."""
        return self.coordinator.data.num_power

    @property
    def native_value(self) -> float | None:
        """Return the current power setpoint."""
        return self.coordinator.data.target_power

    async def async_set_native_value(self, value: float) -> None:
        """Write the power setpoint."""
        await self.coordinator.async_set_target_power(int(value))
