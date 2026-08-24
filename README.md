# SPARTACUS Control Center

**Linux control suite for the DeepCool SPARTACUS 360 / 420 AIO cooler** — a hardware-verified Rust daemon implementing the reverse-engineered USB protocol, plus a PyQt6 desktop app with live telemetry, fan-curve automation, ARGB lighting and a **Theme Studio** for designing 480×480 screens that the daemon renders natively.

Everything shown on the panel or in the UI flows through one validated telemetry pipeline: bad sensors show `--`, never fake zeros; spikes are filtered; stale data is labelled.

---

## Table of contents

1. [What can it do?](#what-can-it-do)
2. [Hardware support](#hardware-support)
3. [Quick start](#quick-start)
4. [Installation](#installation)
5. [Uninstallation](#uninstallation)
6. [Using the app](#using-the-app)
7. [Theme engine](#theme-engine) · [Built-in themes](#built-in-themes) · [Theme spec format](#theme-spec-format) · [Bindings reference](#bindings-reference)
8. [Theme Studio](#theme-studio)
9. [Telemetry quality system](#telemetry-quality-system)
10. [Files & formats](#files--formats)
11. [IPC API reference](#ipc-api-reference)
12. [Architecture](#architecture)
13. [Protocol summary](#protocol-summary)
14. [Safety invariants](#safety-invariants)
15. [Building from source](#building-from-source) · [Tests](#tests)
16. [Troubleshooting](#troubleshooting)

---

## What can it do?

### Monitor

- Live CPU / GPU temperature, usage and frequency; RAM used/total; disk usage; network up/down rates
- Pump, AIO-fan and EXT1/EXT2 RPM read from the Linker controller (~2 Hz passive polls that can never change fan speeds as a side effect)
- Per-metric quality badges everywhere: `47°C ● GOOD (83 ms)` — latency included

### Cool

- Manual duty **sliders** for Pump / AIO / EXT1 / EXT2 (hard 40 % pump floor)
- Per-channel fan **curves**: drag points on a temperature → PWM graph, apply them to the daemon, which stores them (`~/.config/spartacus/curves.toml`), restores them at boot and evaluates them every second
- Automatic ↔ manual arbitration: moving a slider pauses the curve loop; applying a curve resumes it — they never fight

### Light

- Static color, Rainbow and Breathing effects with color picker, speed and saturation
- One-click **Motherboard ARGB sync** (and reclaiming software control)

### Design & display

- **Theme engine (Rust)** — the daemon renders the panel natively, continuously, at cards quality: stamped-circle arcs, ring gauges, progress bars, rounded panels, antialiased text, gradients. No frame streaming needed; the design *runs* on the daemon
- **Seven built-in themes**: `cards`, `cards-light`, `colorful`, `rings` (classic Rust layouts) plus **`neon`**, **`aurora`**, **`slate`** — three modern data-driven designs
- **Theme Studio** — design your own screen with the exact primitives the Rust renderer draws (panels, rings, bars, text, shapes), with live telemetry in the preview, then **APPLY TO DAEMON**: your design is saved and rendered natively, permanently
- Theme choice survives reboots; custom themes live in `~/.config/spartacus/themes/`

### Trust

- 48 Python + 16 Rust tests including golden-vector checksum tests and a full-stack test that runs the real GUI against a mock daemon
- Verified end-to-end on real hardware

---

## Hardware support

- **DeepCool SPARTACUS 360** (360 mm) and **SPARTACUS 420** (420 mm)

The pump cap enumerates as two independent USB devices:

Device

VID:PID

Transport

Function

Display Controller

`3633:0027`

Vendor bulk

480×480 circular LCD

Fan & Lighting "Linker"

`3633:002d`

HID interrupt

Pump/fans PWM, ARGB lighting, tachometry

> ⚠️ The product ID `002d` must be written **lowercase** in udev rules — sysfs reports hex lowercase and udev matching is case-sensitive. The official DeepCool software must not be running; it holds the devices.

---

## Quick start

One command — builds, installs, sets up USB permissions, registers the
daemon as a systemd **user** service (auto-starts on login) and creates
a menu launcher:

```bash
git clone https://github.com/nerdjb/spartacus-control-center.git
cd spartacus-control-center
./scripts/setup.sh
```

Then open **Spartacus Control Center** from your app menu (or run
`spartacus-control-center`). You should see `● Connected` /
`Pipeline LIVE` in the top bar and the dashboard on the pump LCD.

<details>
<summary>Manual / from-source run (no installation)</summary>

```bash
./scripts/build.sh                      # builds the Rust daemon
cd src/daemon && cargo run --release    # terminal 1 — daemon
cd src/gui && python3 main.py           # terminal 2 — GUI
```

USB permissions (one time): `sudo cp packaging/99-spartacus.rules /etc/udev/rules.d/ && sudo udevadm control --reload-rules && sudo udevadm trigger`
</details>

**Uninstall:** `./scripts/uninstall.sh --user` (add `--purge --user` to also wipe themes/curves).

## Installation

### Arch Linux (PKGBUILD)

```bash
cd packaging && makepkg -si
sudo systemctl --user enable --now spartacus-daemon.service
```

### install.sh (any distro)

```bash
cargo build --release                   # inside src/daemon
sudo ./scripts/install.sh               # /usr/bin + /usr/share/spartacus + udev + service
```

### User-local (no sudo)

`./scripts/setup.sh` does exactly this for you (plus service + launcher).
Runtime requirements: `libusb-1.0`, Python ≥ 3.11, `PyQt6`, `Pillow`.

### Uninstallation

**Stop it first** (whatever applies):

```bash
systemctl --user disable --now spartacus-daemon.service   # if installed as a service
pkill -f spartacus-daemon                                 # or any manually started daemon
```

**Installed via PKGBUILD (Arch):**

```bash
sudo pacman -Rns spartacus-control-center
```

**Installed via install.sh — use the matching uninstaller:**

```bash
sudo ./scripts/uninstall.sh            # removes program files, keeps your data
sudo ./scripts/uninstall.sh --purge    # also wipes configs, themes and caches
```

**User-local install (~/.local):**

```bash
rm -f  ~/.local/bin/spartacus-daemon ~/.local/bin/spartacus-control-center
rm -rf ~/.local/share/spartacus
```

**Wipe user data & caches (all methods):**

```bash
rm -rf ~/.config/spartacus     # fan curves (curves.toml), themes, theme selection
rm -f  ~/.config/Spartacus/ControlCenter.conf   # GUI window preferences
sudo rm -rf /etc/spartacus     # system daemon config, if present
```

After removal the panel reverts to the DeepCool logo within ~15 s and the pump runs on the motherboard/firmware default curve — no daemon-side state remains on the device except brightness/orientation stored in panel NVM (change them once in Settings before uninstalling if you care).

---

## Using the app

The window is a sidebar (pages) plus a top bar of status pills:

Indicator

Meaning

`● Connected` / `● Disconnected`

GUI ↔ daemon IPC link

`Daemon Active`

daemon process reachable

`Pipeline LIVE` / `STALE`

validated telemetry fresh (< 2 s) or not

### Overview

Twelve metric cards (CPU temp/usage/frequency, GPU temp/usage, pump/AIO/EXT1/EXT2 RPM, RAM, network). Each card shows the value plus its quality and sample latency. Non-GOOD metrics show `--` with the reason.

### Cooling (manual mode)

Four duty sliders with live percentage labels and profile presets (Silent / Balanced / Performance). Moving a slider sends manual duties to the daemon and **pauses the automatic curve loop** until you apply a curve on the Fans page.

### Fans (automatic mode)

An interactive curve editor per channel:

- **Drag** points to reshape the curve · **double-click** empty space adds a point · **right-click** a point removes it
- The orange cursor shows the current CPU/GPU temperature and the exact PWM the daemon will command right now
- On the *pump* channel everything below the red dashed **40 % floor** is shaded forbidden — the UI snaps points above it and the daemon enforces it again anyway
- **Apply curve to daemon** stores it (`curves.toml`) and switches the channel to automatic control; **Reset** restores the default `(30°,30%) (50°,60%) (70°,100%)`

### Lighting

Pick a mode (Off / Static / Rainbow / Breathing / Temperature-Reactive), tune speed & saturation, choose a color, **Apply lighting**. The Motherboard-sync checkbox hands fans *and* lighting to the motherboard (protocol-correct asymmetric channel table); unticking reclaims software control.

### Telemetry Diagnostics

One row per metric: raw value vs validated value, quality, inter-sample latency, total samples, rejected samples, outlier triggers and the last rejection reason. **Export diagnostics JSON** dumps all of it plus the rejection log for bug reports.

### Settings

LCD brightness (0–100) and orientation — both persist in panel NVM, so the daemon only writes when a value actually changes.

---

## Theme engine

The panel is rendered **by the daemon, natively, in Rust** — the same code path and drawing quality as the classic `cards` dashboard:

- Thick arcs are drawn as chains of filled circles (smooth, round-capped)
- Ring gauges sweep clockwise from 12 o'clock; bars get rounded ends
- Text is rasterized with fontdue (antialiased) from a bold system sans
- The frame is re-rendered every `screen.refresh_ms` and pushed over USB, doubling as the keepalive against the panel's ~15 s logo watchdog

### Built-in themes

| Name | Look |
|---|---|
| `cards` | dark purple gradient, white stat cards, progress bars, pump ring |
| `cards-light` | lavender variant of cards |
| `colorful`, `rings` | classic alternate layouts |
| `neon` | dark navy, cyan/magenta/purple ring gauges |
| `aurora` | deep teal, minimal stat rows, pump ring in the header |
| `slate` | graphite cards with orange/blue accents |

Switch themes from **Theme Studio → APPLY TO DAEMON**, or over IPC:

```jsonc
{"jsonrpc": "2.0", "method": "SetTheme", "params": {"name": "neon"}, "id": 1}
```

The selection is stored in `~/.config/spartacus/theme` and wins over `config.toml` on startup.

### Theme spec format

A theme is a portable JSON document (`.json`) describing a 480×480 design. The daemon parses it (`screen/theme_spec.rs`) and renders it with the same primitives as the built-ins:

```jsonc
{
  "name": "my-theme",
  "background": {"kind": "gradient", "top": "#0B0E1A", "bottom": "#101528"},
  "widgets": [
    {"kind": "panel", "x":14, "y":66, "w":222, "h":148, "r":14,
     "fill":"#161B29", "stroke":"#232B40", "stroke_w":2},
    {"kind": "text", "x":240, "y":42, "size":34, "color":"#FFFFFF",
     "align":"center", "text":"{time}"},
    {"kind": "ring", "cx":240, "cy":240, "r":120, "thickness":14,
     "track":"#1E2438", "fill":"#00E5FF", "binding":"cpu_temp",
     "min":0, "max":100, "start":-90, "sweep":360,
     "center_text":"{cpu_temp:.0}°", "center_size":40},
    {"kind": "bar", "x":30, "y":400, "w":200, "h":10,
     "track":"#1E2438", "fill":"#7CFFB2", "binding":"cpu_usage", "min":0, "max":100},
    {"kind": "rect", "x":0, "y":0, "w":480, "h":56, "fill":"#3A215E"},
    {"kind": "circle", "cx":240, "cy":240, "r":50, "fill":"#101528"}
  ]
}
```

Widget kinds: `panel` (rounded card), `text`, `ring` (gauge), `bar` (progress), `rect`, `circle`.

Text content supports `{binding}` and `{binding:.N}` placeholders resolved from live metrics; unknown bindings render as `--` — never fake zeros.

Custom themes are looked up in `~/.config/spartacus/themes/<name>.json`, then `/etc/spartacus/themes/`, then `/usr/share/spartacus/themes/`.

### Bindings reference

| Binding | Unit | Notes |
|---|---|---|
| `time`, `date` | — | wall clock |
| `cpu_temp`, `gpu_temp` | °C | |
| `cpu_usage`, `gpu_usage` | % | |
| `cpu_freq` | GHz | |
| `ram_used`, `ram_free`, `ram_total` | GB | |
| `ram_pct` | % | |
| `disk_used`, `disk_free`, `disk_total` | GB | |
| `disk_pct` | % | |
| `net_up`, `net_down` | kB/s | |
| `pump_rpm`, `fan_rpm` | RPM | fan_rpm = AIO channel |
| `pump_pct` | % | pump duty approximation |

---

## Theme Studio

Opened from the sidebar ("LCD Studio" entry). Design themes with the same primitives the daemon draws — the preview is a pixel-accurate mirror of the panel output, fed with live telemetry.

- **Presets**: cards, cards-light, neon, aurora, slate — load one and edit
- **Widget palette**: `+ Panel / Text / Ring / Bar / Rect / Circle`
- **Canvas**: click to select, drag to move, dashed outline = selection; live values refresh every second
- **Inspector**: per-widget geometry, colors, alignment, binding, min/max, ring start/sweep, center text
- **Layer list** with reorder (Up/Down), duplicate, delete; undo/redo (`Ctrl+Z` / `Ctrl+Y`)
- **Save JSON** / **Open JSON** / **Export PNG**
- **APPLY TO DAEMON** — saves to `~/.config/spartacus/themes/<name>.json` and switches the daemon to it via IPC. The design renders natively and permanently; no streaming, no GUI round-trip.

> The legacy slayout editor, QDT import and LCD live-streaming were removed: native daemon rendering replaced them (better quality, zero CPU on the GUI side).

---

## Telemetry quality system

Every metric passes one pipeline before any consumer (cards, theme bindings, LCD widgets) sees it:

State

Meaning

Rendered as

`GOOD`

fresh sample inside physical bounds

value

`STALE`

no accepted update > 1000 ms (1500 ms for RPM/net)

`--` + age

`INVALID`

NaN/∞, out-of-bounds, negative RPM, absurd net rate

`--` + reason

`OUTLIER`

sliding-median rejected spike (45→95→46 °C)

`--`; excluded from history

`UNAVAILABLE`

sensor absent from the snapshot

`--`

Design rules enforced everywhere:

- CPU usage comes from `/proc/stat` deltas, network rates from byte-counter deltas with rollover protection
- The outlier filter is a **median**, not an EMA: genuine fast ramps pass untouched, single-frame glitches don't
- Sustained new levels are adopted after repeated confirmation — the filter re-centers instead of latching
- Nothing ever falls back to "last good" silently or renders `0` for missing data

---

## Files & formats

Path

Purpose

`$XDG_RUNTIME_DIR/spartacus.sock`

IPC socket (daemon ↔ GUI)

`~/.config/spartacus/curves.toml`

persisted fan curves (pump + 6 fan channels)

`~/.config/spartacus/config.toml`

optional daemon config (refresh interval, …)

`~/.config/spartacus/theme`

last theme chosen at runtime (wins on startup)

`~/.config/spartacus/themes/*.json`

your Theme Studio designs

`*.png`

Theme Studio exports

---

## IPC API reference

JSON-RPC 2.0, newline-delimited, over the UNIX socket. The GUI's `core/ipc/client.py` wraps all of this; anything that can speak JSON-RPC can too.

Method

Params

Result

`GetStatus`

`{}`

usb\_connected, temps, RPMs, usage, ram/disk/net, `fan_control_auto`

`GetTelemetry`

`{}`

full flat snapshot keyed by canonical binding keys

`GetDiagnostics`

`{}`

daemon health summary

`SetTheme`

`{name}`

switches the panel theme (builtin or `~/.config/spartacus/themes/<name>.json`), persists it

`SendLcdFrame`

`{jpeg_b64}`

legacy: push one raw frame (baseline JPEG gate + 20 s takeover)

`LcdKeepalive`

`{}`

legacy: refresh retained frame without re-send

`LcdSetConfig`

`{orientation?, brightness?}`

applied values (no-op writes skipped, NVM)

`SetPumpSpeed`

`{speed}`

clamped ≥ 40 %, switches to manual

`SetFanSpeed`

`{fan, speed}`

channel 0–3, switches to manual

`SetFans`

`{pump,aio,ext1,ext2,ramp?}`

all four duties, switches to manual

`SetFanCurve`

`{channel, points:[{t,pwm}]}`

sorted/validated points stored + persisted, resumes auto

`SetLighting`

`{mode,color?,speed?,saturation?}`

effect update

`SetMotherboardSync`

`{enable}`

asymmetric motherboard hand-over

`GetConfig` / `SetConfig`

`{}` / config

daemon settings

Errors are standard JSON-RPC errors (`-32602` invalid params, `-32000` hardware error message).

---

## Architecture

```
┌───────────────────── src/daemon (Rust) ─────────────────────┐
│ usb/lcd.rs        3633:0027 · JPEG streaming + control      │
│ usb/controller.rs 3633:002D · HID report 0x10, tachometry   │
│ usb/monitor.rs    reconnects, polls, theme stream, commands │
│ telemetry/        /proc/stat deltas, sysfs sensors          │
│ cooling/          curve evaluation + pump-floor enforcement │
│ screen/           Canvas primitives (stamped arcs, gauges)  │
│   themes*.rs      built-in Rust themes (cards, …)           │
│   theme_spec.rs   data-driven JSON theme renderer           │
│   themes/*.json   neon · aurora · slate (+ cards specs)     │
│ ipc/server.rs     JSON-RPC ⇄ command channel ⇄ monitor task │
└──────────────────────────┬──────────────────────────────────┘
                           │ UNIX socket
┌──────────────────────────▼──────────────────────────────────┐
│ src/gui (PyQt6)                                             │
│  core/ipc       async client + TelemetryWorker thread       │
│  core/telemetry ★ validation pipeline → TelemetryModel      │
│  core/theme     theme spec model + preview renderer         │
│  ui/pages       Overview Cooling Fans Lighting ThemeStudio  │
│                 Diagnostics Settings                        │
└─────────────────────────────────────────────────────────────┘
```

Deep-dive design document: [`docs/UPGRADE_PLAN.md`](/nerdjb/spartacus-control-center/blob/master/docs/UPGRADE_PLAN.md).

## Protocol summary

Reverse-engineered; the authoritative wire specification lives at [gnumbix/deepcool-spartacus-cpp-lib](https://github.com/gnumbix/deepcool-spartacus-cpp-lib).

- **Display control** (bulk EP `0x04`, 46 B): signature `AA 2E`, cmd byte, params, `sum16` LE trailer. Cmds: `0x05` session, `0x04` orientation+brightness (NVM), `0x01` native temp/usage.
- **Image stream** (bulk EP `0x02`): 480×480 **baseline JPEG** only, framed `Start` / `trans`×N / `DCLdfinish`, exactly 512-byte packets, no ACKs.
- **Logo watchdog:** panel reverts to its logo after ~15 s without data; the theme stream refreshes every `refresh_ms`, acting as the keepalive.
- **Linker report** (HID, 64 B, id `0x10`): complete stateless state per transfer, `sum8([1:37])`, marker `0x16`, big-endian tachometers at `[29:37]`. Passive polls use a neutralized report (motherboard sources; EXT2 stays software).

## Safety invariants

1. Pump duty floor **40 %** — enforced by GUI client, IPC layer, curve sanitizer and controller
2. Manual vs automatic fan ownership is explicit; they can never interleave writes
3. Brightness clamped `[0,100]`; orientation `0..3` upright=`0x01`; NVM writes skipped when unchanged
4. Full 64-byte Linker report resent on every change with recomputed checksums
5. Connecting never takes over fans/lighting — monitoring stays passive until asked
6. Invalid telemetry never reaches the panel: theme bindings render `--` / neutral tracks

## Building from source

Rust stable + `pkg-config libusb-1.0` (Arch: `sudo pacman -S rust libusb`), Python ≥ 3.11 with `PyQt6` and `Pillow`.

```bash
cd src/daemon && cargo build --release     # daemon binary
cd src/gui && python3 main.py              # GUI from source tree
```

> 💡 On unreliable/removable storage build out-of-tree: `CARGO_TARGET_DIR=/tmp/spartacus-target cargo build --release`

Offline theme preview without hardware:

```bash
cd src/daemon
./target/release/spartacus-daemon --render-theme cards out.raw        # built-in
./target/release/spartacus-daemon --render-spec my-theme.json out.raw # spec file
python3 -c "from PIL import Image; Image.frombytes('RGB',(480,480),open('out.raw','rb').read()).save('out.png')"
```

## Tests

```bash
python3 -m unittest discover -s tests          # 48 tests: pipeline, theme specs,
                                               # preview renderer, curves, IPC
                                               # round-trip, full-stack GUI vs mock
cd src/daemon && cargo test                    # 16 tests: golden vectors,
                                               # curve parser, override gate
```

The full-stack suite launches the real Qt app against a mock daemon over a real UNIX socket — no hardware needed.

## Troubleshooting

Symptom

Fix

GUI shows `● Disconnected`

daemon not running: start it first; check socket exists

`DeviceNotFoundError` / connect fails

official DeepCool software running? udev rule installed? replug after installing rule

Panel shows DeepCool logo

nothing sent within ~15 s — the daemon theme stream should keep it alive; check daemon logs

Panel shows magenta blocks

a color in your theme spec failed to parse (`#RRGGBB` expected)

Theme didn't switch

name must match a builtin or a file in `~/.config/spartacus/themes/<name>.json`; check daemon log for `Theme set to …`

Theme didn't survive reboot

`~/.config/spartacus/theme` must contain the name; `/etc/spartacus/config.toml` screen.theme is overridden by it

All values `-- ● STALE`

telemetry collector lost sensors; check `SPARTACUS_LOG=debug` daemon output

Slider changes revert

automatic curve loop owns duties — apply a curve to resume auto, curves then follow temperature

## License

MIT / GPL v3

## References

Based on reverse-engineering work from:

- nerdjb/deepcool-spartacus
- gnumbix/deepcool-spartacus-cpp-lib (protocol specification)
- philling-dev/deepcool-digital-linux
- HydroScreen
- Nortank12/deepcool-digital-linux
- Algorithm0/deepcool-digital-info
