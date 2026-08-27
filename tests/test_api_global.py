"""Tests for the readings that come from the secondary /api interface.

The payload is a verbatim capture from firmware 0.79 on an air stove, where the
hydronic and extractor fields are null because the board does not report them.
"""

from __future__ import annotations

import json
from pathlib import Path

from winet_pure.model import decode

FIXTURES = Path(__file__).parent / "fixtures"
MODULE_STATUS = json.loads((FIXTURES / "get_status.json").read_text())
RUNTIME_OFF = json.loads((FIXTURES / "runtime_off.json").read_text())
API_GLOBAL = json.loads((FIXTURES / "api_global.json").read_text())


def test_without_api_the_extra_fields_stay_empty() -> None:
    """A module with no /api interface loses those readings and nothing else."""
    data = decode(RUNTIME_OFF, MODULE_STATUS)
    assert data.api_available is False
    assert data.rpm_extractor is None
    assert data.water_raw is None
    assert data.firmware_status_text is None
    # The rest still decodes.
    assert data.measured_temperature == 27.5
    assert data.status_key == "off"


def test_api_fields_are_carried_through() -> None:
    """The /api payload adds the firmware's own status text."""
    data = decode(RUNTIME_OFF, MODULE_STATUS, API_GLOBAL)
    assert data.api_available is True
    assert data.firmware_status_text == "OFF"


def test_null_hydronic_and_extractor_fields_stay_none() -> None:
    """`null` means the board does not report it, and must not become 0."""
    data = decode(RUNTIME_OFF, MODULE_STATUS, API_GLOBAL)
    assert data.rpm_extractor is None
    assert data.water_raw is None
    assert data.water_setpoint_raw is None


def test_populated_hydronic_and_extractor_fields() -> None:
    """On a stove that reports them, the values come through unconverted."""
    payload = {**API_GLOBAL, "rpmExtractor": 1450, "water": 128, "setWater": 140}
    data = decode(RUNTIME_OFF, MODULE_STATUS, payload)
    assert data.rpm_extractor == 1450
    assert data.water_raw == 128
    assert data.water_setpoint_raw == 140


def test_setair_is_never_used_as_the_setpoint() -> None:
    """The trap this interface sets.

    /api/global reports setAir 20 while register 50 holds 10, and the module's own web
    page shows 10 °C as the set point. setAir tracks tStart, the module's own auto
    start/stop threshold, so the target temperature keeps coming from register 50.
    """
    data = decode(RUNTIME_OFF, MODULE_STATUS, API_GLOBAL)
    assert API_GLOBAL["setAir"] == 20
    assert data.registers[50] == 10
    assert data.target_temperature == 10.0


def test_api_does_not_override_register_derived_values() -> None:
    """Even a contradictory /api payload must not move what registers decide."""
    payload = {**API_GLOBAL, "status": 4, "air": 999, "gasflue": 99, "power": 3}
    data = decode(RUNTIME_OFF, MODULE_STATUS, payload)
    assert data.status_key == "off", "status comes from register 2"
    assert data.measured_temperature == 27.5, "temperature comes from register 0"
    assert data.flue_gas_temperature == 30.0, "flue gas comes from register 4"
    assert data.target_power is None, "power comes from register 51"
