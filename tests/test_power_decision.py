"""Exhaustive tests for the on/off decision.

The module exposes only a *toggle*, so a wrong decision here lights a stove that should
stay off. Every status the default customization table can report is covered explicitly.
"""

from __future__ import annotations

import pytest
from winet_pure.const import (
    STATUS_ALARM,
    STATUS_ALARM_MEMORY,
    STATUS_BRAZIER_CLEANING,
    STATUS_FINAL_CLEANING,
    STATUS_IGNITION,
    STATUS_OFF,
    STATUS_STANDBY,
    STATUS_WAIT_FLAME_1,
    STATUS_WAIT_FLAME_2,
    STATUS_WORK,
    STATUS_WORK_MODULATING,
)
from winet_pure.model import PowerAction, decide_power_action

ALL_STATUSES = [
    STATUS_OFF,
    STATUS_WAIT_FLAME_1,
    STATUS_WAIT_FLAME_2,
    STATUS_IGNITION,
    STATUS_WORK,
    STATUS_BRAZIER_CLEANING,
    STATUS_FINAL_CLEANING,
    STATUS_STANDBY,
    STATUS_ALARM,
    STATUS_ALARM_MEMORY,
    STATUS_WORK_MODULATING,
]


@pytest.mark.parametrize("turn_on", [True, False])
def test_unknown_status_never_toggles(turn_on: bool) -> None:
    """A missing status must never produce a blind toggle."""
    assert decide_power_action(None, turn_on) is PowerAction.REFUSE_UNKNOWN


def test_turning_on_from_off_toggles() -> None:
    """The only case where an ignition may be commanded."""
    assert decide_power_action(STATUS_OFF, True) is PowerAction.TOGGLE


def test_turning_on_when_already_on_does_nothing() -> None:
    """No double toggle, which would shut the stove down instead."""
    for status in ALL_STATUSES:
        if status in (STATUS_OFF, STATUS_FINAL_CLEANING):
            continue
        assert decide_power_action(status, True) is PowerAction.NOTHING, status


def test_turning_on_during_final_cleaning_is_refused() -> None:
    """Matches the firmware, which shows 'wait for the OFF state'."""
    assert (
        decide_power_action(STATUS_FINAL_CLEANING, True)
        is PowerAction.REFUSE_WAIT_FOR_OFF
    )


def test_turning_off_when_already_off_does_nothing() -> None:
    """A redundant off must not toggle the stove *on*."""
    assert decide_power_action(STATUS_OFF, False) is PowerAction.NOTHING


def test_turning_off_during_final_cleaning_does_nothing() -> None:
    """The shutdown is already under way and cannot be hurried."""
    assert decide_power_action(STATUS_FINAL_CLEANING, False) is PowerAction.NOTHING


def test_turning_off_while_running_toggles() -> None:
    """Every 'on' phase, including ignition and alarm, accepts a shutdown."""
    for status in ALL_STATUSES:
        if status in (STATUS_OFF, STATUS_FINAL_CLEANING):
            continue
        assert decide_power_action(status, False) is PowerAction.TOGGLE, status


def test_alarm_can_be_cleared_with_an_off_command() -> None:
    """Pressing off is how a Micronova board acknowledges an alarm."""
    assert decide_power_action(STATUS_ALARM, False) is PowerAction.TOGGLE
    assert decide_power_action(STATUS_ALARM_MEMORY, False) is PowerAction.TOGGLE


def test_status_from_another_customization_table_is_treated_as_on() -> None:
    """An unmapped non-zero status is 'on', the same assumption the firmware makes."""
    assert decide_power_action(42, False) is PowerAction.TOGGLE
    assert decide_power_action(42, True) is PowerAction.NOTHING


def test_a_toggle_is_only_ever_produced_by_a_state_disagreement() -> None:
    """Property: TOGGLE implies the firmware disagrees with the request."""
    for status in [*ALL_STATUSES, 42, 255]:
        for turn_on in (True, False):
            if decide_power_action(status, turn_on) is PowerAction.TOGGLE:
                assert (status != STATUS_OFF) != turn_on, (status, turn_on)
