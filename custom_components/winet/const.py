"""Constants for the WiNET pellet stove integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "winet"

MANUFACTURER: Final = "Net Software S.r.l."
MODEL_NAME: Final = "WiNET"

CONF_SCAN_INTERVAL: Final = "scan_interval"
DEFAULT_SCAN_INTERVAL: Final = 15
MIN_SCAN_INTERVAL: Final = 5
MAX_SCAN_INTERVAL: Final = 300

DEFAULT_NAME: Final = "Stufa"

# --- registers ------------------------------------------------------------

REG_MEASURED_TEMP: Final = 0
REG_STATUS: Final = 2
REG_ALARM: Final = 3
REG_FLUE_TEMP: Final = 4
REG_TARGET_TEMP: Final = 50
REG_TARGET_POWER: Final = 51
REG_CLOCK_WEEKDAY: Final = 59
REG_CLOCK_HOUR: Final = 60
REG_CLOCK_MINUTE: Final = 61
REG_CLOCK_DAY: Final = 62
REG_CLOCK_MONTH: Final = 63
REG_CLOCK_YEAR: Final = 64

#: Register 4 counts from 30 °C, not from zero: the module's own parameter definition
#: is ``mul=1, offset=30, min=30, max=285``. A raw 0 means 30 °C, not a dead probe.
FLUE_TEMP_OFFSET: Final = 30

#: Registers that `management.js` never references. Exposed as disabled-by-default
#: diagnostics so they can be identified by watching a running stove.
UNDOCUMENTED_REGISTERS: Final = (300, 301, 302, 303)

MEMORY_VOLATILE: Final = 0
MEMORY_PERSISTENT: Final = 1

#: Raw value the firmware reports when a register holds no meaningful data.
RAW_UNAVAILABLE: Final = 255

# UI limits taken from the `<label id="p50">` / `<label id="p51">` attributes.
TARGET_TEMP_MIN: Final = 5.0
TARGET_TEMP_MAX: Final = 40.0
DEFAULT_NUM_POWER: Final = 5

# --- status ---------------------------------------------------------------

STATUS_OFF: Final = 0
STATUS_WAIT_FLAME_1: Final = 1
STATUS_WAIT_FLAME_2: Final = 2
STATUS_IGNITION: Final = 3
STATUS_WORK: Final = 4
STATUS_BRAZIER_CLEANING: Final = 5
STATUS_FINAL_CLEANING: Final = 6
STATUS_STANDBY: Final = 7
STATUS_ALARM: Final = 8
STATUS_ALARM_MEMORY: Final = 9
#: Not a real register value: the firmware substitutes it while working at setpoint.
STATUS_WORK_MODULATING: Final = 200

STATUS_UNKNOWN_KEY: Final = "unknown"

STATUS_KEYS: Final[dict[int, str]] = {
    STATUS_OFF: "off",
    STATUS_WAIT_FLAME_1: "wait_flame",
    STATUS_WAIT_FLAME_2: "wait_flame",
    STATUS_IGNITION: "ignition",
    STATUS_WORK: "work",
    STATUS_BRAZIER_CLEANING: "brazier_cleaning",
    STATUS_FINAL_CLEANING: "final_cleaning",
    STATUS_STANDBY: "standby",
    STATUS_ALARM: "alarm",
    STATUS_ALARM_MEMORY: "alarm_memory",
    STATUS_WORK_MODULATING: "work_modulating",
}

#: Ordered for the enum sensor's `options`; duplicates from STATUS_KEYS removed.
STATUS_OPTIONS: Final = [
    "off",
    "wait_flame",
    "ignition",
    "work",
    "work_modulating",
    "brazier_cleaning",
    "final_cleaning",
    "standby",
    "alarm",
    "alarm_memory",
    STATUS_UNKNOWN_KEY,
]

#: Statuses in which the stove is producing heat.
STATUS_HEATING: Final = frozenset(
    {STATUS_WORK, STATUS_WORK_MODULATING, STATUS_BRAZIER_CLEANING}
)
#: Statuses in which the stove is on its way to producing heat.
STATUS_PREHEATING: Final = frozenset(
    {STATUS_WAIT_FLAME_1, STATUS_WAIT_FLAME_2, STATUS_IGNITION}
)
STATUS_ALARMS: Final = frozenset({STATUS_ALARM, STATUS_ALARM_MEMORY})

# --- alarms ---------------------------------------------------------------

ALARM_BIT_KEYS: Final = (
    "fumes_probe_failure",
    "fumes_overtemperature",
    "extractor_malfunction",
    "ignition_failure",
    "no_pellet",
    "no_pressure",
    "thermal_safety",
    "pellet_compartment_open",
)

ALARM_NONE_KEY: Final = "none"
ALARM_OPTIONS: Final = [ALARM_NONE_KEY, *ALARM_BIT_KEYS]

# --- module-side auto start/stop -----------------------------------------

AUTO_MODE_OPTIONS: Final = {
    0: "disabled",
    1: "temperature",
    2: "chrono",
    3: "threshold_on_timeslot",
}

# --- behaviour ------------------------------------------------------------

#: The firmware only offers a *toggle*, so a power command is optimistic for a while.
OPTIMISTIC_POWER_WINDOW: Final = 90.0
#: Delay before re-reading the stove after a write, so the module has polled the board.
POST_WRITE_REFRESH_DELAY: Final = 2.0

SERVICE_SET_REGISTER: Final = "set_register"
ATTR_MEMORY: Final = "memory"
ATTR_REGISTER: Final = "register"
ATTR_VALUE: Final = "value"
