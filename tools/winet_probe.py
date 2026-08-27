#!/usr/bin/env python3
"""Read-only probe for a WiNET module.

Polls the two read endpoints and prints a decoded snapshot, so you can watch which
registers move while the stove changes phase. Useful for identifying register 4 and
300-303, whose meaning the module's own web app never uses.

    python3 tools/winet_probe.py 192.168.1.148
    python3 tools/winet_probe.py 192.168.1.148 --watch 10 --csv log.csv

This script never writes: it only ever sends ``key=019`` and ``key=020`` plus
``/ajax/get-status``. It deliberately has no code path that can reach ``key=022``
(the on/off toggle) or ``/ajax/set-register``.
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import csv
import datetime as dt
import gzip
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

STATUS_NAMES = {
    0: "OFF",
    1: "WAIT FLAME",
    2: "WAIT FLAME",
    3: "IGNITION",
    4: "WORK",
    5: "BRAZIER CLEANING",
    6: "FINAL CLEANING",
    7: "STANDBY",
    8: "ALARM",
    9: "ALARM MEMORY",
}

ALARM_BITS = (
    "flue gas probe failure",
    "flue gas overtemperature",
    "extractor malfunction",
    "ignition failure",
    "out of pellets",
    "no pressure",
    "thermal safety",
    "pellet compartment open",
)

REGISTER_NAMES = {
    0: "measured temp (raw)",
    2: "status",
    3: "alarm bitmask",
    4: "unknown",
    50: "target temp (raw)",
    51: "target power",
    59: "clock weekday",
    60: "clock hour (BCD)",
    61: "clock minute (BCD)",
    62: "clock day",
    63: "clock month",
    64: "clock year",
}


def _post(host: str, path: str, fields: dict[str, object] | None) -> dict:
    """POST a form body and return the decoded JSON object."""
    url = f"http://{host}{path}"
    body = urllib.parse.urlencode(fields).encode() if fields else b""
    request = urllib.request.Request(
        url, data=body, headers={"Accept-Encoding": "gzip"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = response.read()
        if response.headers.get("Content-Encoding") == "gzip":
            payload = gzip.decompress(payload)
    return json.loads(payload.decode("utf-8", "replace"))


def read_snapshot(host: str) -> tuple[dict, dict]:
    """Return (runtime, module_status). Both are pure reads."""
    return _post(host, "/ajax/get-registers", {"key": "020", "category": 0}), _post(
        host, "/ajax/get-status", None
    )


def read_config(host: str) -> dict:
    """Return the module configuration (pure read)."""
    return _post(host, "/ajax/get-registers", {"key": "019"})


def describe(runtime: dict, module: dict) -> str:
    """Render one snapshot as a human-readable block."""
    registers = {int(reg): int(value) for reg, value in runtime.get("params", [])}
    temp_div = float(runtime.get("tempDiv") or 1)
    set_div = float(runtime.get("setTempDiv") or 1)
    status = registers.get(2)
    alarm = registers.get(3) or 0
    active = [name for bit, name in enumerate(ALARM_BITS) if alarm & (1 << bit)]

    lines = [
        f"{dt.datetime.now():%H:%M:%S}  "
        f"status={status} ({STATUS_NAMES.get(status, '?')})  "
        f"measured={registers.get(0, 0) * temp_div:.1f}°C  "
        f"target={registers.get(50, 0) * set_div:.1f}°C  "
        f"power={registers.get(51)}  "
        f"alarm=0x{alarm:02X} {active or ''}",
    ]
    unknown = {
        reg: value for reg, value in registers.items() if reg not in REGISTER_NAMES
    }
    lines.append(
        "          registers: "
        + "  ".join(f"{reg}={value}" for reg, value in sorted(registers.items()))
    )
    if unknown:
        lines.append(
            "          undocumented: "
            + "  ".join(f"{reg}={value}" for reg, value in sorted(unknown.items()))
        )
    lines.append(
        f"          wifi: {module.get('network')} signal={module.get('signal')} "
        f"rssi={module.get('rssi')}dBm  fw={module.get('fwVer')}"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("host", help="IP or hostname of the WiNET module")
    parser.add_argument(
        "--watch",
        type=float,
        metavar="SECONDS",
        help="poll repeatedly at this interval instead of once",
    )
    parser.add_argument("--csv", metavar="FILE", help="append every register to a CSV")
    parser.add_argument("--json", action="store_true", help="print the raw payloads")
    args = parser.parse_args(argv)

    try:
        config = read_config(args.host)
    except (urllib.error.URLError, OSError, ValueError) as err:
        print(f"Cannot read {args.host}: {err}", file=sys.stderr)
        return 1

    print(
        f"WiNET at {args.host}: name={config.get('name')!r} "
        f"model={config.get('model')} custom={config.get('custom')} "
        f"tempDiv={config.get('tempDiv')} setTempDiv={config.get('setTempDiv')} "
        f"numPower={config.get('numPower')} uart={config.get('uart')}"
    )
    if config.get("custom") != 65535:
        print(
            "  ! This module uses a non-default customization profile; the status and "
            "alarm names above may not apply.",
            file=sys.stderr,
        )
    print()

    with ExitStack() as stack:
        writer = None
        csv_file = None
        if args.csv:
            csv_file = stack.enter_context(
                Path(args.csv).open("a", newline="", encoding="utf-8")
            )
            writer = csv.writer(csv_file)
        return _loop(args, writer, csv_file)


def _loop(args, writer, csv_file) -> int:
    """Poll until interrupted, or once if --watch was not given."""
    try:
        while True:
            runtime, module = read_snapshot(args.host)
            if args.json:
                print(json.dumps({"runtime": runtime, "status": module}, indent=2))
            else:
                print(describe(runtime, module))
            if writer is not None:
                registers = dict(runtime.get("params", []))
                if csv_file.tell() == 0:
                    writer.writerow(["timestamp", *sorted(registers)])
                writer.writerow(
                    [
                        dt.datetime.now().isoformat(timespec="seconds"),
                        *(registers[reg] for reg in sorted(registers)),
                    ]
                )
                csv_file.flush()
            if not args.watch:
                return 0
            time.sleep(args.watch)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
