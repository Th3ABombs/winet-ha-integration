# WiNET local HTTP protocol (reverse engineered)

Device: **WiNET** Wi-Fi module by *Net Software S.r.l.* (`Server: NetSoftware-httpd/0.3`),
bridging a Micronova-style pellet stove controller to Wi-Fi.
Reversed from `management.html`, `management.js`, `status.js` and live read-only probing of
firmware **0.79**, `model = 0`, `custom = 65535` (default customization profile).

All responses are JSON. Responses are gzip-encoded, so send `Accept-Encoding: gzip`
(any normal HTTP client does).

There is **no authentication** on the local interface.

---

## Endpoints

| Method | Path | Nature | Purpose |
|---|---|---|---|
| GET/POST | `/ajax/get-status` | read-only | Wi-Fi / firmware / network diagnostics |
| POST | `/ajax/get-registers` | **mixed** | dispatcher keyed by `key=` (see below) |
| POST | `/ajax/set-register` | write | write one stove register |
| POST | `/ajax/reboot` | write | reboot the Wi-Fi module |
| POST | `/ajax/upgrade`, `/ajax/check-upg-sts` | write | firmware update |
| POST | `/ajax/start-pairing`, `/ajax/remove-ext-dev`, `/ajax/life-ext-dev` | write | ESP-NOW wireless sensor pairing |
| POST | `/ajax/set-ap-ip-base` | write | change AP subnet + reboot |

> ⚠️ `/ajax/get-registers` is **not** read-only despite its name. It is a generic command
> dispatcher: `key=022` toggles the stove on/off, `key=026` renames the device,
> `key=027` overwrites the module settings, `key=098` changes a display flag.
> Only `key=019` and `key=020` are pure reads.

Bodies are `application/x-www-form-urlencoded`. (The web UI declares
`Content-Type: application/json` but jQuery actually serializes a plain object as a form
body; the firmware only parses the form body.)

### `key=019` — module configuration (read)

`POST /ajax/get-registers` with `key=019`

```json
{"key":"019","fwUpdate":false,"tempDiv":0.5,"setTempDiv":1,"numPower":5,"mode":0,
 "modeThreeshold":0,"model":0,"localWeb":1,"uart":[1200,2],"isForcedOld":false,
 "isOld":false,"custom":65535,"name":"NO NAME","tStart":20,"tStop":23,"weekDay":4,
 "mon":[0,0,0,0,0,0,0,0], "...":"tue..sun"}
```

* `tempDiv` — multiplier applied to the **measured** temperature register (0.5 here)
* `setTempDiv` — multiplier applied to the **setpoint** register (1 here)
* `numPower` — number of selectable power levels (5 here)
* `custom` — customization code; selects the status/alarm decoding table. `65535` = default
* `mode` — module-side auto start/stop: `0` disabled, `1` temperature, `2` chrono,
  `3` threshold temperature on time slot
* `uart` — `[baud, ?]` of the serial link to the stove board
* `mon`..`sun` — chrono time slots, 8 bytes/day (4 start/end pairs)

### `key=020` — runtime poll (read)

`POST /ajax/get-registers` with `key=020&category=<0..4>`

```json
{"key":"020",
 "params":[[0,55],[2,4],[3,0],[4,200],[50,10],[51,255],
           [59,0],[60,255],[61,0],[62,255],[63,0],[64,255],
           [300,0],[301,0],[302,0],[303,8]],
 "tsense":{"show":1,"list":[]},
 "cat":0,"signal":2,"logTemp":275,"tempDiv":0.5,"setTempDiv":1,"numPower":5,
 "mode":0,"modeThreeshold":0,"tStart":20,"tStop":23,"model":0,"isOld":true,
 "custom":65535,"name":"NO NAME","ssid":"MyWiFi","inetTime":[2026,8,27,15,47,0,0,4]}
```

`params` is a list of `[registerId, rawValue]`. The returned set is fixed by the firmware;
`category` does **not** change it on this model (values > 4 are clamped).
`logTemp` is the measured temperature ×10 (275 → 27.5 °C), i.e. redundant with register 0.

