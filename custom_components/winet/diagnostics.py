"""Diagnostics support for the WiNET integration."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .api import WinetError
from .coordinator import WinetConfigEntry

#: No credentials exist on the local interface; only the topology is worth hiding.
TO_REDACT = {"currentIp", "currentGw", "currentMask", "currentApIp", "network", "ssid"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: WinetConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    data = coordinator.data
    raw_config: dict[str, Any]
    try:
        raw_config = await coordinator.client.async_get_config()
    except WinetError as err:
        # A diagnostics download should still succeed when the module is unreachable.
        raw_config = {"error": str(err)}

    return {
        "entry": {
            "options": dict(entry.options),
            "scan_interval": getattr(coordinator.update_interval, "seconds", None),
        },
        "firmware_version": coordinator.firmware_version,
        "decoded": async_redact_data(
            {
                **{
                    field: value
                    for field, value in asdict(data).items()
                    if field != "module"
                },
                "status_key": data.status_key,
                "alarm_key": data.alarm_key,
                "active_alarms": data.active_alarms,
                "measured_temperature": data.measured_temperature,
                "target_temperature": data.target_temperature,
                "target_power": data.target_power,
            },
            TO_REDACT,
        ),
        "module_status": async_redact_data(data.module, TO_REDACT),
        "module_config": async_redact_data(raw_config, TO_REDACT),
    }
