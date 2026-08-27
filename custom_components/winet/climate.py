"""Climate platform: the stove itself."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    STATUS_ALARMS,
    STATUS_FINAL_CLEANING,
    STATUS_HEATING,
    STATUS_OFF,
    STATUS_PREHEATING,
    STATUS_STANDBY,
    TARGET_TEMP_MAX,
    TARGET_TEMP_MIN,
)
from .coordinator import WinetConfigEntry, WinetCoordinator
from .entity import WinetEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WinetConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the stove climate entity."""
    async_add_entities([WinetClimate(entry.runtime_data)])


class WinetClimate(WinetEntity, ClimateEntity):
    """The pellet stove, as a thermostat."""

    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_min_temp = TARGET_TEMP_MIN
    _attr_max_temp = TARGET_TEMP_MAX

    def __init__(self, coordinator: WinetCoordinator) -> None:
        """Initialise the climate entity."""
        super().__init__(coordinator, "climate")

    @property
    def target_temperature_step(self) -> float:
        """Return the step, which is one raw register unit."""
        return self.coordinator.data.set_temp_div or 1.0

    @property
    def current_temperature(self) -> float | None:
        """Return the temperature measured by the stove."""
        return self.coordinator.data.measured_temperature

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature setpoint."""
        return self.coordinator.data.target_temperature

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return HEAT while the stove is on and not already shutting down.

        The firmware still calls the stove "on" during the final cleaning cycle, but a
        thermostat that flipped back to Heat right after the user asked for Off would be
        actively misleading. The Status sensor keeps reporting the real phase.
        """
        is_on = self.coordinator.data.is_heat_on
        if is_on is None:
            return None
        return HVACMode.HEAT if is_on else HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return what the stove is actually doing."""
        status = self.coordinator.data.status
        if status is None:
            return None
        if status in STATUS_HEATING:
            return HVACAction.HEATING
        if status in STATUS_PREHEATING:
            return HVACAction.PREHEATING
        if status == STATUS_STANDBY:
            return HVACAction.IDLE
        if status == STATUS_FINAL_CLEANING:
            # Fans still running to burn off the last pellets, but on the way out.
            return HVACAction.IDLE
        if status == STATUS_OFF or status in STATUS_ALARMS:
            return HVACAction.OFF
        return None

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Turn the stove on or off."""
        await self.coordinator.async_set_power(hvac_mode == HVACMode.HEAT)

    async def async_turn_on(self) -> None:
        """Turn the stove on."""
        await self.coordinator.async_set_power(True)

    async def async_turn_off(self) -> None:
        """Turn the stove off."""
        await self.coordinator.async_set_power(False)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the temperature setpoint."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is not None:
            await self.coordinator.async_set_target_temperature(float(temperature))