`tsense.list` entries are `[id, name, temperature, battery(0..3), zone]`, where zone is
`0 STANDBY / 1 AIR FRONT / 2 CAN 1 / 3 CAN 2`. Empty when no ESP-NOW sensor is paired.

`inetTime` is `[year, month, day, hour, minute, ?, ?, weekday]`.

### `key=022` — ⚠️ toggle stove on/off (write)

`POST /ajax/get-registers` with `key=022` → `{"result":true}`

This is `App.ChangeStatus()`, bound to the power button. It is a **toggle with no
argument** — the firmware decides the right register sequence for the stove model.
The web UI gates it behind a confirmation dialog and refuses to turn the stove *on*
while status is *final cleaning*; over raw HTTP there is no such guard.

### `key=026` — rename device (write)

`key=026&name=<str>&customCode=<int>`

### `key=027` — save module settings (write)

`key=027&tempDiv=&setTempDiv=&numPower=&mode=&modeThreshold=&days=127&tStart=&tStop=`
plus 56 chrono fields `d<1..7>f<1..4>{s,e}`. Triggers a page reload in the UI.

### `key=098` — tsense visibility flag (write)

`key=098&visible=0|1`

### `key=002` — write a stove register (write)

`POST /ajax/set-register` with `key=002&memory=<0|1>&regId=<n>&value=<raw>`

* `memory` — `0` = volatile (RAM), `1` = persistent (EEPROM). Setpoints use `1`.
* `value` — the **raw** register byte, i.e. `(displayed - offset) / mul`.

### `/ajax/get-status` — module diagnostics (read)

```json
{"status":5,"fwUpdate":false,"apConnected":1,"lastDisconnectReason":201,
 "lastCloudError":0,"currentApIp":"192.168.10.1","currentIp":"192.168.1.148",
 "currentMask":"255.255.255.0","currentGw":"192.168.1.1",
 "inetTime":"2026-08-27 15:51","inetWeekDay":4,"client":2,"network":"MyWiFi",
 "signal":2,"rssi":-96,"eNowDevs":[],"show":1,"pairing":0,"timeout":0,
 "fwVer":"0.79","boot":1}
```

No MAC address is exposed by any local endpoint, so the integration keys its unique ID
off the host. Give the module a static DHCP lease.

---

## Registers (default profile, `custom = 65535`)

| Reg | Memory | Meaning | Encoding |
|---|---|---|---|
| 0 | 0 (r/o) | Measured temperature | `raw × tempDiv` °C, 1 decimal |
| 2 | — | **Status** | see table below |
| 3 | — | **Alarm bitmask** | see table below |
| 4 | 0 (r/o) | **Flue gas temperature** | `raw + 30` °C (`mul=1, offset=30`, range 30–285) |
| 50 | 1 | Target temperature | `raw × setTempDiv` °C, UI range 5–40 |
| 51 | 1 | Target power level | `1..numPower`; `255` = not available |
| 59 | 1 | Stove clock: weekday | `1..7` |
| 60 | 1 | Stove clock: hour | BCD (`0x23` = 23) |
| 61 | 1 | Stove clock: minute | BCD (`0x59` = 59) |
| 62 | 1 | Stove clock: day | `1..31` |
| 63 | 1 | Stove clock: month | `1..12` |
| 64 | 1 | Stove clock: year | `raw + 2000` |
| 300–303 | — | unknown, module-internal — **not** board registers | `303` was `8` while running, `0` when off |

Register 4's offset is not a quirk of one customization profile: **30…285 inclusive is
exactly 256 values**, i.e. one byte. The module shifts the reading by 30 °C to gain
headroom above 255 °C, which a plain byte cannot express. Every profile in
`management.js` that defines a control for register 4 uses `offset=30`; the default
profile defines none, which is why the local page never shows it.

