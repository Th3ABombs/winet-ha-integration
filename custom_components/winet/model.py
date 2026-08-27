"""Pure decoding of the WiNET payloads.

Kept free of Home Assistant imports so it can be unit-tested — and read — on its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import logging
from typing import Any

from .const import (
    ALARM_BIT_KEYS,
    ALARM_NONE_KEY,
    AUTO_MODE_OPTIONS,
    DEFAULT_NUM_POWER,
    FLUE_TEMP_OFFSET,
    RAW_UNAVAILABLE,
    REG_ALARM,
    REG_FLUE_TEMP,
    REG_MEASURED_TEMP,
    REG_STATUS,
    REG_TARGET_POWER,
    REG_TARGET_TEMP,
    STATUS_ALARMS,
    STATUS_FINAL_CLEANING,
    STATUS_KEYS,
    STATUS_OFF,
    STATUS_UNKNOWN_KEY,
    STATUS_WORK,
    STATUS_WORK_MODULATING,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class WinetData:
    """A decoded snapshot of one poll cycle."""

    registers: dict[int, int] = field(default_factory=dict)
    #: Status as reported by register 2, before the modulating substitution.
    raw_status: int | None = None
    #: Status after substituting 200 ("work, modulating") the way the firmware does.
    status: int | None = None
    temp_div: float = 1.0
    set_temp_div: float = 1.0
    num_power: int = DEFAULT_NUM_POWER
    custom_code: int = 0
    model: int = 0
    auto_mode: int | None = None
    device_name: str | None = None
    ssid: str | None = None
    signal: int | None = None
    tsense: list[list[Any]] = field(default_factory=list)
    module: dict[str, Any] = field(default_factory=dict)

    # --- from the secondary /api interface, absent on modules that lack it ---
    #: Status string decoded by the firmware itself, e.g. "OFF". Informational only:
    #: the entities decode register 2 so their wording stays under our control.
    firmware_status_text: str | None = None
    #: Extractor fan speed. ``None`` when the board does not report it.
    rpm_extractor: int | None = None
    #: Hydronic readings, raw. ``None`` on an air stove. The scale is unverified --
    #: see the note on the sensors -- so these are published unconverted.
    water_raw: int | None = None
    water_setpoint_raw: int | None = None
    #: Whether /api/global answered at all this cycle.
    api_available: bool = False

    @property
    def status_key(self) -> str:
        """Return the translation key for the current status."""
        if self.status is None:
            return STATUS_UNKNOWN_KEY
        return STATUS_KEYS.get(self.status, STATUS_UNKNOWN_KEY)

    @property
    def is_on(self) -> bool | None:
        """Return whether the stove is on *in the firmware's sense*.

        The web UI treats every status other than OFF as "on" — standby, final cleaning
        and alarm included — and the on/off toggle flips exactly that notion. The power
        command relies on this, so it must not be redefined.
        """
        if self.status is None:
            return None
        return self.status != STATUS_OFF

    @property
    def is_shutting_down(self) -> bool:
        """Return whether the stove is running its unstoppable shutdown cycle."""
        return self.status == STATUS_FINAL_CLEANING

    @property
    def is_heat_on(self) -> bool | None:
        """Return whether the stove is on *and* not already shutting down.

        This is what a thermostat should show: once the shutdown cycle starts the user's
        intent is "off", even though the firmware still calls the stove on.
        """
        if self.status is None:
            return None
        return self.status != STATUS_OFF and not self.is_shutting_down

    @property
    def measured_temperature(self) -> float | None:
        """Return the measured temperature in °C."""
        raw = self.registers.get(REG_MEASURED_TEMP)
        if raw is None:
            return None
        return round(raw * self.temp_div, 1)

    @property
    def flue_gas_temperature(self) -> float | None:
        """Return the flue gas temperature in °C.

        Register 4 is offset by 30 °C, so a raw 0 is a cold probe at 30 °C rather than a
        missing reading — which is why the register reads 0 on a stove that is off.
        """
        raw = self.registers.get(REG_FLUE_TEMP)
        if raw is None:
            return None
        return float(raw + FLUE_TEMP_OFFSET)

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature setpoint in °C."""
        raw = self.registers.get(REG_TARGET_TEMP)
        if raw is None or raw == RAW_UNAVAILABLE:
            return None
        return round(raw * self.set_temp_div, 1)

    @property
    def target_power(self) -> int | None:
        """Return the power setpoint (1..num_power), or None if not reported."""
        raw = self.registers.get(REG_TARGET_POWER)
        if raw is None or raw == RAW_UNAVAILABLE or not 1 <= raw <= self.num_power:
            return None
        return raw

    @property
    def alarm_code(self) -> int | None:
        """Return the raw alarm bitmask."""
        return self.registers.get(REG_ALARM)

    @property
    def active_alarms(self) -> list[str]:
        """Return the translation keys of every set alarm bit."""
        code = self.alarm_code
        if not code:
            return []
        return [key for bit, key in enumerate(ALARM_BIT_KEYS) if code & (1 << bit)]

    @property
    def alarm_key(self) -> str:
        """Return the alarm to display.

        The firmware shows only the lowest set bit, so we do the same.
        """
        active = self.active_alarms
        return active[0] if active else ALARM_NONE_KEY

    @property
    def has_alarm(self) -> bool:
        """Return whether the stove is in an alarm condition."""
        return bool(self.alarm_code) or self.status in STATUS_ALARMS

    @property
    def auto_mode_key(self) -> str | None:
        """Return the translation key of the module-side auto start/stop mode."""
        if self.auto_mode is None:
            return None
        return AUTO_MODE_OPTIONS.get(self.auto_mode)


