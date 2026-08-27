"""Sensor platform for the WiNET integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import (
    ALARM_OPTIONS,
    AUTO_MODE_OPTIONS,
    STATUS_OPTIONS,
    UNDOCUMENTED_REGISTERS,
)
from .coordinator import WinetConfigEntry, WinetCoordinator
from .entity import WinetEntity
from .model import WinetData


@dataclass(frozen=True, kw_only=True)
class WinetSensorDescription(SensorEntityDescription):
    """Describes a WiNET sensor."""

    value_fn: Callable[[WinetData], StateType]


SENSORS: tuple[WinetSensorDescription, ...] = (
    WinetSensorDescription(
        key="status",
        translation_key="status",
        device_class=SensorDeviceClass.ENUM,
        options=STATUS_OPTIONS,
        value_fn=lambda data: data.status_key,
    ),
    WinetSensorDescription(
        key="alarm",
        translation_key="alarm",
        device_class=SensorDeviceClass.ENUM,
        options=ALARM_OPTIONS,
        value_fn=lambda data: data.alarm_key,
    ),
    WinetSensorDescription(
        key="measured_temperature",
        translation_key="measured_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda data: data.measured_temperature,
    ),
    WinetSensorDescription(
        key="target_temperature",
        translation_key="target_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.target_temperature,
    ),
    WinetSensorDescription(
        key="target_power",
        translation_key="target_power",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.target_power,
    ),
    WinetSensorDescription(
        key="auto_mode",
        translation_key="auto_mode",
        device_class=SensorDeviceClass.ENUM,
        options=list(AUTO_MODE_OPTIONS.values()),
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.auto_mode_key,
    ),
    WinetSensorDescription(
        key="wifi_signal",
        translation_key="wifi_signal",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.signal,
    ),
    WinetSensorDescription(
        key="rssi",
        translation_key="rssi",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.module.get("rssi"),
    ),
    WinetSensorDescription(
        key="ssid",
        translation_key="ssid",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.ssid,
    ),
    WinetSensorDescription(
        key="ip_address",
        translation_key="ip_address",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.module.get("currentIp"),
    ),
    WinetSensorDescription(
        key="alarm_code",
        translation_key="alarm_code",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.alarm_code,
    ),
    WinetSensorDescription(
        key="status_code",
        translation_key="status_code",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.raw_status,
    ),
)


def _raw_register_sensor(register: int) -> WinetSensorDescription:
    """Build a diagnostic sensor for a register whose meaning is unknown."""
    return WinetSensorDescription(
        key=f"register_{register}",
        # Deliberately not translated: these carry no known meaning to translate.
        name=f"Register {register}",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data, reg=register: data.registers.get(reg),
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WinetConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    coordinator = entry.runtime_data
    descriptions = [
        *SENSORS,
        *(_raw_register_sensor(reg) for reg in UNDOCUMENTED_REGISTERS),
    ]
    async_add_entities(WinetSensor(coordinator, desc) for desc in descriptions)


class WinetSensor(WinetEntity, SensorEntity):
    """A sensor reading one decoded field of the snapshot."""

    entity_description: WinetSensorDescription

    def __init__(
        self, coordinator: WinetCoordinator, description: WinetSensorDescription
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)