Register 4's offset explains an otherwise suspicious reading: it is `0` on a stove that is
off, while the room sits at 27.5 °C. With the offset applied that is 30 °C — a cold probe,
not a missing value. Observed `200` (= 230 °C) while the stove was burning.

Registers 59–64 read back `0`/`255` alternately on this stove, i.e. the board reports no
clock. Registers 300–303 are never referenced by `management.js`; they are exposed as
disabled-by-default diagnostic entities so they can be identified by observation.

### Registers the firmware knows but this module does not send

`management.js` defines parameter controls for many more registers than `key=020`
returns, and labels them via `txt_p<register>` keys. They are listed here because the
obvious question — "can I read the flue pressure?" — deserves a precise answer. The
`key=020` set is fixed by the firmware and there is no arbitrary-read endpoint, so these
registers are unreachable *through `/ajax`*. Some of them are reachable through the
separate REST API documented below.

| Reg | Label | Sent by this module? |
|---|---|---|
| 1 | Water temperature | not via `/ajax`; **`/api/global` has `water`** |
| 4 | **Flue gas temperature** | **yes** |
| 5, 8 | Flow (air flow meter) | no — and not in `/api` either |
| 6 | Water pressure | no — and not in `/api` either |
| 7 | Remote control temperature | no |
| 10 | Flue extractor (fan speed) | not via `/ajax`; **`/api/global` has `rpmExtractor`** |
| 11, 12 | Buffer tank / heater temperature | no |
| 13 | Real power | no — and not in `/api` either |
| 32, 33 | Buffer tank bottom / top temperature | no |
| 34–36 | Pellet mode, eco/standby, season | no |
| 37–39, 49, 52 | Pump / boiler / buffer / DHW setpoints | no |
| 40, 41, 47, 48 | Ducting channel 1 & 2 setpoints | no |
| 42 | Selected probe | no |
| 43, 44 | Pellet / air percentage | no |
| 45, 46 | Fan enable / fan setpoint | no |

Most of these belong to hydronic (`idro`) stoves. On the reference unit — an air stove,
`model = 0` — only register 4 from this list is actually served.

There is **no analogue depression reading**. The board signals a failed draught through
alarm bit 5 ("no pressure"), i.e. a pressure switch, not a transducer.

The register-to-meaning mapping and the UI limits come from the `<label class="parameter">`
attributes in `management.html`:
`memory`, `reg`, `regtype`, `mul`, `offset`, `unit`, `min`, `max`, `delta`, `decimals`,
`mask`, `shift`, `view`.

### Status — register 2

| Value | Italian (firmware) | Meaning |
|---|---|---|
| 0 | OFF | off |
| 1 | ATTESA FIAMMA | waiting for flame |
| 2 | ATTESA FIAMMA | waiting for flame |
| 3 | ACCENSIONE | igniting |
| 4 | LAVORO | running |
| 5 | PULIZIA BRACIERE | brazier cleaning |
| 6 | PULIZIA FINALE | final cleaning (shutting down) |
| 7 | STAND-BY | standby |
| 8 | ALLARME | alarm |
| 9 | MEMORIA ALLARME | alarm memory |
| 200 | LAVORO (MODULA) | *virtual*: status 4 **and** measured ≥ setpoint |

Derived by the UI: "on" means `status != 0`. Work status is `4`.
`StoveIsFinalCleaning` is `status == 6`.

Other `custom` codes select different tables (`msg_status_rav_*` for 5619/5620/5623/5629,
`msg_status_jmec_idea_*` for 5952–5954, with different work/final-cleaning values and
alarms at 10/11 instead of 8/9). This integration implements the default table and falls
back to `unknown` elsewhere.

### Alarm — register 3, bitmask

| Bit | Italian (firmware) |
|---|---|
| 0 | Guasto sonda fumi |
| 1 | Sovratemperatura fumi |
| 2 | Malfunzionamento estrattore |
| 3 | Mancata accensione |
| 4 | Mancanza pellet |
| 5 | Mancanza pressione |
| 6 | Sicurezza termica |
| 7 | Vano pellet aperto |