def decode(
    runtime: dict[str, Any],
    module: dict[str, Any],
    api_global: dict[str, Any] | None = None,
) -> WinetData:
    """Turn the JSON payloads into a :class:`WinetData`.

    ``api_global`` is the optional ``/api/global`` body; modules without that interface
    simply pass ``None`` and lose only the readings unique to it.
    """
    registers: dict[int, int] = {}
    for entry in runtime.get("params") or []:
        if isinstance(entry, (list, tuple)) and len(entry) >= 2:
            try:
                registers[int(entry[0])] = int(entry[1])
            except (TypeError, ValueError):
                _LOGGER.debug("Skipping malformed register entry %r", entry)

    tsense = runtime.get("tsense") or {}
    data = WinetData(
        registers=registers,
        temp_div=_as_float(runtime.get("tempDiv"), 1.0),
        set_temp_div=_as_float(runtime.get("setTempDiv"), 1.0),
        num_power=(
            _as_int(runtime.get("numPower"), DEFAULT_NUM_POWER) or DEFAULT_NUM_POWER
        ),
        custom_code=_as_int(runtime.get("custom"), 0) or 0,
        model=_as_int(runtime.get("model"), 0) or 0,
        auto_mode=_as_int(runtime.get("mode"), None),
        device_name=runtime.get("name"),
        ssid=runtime.get("ssid") or module.get("network"),
        signal=_as_int(runtime.get("signal"), None),
        tsense=tsense.get("list") or [],
        module=module,
    )

    if api_global:
        data.api_available = True
        data.firmware_status_text = api_global.get("description")
        data.rpm_extractor = _as_int(api_global.get("rpmExtractor"), None)
        data.water_raw = _as_int(api_global.get("water"), None)
        data.water_setpoint_raw = _as_int(api_global.get("setWater"), None)
        # Deliberately NOT read: `setAir`. It reports the module's own auto start/stop
        # threshold (tStart), not the stove's setpoint: on the reference stove it says
        # 20 while the web page shows the setpoint as the 10 held in register 50.

    raw_status = registers.get(REG_STATUS)
    data.raw_status = raw_status
    data.status = raw_status
    if raw_status == STATUS_WORK:
        measured = data.measured_temperature
        target = data.target_temperature
        if measured is not None and target is not None and measured >= target:
            data.status = STATUS_WORK_MODULATING

    return data


class PowerAction(Enum):
    """What :func:`decide_power_action` concluded should happen."""

    #: Send the on/off toggle.
    TOGGLE = "toggle"
    #: The stove is already where it should be; send nothing.
    NOTHING = "nothing"
    #: The board will refuse; tell the user instead of sending anything.
    REFUSE_WAIT_FOR_OFF = "refuse_wait_for_off"
    #: We do not know what the stove is doing, so we must not toggle blindly.
    REFUSE_UNKNOWN = "refuse_unknown"


def decide_power_action(status: int | None, turn_on: bool) -> PowerAction:
    """Decide whether the on/off toggle should be sent.

    The module offers no absolute power command, only a toggle, so getting this wrong
    means lighting a stove that should stay off. The rules mirror the web UI:

    * an unknown status must never be toggled — we would be guessing;
    * the board refuses to restart during the final cleaning cycle;
    * a shutdown request during that cycle is already satisfied;
    * otherwise toggle only if the firmware's on/off notion disagrees with the request.
    """
    if status is None:
        return PowerAction.REFUSE_UNKNOWN
    if status == STATUS_FINAL_CLEANING:
        return PowerAction.REFUSE_WAIT_FOR_OFF if turn_on else PowerAction.NOTHING
    is_on = status != STATUS_OFF
    return PowerAction.NOTHING if is_on == turn_on else PowerAction.TOGGLE


def _as_float(value: Any, default: float) -> float:
    """Coerce ``value`` to float, falling back to ``default``."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if result else default


def _as_int(value: Any, default: int | None) -> int | None:
    """Coerce ``value`` to int, falling back to ``default``."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
