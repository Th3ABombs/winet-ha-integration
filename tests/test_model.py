"""Unit tests for the pure decoding layer.

Run with ``python -m pytest tests`` — these tests import no Home Assistant code.
The payloads are captures from a WiNET 0.79 module (model 0, custom 65535), with the
reporting network's SSID replaced by a placeholder.
"""

from __future__ import annotations

import json
from pathlib import Path

from winet_pure.const import (
    STATUS_ALARM,
    STATUS_FINAL_CLEANING,
    STATUS_OFF,
    STATUS_WORK,
    STATUS_WORK_MODULATING,
)
from winet_pure.model import decode

FIXTURES = Path(__file__).parent / "fixtures"
MODULE_STATUS = json.loads((FIXTURES / "get_status.json").read_text())
RUNTIME_OFF = json.loads((FIXTURES / "runtime_off.json").read_text())
RUNTIME_RUNNING = json.loads((FIXTURES / "runtime_running.json").read_text())


def test_decodes_registers_from_pair_list() -> None:
    """The [reg, value] pairs become an int-keyed mapping."""
    data = decode(RUNTIME_OFF, MODULE_STATUS)
    assert data.registers[0] == 55
    assert data.registers[2] == 0
    assert data.registers[303] == 0
    assert len(data.registers) == len(RUNTIME_OFF["params"])


def test_measured_temperature_applies_temp_div() -> None:
    """Register 0 is scaled by tempDiv, matching the module's own logTemp."""
    data = decode(RUNTIME_OFF, MODULE_STATUS)
    assert data.measured_temperature == 27.5
    assert data.measured_temperature == RUNTIME_OFF["logTemp"] / 10


def test_flue_gas_temperature_is_offset_by_30_degrees() -> None:
    """Register 4 counts from 30 °C, per the module's own parameter definition."""
    running = decode(RUNTIME_RUNNING, MODULE_STATUS)
    assert running.registers[4] == 200
    assert running.flue_gas_temperature == 230.0

    off = decode(RUNTIME_OFF, MODULE_STATUS)
    # A raw 0 on a cold stove is 30 °C, not a missing reading -- which is why the
    # register reads 0 while the room itself sits at 27.5 °C.
    assert off.registers[4] == 0
    assert off.flue_gas_temperature == 30.0
    assert off.measured_temperature == 27.5


def test_flue_gas_temperature_absent_when_not_reported() -> None:
    """A payload without register 4 yields no reading rather than 30 °C."""
    assert decode({"params": [[2, 0]]}, {}).flue_gas_temperature is None


def test_setpoints() -> None:
    """Setpoint 10 with setTempDiv 1 reads as 10 °C; power 255 is 'not reported'."""
    data = decode(RUNTIME_OFF, MODULE_STATUS)
    assert data.target_temperature == 10.0
    assert data.target_power is None


def test_off_state() -> None:
    """Status 0 is off in every sense."""
    data = decode(RUNTIME_OFF, MODULE_STATUS)
    assert data.status == STATUS_OFF
    assert data.status_key == "off"
    assert data.is_on is False
    assert data.is_heat_on is False
    assert data.is_shutting_down is False
    assert data.has_alarm is False
    assert data.active_alarms == []
    assert data.alarm_key == "none"


def test_running_state() -> None:
    """Status 4 with the measurement below setpoint stays plain 'work'."""
    data = decode(RUNTIME_RUNNING, MODULE_STATUS)
    assert data.status == STATUS_WORK
    assert data.status_key == "work"
    assert data.is_on is True
    assert data.is_heat_on is True
    assert data.target_power == 3


def test_modulating_substitution() -> None:
    """Working at or above setpoint becomes the virtual status 200."""
    runtime = json.loads(json.dumps(RUNTIME_RUNNING))
    # measured = 55 * 0.5 = 27.5 °C; drop the setpoint below it.
    runtime["params"] = [
        [reg, 20 if reg == 50 else value] for reg, value in runtime["params"]
    ]
    data = decode(runtime, MODULE_STATUS)
    assert data.status == STATUS_WORK_MODULATING
    assert data.status_key == "work_modulating"
    assert data.raw_status == STATUS_WORK, "the raw register must stay untouched"


def test_final_cleaning_is_on_for_the_firmware_but_off_for_a_thermostat() -> None:
    """The distinction the power command depends on."""
    runtime = json.loads(json.dumps(RUNTIME_OFF))
    runtime["params"] = [
        [reg, STATUS_FINAL_CLEANING if reg == 2 else value]
        for reg, value in runtime["params"]
    ]
    data = decode(runtime, MODULE_STATUS)
    assert data.is_on is True
    assert data.is_heat_on is False
    assert data.is_shutting_down is True


def test_alarm_bitmask_lists_every_bit_but_shows_the_lowest() -> None:
    """Register 3 is a bitmask; the firmware displays only the lowest set bit."""
    runtime = json.loads(json.dumps(RUNTIME_OFF))
    runtime["params"] = [
        [reg, 0b0001_1001 if reg == 3 else value] for reg, value in runtime["params"]
    ]
    data = decode(runtime, MODULE_STATUS)
    assert data.active_alarms == [
        "fumes_probe_failure",
        "ignition_failure",
        "no_pellet",
    ]
    assert data.alarm_key == "fumes_probe_failure"
    assert data.has_alarm is True


def test_alarm_status_without_bits_still_flags_a_problem() -> None:
    """Status 8 is an alarm even if register 3 happens to read 0."""
    runtime = json.loads(json.dumps(RUNTIME_OFF))
    runtime["params"] = [
        [reg, STATUS_ALARM if reg == 2 else value] for reg, value in runtime["params"]
    ]
    data = decode(runtime, MODULE_STATUS)
    assert data.has_alarm is True
    assert data.status_key == "alarm"


def test_missing_and_malformed_payload_fields_do_not_raise() -> None:
    """A truncated payload degrades to None rather than blowing up."""
    data = decode({"params": [[0, "x"], "junk", [2, 4]]}, {})
    assert data.registers == {2: 4}
    assert data.measured_temperature is None
    assert data.target_temperature is None
    assert data.temp_div == 1.0
    assert data.num_power == 5


def test_unknown_status_falls_back() -> None:
    """A status from another customization table is reported as unknown."""
    data = decode({"params": [[2, 42]]}, {})
    assert data.status_key == "unknown"


def test_auto_mode_and_module_fields() -> None:
    """Module-side fields are carried through."""
    data = decode(RUNTIME_OFF, MODULE_STATUS)
    assert data.auto_mode_key == "disabled"
    assert data.num_power == 5
    assert data.custom_code == 65535
    assert data.module["fwVer"] == "0.79"
    assert data.ssid == "MyWiFi"