The firmware displays only the lowest set bit. The alarm box is shown only while
status is `8` or `9`.

---

## Polling

The web UI polls `key=020` every **750 ms** with a single-request queue. Anything from a
few seconds upward is comfortable; this integration defaults to 15 s.

---

## Cross-check against the ESPHome `micronova` component

[ESPHome's `micronova` component](https://esphome.io/components/micronova/) speaks the
raw serial protocol to the same family of boards — 1200 baud, 8N2, which is exactly what
this module reports in `key=019` as `"uart":[1200,2]`. It is an independent
reverse engineering effort, so it is worth comparing against.

**The status table is independently confirmed.** ESPHome's `STOVE_STATES`:

| Code | ESPHome | WiNET firmware | |
|---|---|---|---|
| 0 | Off | OFF | ✅ |
| 1 | Start | ATTESA FIAMMA | same phase |
| 2 | Pellets loading | ATTESA FIAMMA | same phase |
| 3 | Ignition | ACCENSIONE | ✅ |
| 4 | Working | LAVORO | ✅ |
| 5 | Brazier Cleaning | PULIZIA BRACIERE | ✅ |
| 6 | Final Cleaning | PULIZIA FINALE | ✅ |
| 7 | Standby | STAND-BY | ✅ |
| 8 | No pellets alarm | ALLARME | alarm |
| 9 | No ignition alarm | MEMORIA ALLARME | alarm |

Two independently derived tables agree on every phase. The naming of 1/2 and 8/9 differs
because the two projects read different things: ESPHome names the alarm *cause*, while
this module keeps the cause separately in register 3.

**WiNET register ids are an abstraction, not raw addresses.** ESPHome addresses the board
directly and its defaults do not line up with the ids this module publishes:

| Value | ESPHome (location, address) | WiNET reg |
|---|---|---|
| Room temperature | `0x00`, `0x01`, divisor 2 | 0 (`tempDiv` 0.5 — same scaling) |
| Flue gas temperature | `0x00`, `0x5A` | 4 |
| Stove power | `0x00`, `0x34` | 13 ("real power", not served) |
| Fan speed | `0x00`, `0x37` | 10 ("flue extractor", not served) |
| Water temperature | `0x00`, `0x3B`, divisor 2 | 1 (not served) |
| Water pressure | `0x00`, `0x3C`, divisor 10 | 6 (not served) |
| Thermostat temperature | `0x20`, `0x7D` | 50 |

So the `regId` accepted by `/ajax/set-register` cannot be treated as a Micronova memory
address, and the module's `memory` field (0/1) is its own abstraction over the protocol's
`0x00`/`0x20` locations.

Note that ESPHome reads the flue gas temperature with **no offset**, while this module
applies `+30`. Both are consistent: the module re-packs the board's value into a byte
spanning 30–285 °C, as the exact 256-value range shows.

**Registers 300–303 cannot be board registers at all.** ESPHome declares the protocol's
address field as `uint8_t memory_address`, so a Micronova address is one byte: 0–255.
Ids in the 300s are outside that space by construction, and they carry no `txt_p<n>`
label. `management.js` never reads them either — the only numeric matches for 299–304 in
the module's whole JavaScript bundle are a jQuery HTTP status check (`e < 300`) and an
Ajax timeout (`a < 3000`).

They are therefore values the module computes or holds itself, published for a consumer
that is not the local web page — most plausibly the vendor's cloud/mobile app, which
reaches the same dispatcher through `default.aspx/PostAction` with the same `key` codes.
What they mean is still open: on the reference stove 300–302 read `0` throughout, while
303 read `8` during a burn and `0` once the stove reached OFF.

**No draught sensor exists on either side.** ESPHome exposes water *pressure* (hydronic
circuit) and no depression reading; this module reports a failed draught only as alarm
bit 5. On these boards the draught is monitored by a pressure switch, not a transducer.

**If you need the values neither interface serves** — air flow, water pressure, real
power — the ESPHome component can read arbitrary `memory_location`/`memory_address` pairs
over the same serial link. That means tapping the board's serial connector directly:
neither of the WiNET's HTTP interfaces has an arbitrary-read endpoint.

---

## The second interface: `/api/`

The module also serves a REST API that its own local web page never calls, so it does not
appear anywhere in `management.js`. It exists on firmware 0.79 and was found by reading
the [HASS_WINET](https://github.com/morenonew2/HASS_WINET) project, which uses it
exclusively. Both interfaces are live at the same time and agree with each other.

### `GET /api/global` — decoded runtime state (read)

```json
{"status":0,"description":"OFF","gasflue":0,"rpmExtractor":null,
 "air":55,"setAir":20,"water":null,"setWater":null,"power":255}
```

| Field | Meaning | `/ajax` equivalent |
|---|---|---|
| `status` | status code | register 2 |
| `description` | **status decoded by the firmware** | — (we decode register 2 ourselves) |
| `gasflue` | flue gas temperature, raw | register 4 |
| `rpmExtractor` | extractor fan speed, `null` when unsupported | register 10, not served by `key=020` |
| `air` | measured air temperature, raw | register 0 |
| `setAir` | ⚠️ **not the stove setpoint** — see below | — |
| `water`, `setWater` | hydronic values, `null` on an air stove | registers 1 / 49, not served by `key=020` |
| `power` | power setpoint (`255` = not set) | register 51 |

> ⚠️ **`setAir` is not the temperature setpoint.** On the reference stove `setAir` reads
> 20 while register 50 reads 10, and the module's own web page displays **10 °C** as the
> set point — so register 50 is authoritative. `setAir` matches `tStart` from `key=019`,
> the module's *auto start/stop* threshold. Anything driving a thermostat from `setAir`
> is writing to the wrong concept. This integration uses register 50.

`rpmExtractor`, `water` and `setWater` are `null` on the reference stove because the
board does not report them, not because the API lacks them. On a hydronic stove they
should carry values.

### `GET /api/id` — identity (read)

```json
{"id":"WiNET Gen.Stove","mac":"XXXXXXXXXXXX","apSsid":"WINET-XXXXXXXX",
 "apWpaPwd":"XXXXXXXX","staSsid":"..."}
```

This is the only local endpoint that exposes the **MAC address**, which is what a stable
device identity should key off. The MAC's OUI is Espressif's, confirming the module is
ESP32-based — consistent with its ESP-NOW support, its dual boot partitions (`boot` in
`/ajax/get-status`) and its OTA endpoint.

> ⚠️ `apWpaPwd` is the module's **access-point WPA password**, served without
> authentication. Do not paste `/api/id` output into issues or forums.

### Write endpoints — do not probe these

`GET /api/status/0` and `/api/status/1` turn the stove **off and on**. `/api/power/…`,
`/api/temperature/air/…`, `/api/temperature/water/…`, `/api/global/season/…` and
`/api/rele/<n>/status/<0|1>` are likewise setters expressed as path segments, so a
casually "GET-ing around" probe of this API actuates hardware. `GET /api/` on its own
returns `{"result":false}`.

This integration **uses** the `/api` interface where it is better, and keeps `/ajax`
where `/ajax` is better:

| Concern | Interface used | Why |
|---|---|---|
| Identity | `/api/id` | only local source of the MAC |
| On/off | `/api/status/<1\|0>` | **absolute**, where `key=022` is a blind toggle |
| Extractor speed, hydronic readings | `/api/global` | `key=020` never serves them |
| Status, alarms, temperatures, scaling | `key=020` | `/api/global` carries no alarm and no `tempDiv`/`setTempDiv` |
| Temperature and power setpoints | `/ajax/set-register` | the register encoding is documented by the module's own JS; `/api/temperature/air/<n>` has an unverified unit — one project scales it by ×2 |

`/api/global` is polled alongside `key=020`. If it fails once the integration stops asking
and carries on without those readings, so a firmware that lacks the interface still works.
