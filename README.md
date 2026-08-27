# WiNET pellet stove — Home Assistant integration

A local-polling Home Assistant integration for **WiNET** Wi-Fi modules by
*Net Software S.r.l.*, the dongles that bridge a Micronova-style pellet stove
controller onto Wi-Fi.

Everything runs over the module's own HTTP interface on your LAN. No cloud, no account.

Developed and verified against firmware **0.79**, `model = 0`,
`custom = 65535` (the default customization profile).

> [!WARNING]
> **The write paths have never been run against a real stove.** Reading is verified
> against the device; the temperature and power setpoints and the on/off toggle are
> implemented from the reverse engineered protocol and have not been exercised. Watch
> the first ignition rather than automating it. See
> [How on/off works](#how-onoff-works-and-why-it-matters).

## What you get

| Entity | Notes |
|---|---|
| `climate` | On/off, temperature setpoint, measured temperature, `hvac_action` |
| `number` — Power level | Flame power 1…*n* (register 51) |
| `sensor` — Status | Enum: off, waiting for flame, igniting, running, running (modulating), brazier cleaning, final cleaning, standby, alarm, alarm memory |
| `sensor` — Alarm | Enum, decoded from the register-3 bitmask |
| `sensor` — Measured temperature, flue gas temperature, target temperature, power level | |
| `sensor` — Extractor fan speed | From `/api/global`; empty when the board does not report it |
| `sensor` — Water temperature / setpoint (raw) | Diagnostic, disabled by default — **unconverted**, see below |
| `sensor` — Module auto start/stop | The module's own thermostat/schedule mode (read-only) |
| `sensor` — Wi-Fi signal, RSSI, SSID, IP | Diagnostic; some disabled by default |
| `sensor` — Status code, alarm bitmask, `Register 300…303` | Diagnostic, disabled by default — see [Unknown registers](#unknown-registers) |
| `binary_sensor` — Alarm, Running, Module firmware update | |

Plus a `winet.set_register` service for writing raw registers (advanced).

## Install

### HACS

Add this repository as a custom repository of type *Integration*, install it, restart
Home Assistant, then **Settings → Devices & services → Add integration → WiNET**.

### Manual

Copy `custom_components/winet` into your Home Assistant `config/custom_components/`
directory and restart.

## Configure

You are asked for the module's host — for example `192.168.1.148`. A pasted
`http://192.168.1.148/management.html`-style URL is accepted too; only the host is kept.

Setup performs **reads only**: `/ajax/get-status` and `key=019`. Nothing is sent to the
stove board.

**Identifying the module.** Setup asks whether to key the device on its **MAC address**
or on the **IP/hostname**. The MAC is read from `/api/id` and survives a changed DHCP
lease, so it is the default. Choose the host if you prefer — or if your firmware does not
serve `/api/id`, in which case the host is used regardless and you will want a static
DHCP lease. Changing the choice later means removing and re-adding the integration.

Upgrading from a version that predates this keeps your entities and their history: the
config entry is migrated to the MAC and the entity registry is rewritten in the same
step.

On the reference installation the module sits at **-96 dBm** — right at the edge of
usable. If polls time out intermittently, that is the Wi-Fi link, not the integration.

The polling interval defaults to **15 s** and is configurable (5–300 s) under the
integration's *Configure* button. The module's own web app polls every 0.75 s, so short
intervals are not a problem for the hardware — but every poll makes the module talk to
the stove board over a 1200 baud serial link, so there is no point going below a few
seconds.

## How on/off works, and why it matters

The firmware exposes **no absolute power command**. There is only a *toggle*
(`key=022`), the same one behind the power button in the web UI — and over raw HTTP
there is no confirmation dialog in front of it.

So the integration:

1. reads the current status,
2. sends the toggle **only** if the stove is not already in the requested state,
3. refuses to turn the stove *on* while it is in *final cleaning*, exactly as the web UI
   does (the board will not restart mid-shutdown),
4. treats a shutdown request during *final cleaning* as a no-op,
5. shows the requested state optimistically for up to 90 s, then falls back to whatever
   the stove actually reports and logs a warning.

Commands are serialised behind a lock, so a double-tap in the UI or two automations
firing at once cannot produce two toggles that cancel each other out.

One deliberate divergence from the firmware: during the final cleaning cycle the firmware
still considers the stove "on". The `climate` entity reports **off** at that point,
because the cycle cannot be interrupted and the user's intent was off. The *Status*
sensor keeps reporting the real phase (`final_cleaning`), and the *Running* binary sensor
keeps the firmware's own notion.

## What the module does *not* report

The module's own JavaScript defines controls for many more registers than the `key=020`
poll actually serves — water temperature, air flow, water pressure, extractor RPM, real
power. Most belong to hydronic stoves. The full list is in
[`docs/PROTOCOL.md`](docs/PROTOCOL.md).

The module also serves a **second REST interface, `/api/`**, that its own web page never
calls. This integration uses it for the module's MAC, for the extractor and hydronic
readings, and — importantly — for on/off, because `/api/status/1` is an *absolute*
command where `/ajax`'s `key=022` is a blind toggle. Status, alarms and the temperature
scaling still come from `/ajax`, which is the only place they exist.

If a module does not serve `/api`, the integration notices on the first failed poll and
carries on without it, falling back to the toggle. `docs/PROTOCOL.md` has the split, and
a warning about which `/api` endpoints are setters that actuate the stove.

Air flow, water pressure and real power are served by neither interface.

In particular there is **no analogue draught/depression reading**: the board reports a
failed draught as alarm bit 5 ("no pressure"), which is a pressure switch, not a sensor.
The [ESPHome `micronova` component](https://esphome.io/components/micronova/), which
speaks the raw serial protocol to the same boards, has no such sensor either.

For what neither interface serves, ESPHome can read arbitrary memory addresses over the
same 1200 baud link — that means tapping the board's serial connector.
`docs/PROTOCOL.md` cross-checks the two projects and confirms this integration's status
table against ESPHome's, independently derived.

Flue gas temperature *is* available — register 4, offset by 30 °C — even though the
module's own local web page never displays it.

## Unknown registers

Registers **300–303** are reported but never referenced by the module's web app. On the
reference stove, 303 read `8` while running and `0` when off.

They are not board registers: the Micronova protocol addresses memory with a single byte,
so ids in the 300s cannot reach the stove's controller. They are values the module itself
computes or holds — which also means no amount of comparing against ESPHome will identify
them.

They are exposed as diagnostic sensors, **disabled by default**. Enable them and watch
the stove through an ignition/shutdown cycle to work out what they are — or use the
bundled read-only probe:

```bash
python3 tools/winet_probe.py 192.168.1.148 --watch 10 --csv stove.csv
```

That script only ever issues the two read requests; it has no code path that can reach
the toggle or a register write. If you identify a register, please open an issue.

Registers 59–64 are the stove's clock. On the reference stove they read `0`/`255`
alternately, i.e. the board reports no clock, so no entity is created for them.

## Readings this integration does not convert

`water` and `setWater` from `/api/global` are published **raw**, as diagnostic entities
disabled by default. They are `null` on the air stove this was developed against, so
their scale could not be verified — ESPHome divides the equivalent board reading by 2,
but whether `/api` has already applied that is unknown. Publishing an unconverted number
is better than a temperature entity that might be out by a factor of two. If you have a
hydronic stove and can compare against its display, please open an issue.

## The `winet.set_register` service

```yaml
action: winet.set_register
data:
  device_id: <your WiNET device>
  register: 51
  value: 3
  memory: 1   # 0 = RAM (volatile), 1 = EEPROM (persistent)
```

`value` is the **raw** register value, unscaled: for a temperature setpoint that means
`°C / setTempDiv`. Writing the wrong register can change your stove's configuration.
Use it for exploration, not for automations — the `climate` and `number` entities are the
supported path for setpoints.

## Other customization profiles

The module ships several status and alarm tables, selected by the `custom` code it
reports. This integration implements the default table (`custom = 65535`). On another
profile the numbers mean different things — the work status can be 5 or 7 instead of 4,
and alarms sit at 10/11 instead of 8/9. Statuses outside the default table are reported
as `unknown` rather than mislabelled. If you have such a module, its `custom` code and a
capture from `tools/winet_probe.py` are enough to add support; open an issue.

## Protocol

The local HTTP protocol, register map, status and alarm tables are documented in
[`docs/PROTOCOL.md`](docs/PROTOCOL.md), reverse engineered from the module's own
`management.js` / `status.js` plus read-only probing.

Worth knowing if you poke at the device yourself: **`/ajax/get-registers` is not
read-only despite its name.** It is a command dispatcher. `key=022` toggles the stove,
`key=026` renames it, `key=027` overwrites the module settings. Only `key=019` and
`key=020` are safe reads.

## Security

The module's local web interface has **no authentication**: anyone who can reach it on
your network can light your stove. Securing that — VLAN, firewall rules, whatever fits
your network — is out of scope for this integration.

## Tests

The decoding layer (`const.py` + `model.py`) has no Home Assistant dependencies and is
covered by unit tests built from real device captures:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-test.txt
.venv/bin/python -m pytest tests -q
.venv/bin/ruff check custom_components tests tools
```

The suite covers the register decoding against real device captures
(`tests/fixtures/`) and, exhaustively, the on/off decision for every status the default
customization table can report — the one place where a mistake lights a stove that
should stay off.

## Not implemented

* the module's own scheduler and auto start/stop mode (`key=027`) — exposed read-only
* ESP-NOW wireless temperature sensors (`tsense`) — none available to test against
* module reboot, firmware upgrade, Wi-Fi/AP reconfiguration
* renaming the device on the module (`key=026`)

## License

MIT — see [`LICENSE`](LICENSE).
