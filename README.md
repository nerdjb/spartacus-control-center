# SPARTACUS Control Center

**Linux control suite for the DeepCool SPARTACUS 360 / 420 AIO cooler** — a hardware-verified
Rust daemon implementing the reverse-engineered USB protocol, plus a PyQt6 desktop app with
live telemetry, fan-curve automation, ARGB lighting control and a full **LCD Studio** for
designing screens on the 480×480 pump-cap display.

Everything shown on the panel or in the UI flows through one validated telemetry pipeline:
bad sensors show `--`, never fake zeros; spikes are filtered; stale data is labelled.

---

## Table of contents

1. [What can it do?](#what-can-it-do)
2. [Hardware support](#hardware-support)
3. [Quick start](#quick-start)
4. [Installation](#installation)
5. [Using the app](#using-the-app)
6. [LCD Studio](#lcd-studio) · [Designing your first screen](#designing-your-first-screen) · [Telemetry bindings reference](#telemetry-bindings-reference) · [Importing LCD-Wiki `.qdt` themes](#importing-lcd-wiki-qdt-themes)
7. [Live Mode](#live-mode-stream-to-the-panel)
8. [Telemetry quality system](#telemetry-quality-system)
9. [Files & formats](#files--formats)
10. [IPC API reference](#ipc-api-reference)
11. [Architecture](#architecture)
12. [Protocol summary](#protocol-summary)
13. [Safety invariants](#safety-invariants)
14. [Building from source](#building-from-source) · [Tests](#tests)
15. [Troubleshooting](#troubleshooting)

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
- **LCD Studio** — an honest editor on an exact 480×480 canvas: text, telemetry-bound text, ring gauges, images, shapes, gradient backgrounds; layers with lock/hide/reorder/duplicate; grouping; alignment guides; snap-to-grid; zoom 25–200 %; undo/redo; inspector panel
- Six built-in editable templates (Apple Style, MSI Style, Black Tech, Minimal Cyber, Dual Ring, Triple Ring)
- **Realistic preview** composited into a pump-block frame before you commit
- **SEND TO LCD** pushes your design straight to the panel through the daemon
- **Live Mode** streams your layout with live telemetry at 15/30/60 FPS off the GUI thread
- **QDT import** loads lcdwiki.com themes (round `480X480-*.qdt` and rectangular), extracts their images and converts widgets into fully editable native layers

### Trust
- 67 Python + 13 Rust tests including golden-vector checksum tests and a full-stack test that runs the real GUI against a mock daemon
- Verified end-to-end on real hardware, including a 123-frame live stream at 30 FPS

---

## Hardware support

- **DeepCool SPARTACUS 360** (360 mm) and **SPARTACUS 420** (420 mm)

The pump cap enumerates as two independent USB devices:

| Device | VID:PID | Transport | Function |
|---|---|---|---|
| Display Controller | `3633:0027` | Vendor bulk | 480×480 circular LCD |
| Fan & Lighting "Linker" | `3633:002d` | HID interrupt | Pump/fans PWM, ARGB lighting, tachometry |

> ⚠️ The product ID `002d` must be written **lowercase** in udev rules — sysfs reports hex lowercase and udev matching is case-sensitive.
> The official DeepCool software must not be running; it holds the devices.

---

## Quick start

```bash
git clone https://github.com/nerdjb/spartacus-control-center.git
cd spartacus-control-center
./scripts/build.sh                      # builds the Rust daemon

# permissions for raw USB access (one time)
sudo cp packaging/99-spartacus.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger

# terminal 1 — daemon (owns the USB devices)
cd src/daemon && cargo run --release

# terminal 2 — GUI
cd src/gui && python3 main.py
```

You should see `● Connected` / `Pipeline LIVE` in the top bar and the built-in dashboard on the pump LCD.

---

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

```bash
install -m755 src/daemon/target/release/spartacus-daemon ~/.local/bin/
mkdir -p ~/.local/share/spartacus
cp -r src/gui/{ui,core,daemon,main.py} ~/.local/share/spartacus/
cat > ~/.local/bin/spartacus-control-center <<'SH'
#!/bin/bash
exec python3 "$HOME/.local/share/spartacus/main.py" "$@"
SH
chmod +x ~/.local/bin/spartacus-control-center
```

Runtime requirements: `libusb-1.0`, Python ≥ 3.11, `PyQt6`, `Pillow`.

---

## Using the app

The window is a sidebar (pages) plus a top bar of status pills:

| Indicator | Meaning |
|---|---|
| `● Connected` / `● Disconnected` | GUI ↔ daemon IPC link |
| `Daemon Active` | daemon process reachable |
| `Pipeline LIVE` / `STALE` | validated telemetry fresh (< 2 s) or not |
| **SEND TO LCD** | global button — sends the current Studio design to the panel |

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

## LCD Studio

Opened from the sidebar. Layout: canvas center, layer panel + inspector right, toolbar top.

**Toolbar**

| Control | What it does |
|---|---|
| Preset dropdown | Load one of six built-in templates (current design is pushed to undo) |
| Zoom `25–200 %` | Canvas magnification (default 100 % = true size) |
| Circular mask | Show/hide the round panel mask |
| Grid / Snap | 16 px grid overlay; drag positions quantize to 8 px |
| Group / Ungroup | `Ctrl+G` welds the selection into one movable unit; `Ctrl+Shift+U` releases it |
| FPS + START LIVE | Live Mode streaming (see below) |
| Realistic Preview | Render inside a pump-block frame, exactly what ships to the panel |
| **SEND TO LCD** | Encode baseline JPEG → daemon → panel |

**Canvas interaction**

| Action | Input |
|---|---|
| Select | click (topmost element under cursor wins) |
| Multi-select | `Shift`+click, or drag a rubber band on empty space |
| Move | drag (multi-selection moves together) |
| Nudge | arrow keys, 1 px steps |
| Snap | 8 px grid (when Snap on) and cyan guides at the canvas center (240,240) and sibling centers |
| Select all | `Ctrl+A` |

**Elements** (added with `+ Text` / `+ Ring`, duplicated with `Dup`, deleted with `Delete`, reordered with `Front`/`Back`):

| Element | Editable properties (Inspector) |
|---|---|
| Text | content (supports `{bindings}`), font family/size/bold, alignment, letter-spacing, rotation, opacity, color |
| Ring gauge | binding key, min/max range, radius, thickness, start/end angle, track + active colors |
| Image | path (PNG/JPEG/BMP), width/height, keep-aspect, fractional crop, rotation, opacity |
| Shape | rectangle / rounded / circle / line / arc, stroke + fill colors, corner radius |
| Background | linear/radial gradient or solid, optional image |

**Layer panel** lists layers top-first with hidden 🔒 state markers; selecting a row selects it on canvas and populates the Inspector. All edits are undoable — history is snapshot-based, capped at 100 steps, committed on drag-release, add/delete/duplicate/reorder/preset/import/group.

**Saving:** `Save layout` writes a portable `.slayout.json`; `Load .qdt / layout` opens those or an LCD-Wiki theme.

---

## Designing your first screen

A five-minute walkthrough — “big CPU temperature with a ring around it”:

1. Open **LCD Studio** and pick the **Minimal Cyber** preset as a starting point.
2. Click the big `{cpu_temp}` text. In the Inspector set Font size `72`, Bold on, color `#00F0FF`. Drag it near the center — release when the cyan center guide appears.
3. Click the ring. Set Binding `cpu_temp`, Min `20`, Max `95` (matching °C), Thickness `18`, track `#2A2E35`.
4. Add your own label: `+ Text`, type `CPU LOAD {cpu_usage}%` in the Inspector’s Content field, size `20`, drag it below the ring.
5. Press **Realistic Preview** — you see the exact panel output inside the pump block, with live values already substituted.
6. Hit **SEND TO LCD**. The status line reports `LCD accepted frame (… B, sum16=0x…)`. Look at your pump cap — your design is on it.
   The built-in dashboard stays out of the way for 20 s after each send; send again any time to renew.
7. Want it permanent? **START LIVE** streams your design with continuously updating telemetry at the chosen FPS. Stop whenever; the dashboard resumes automatically afterwards.
8. `Save layout` to keep the design as `mydesign.slayout.json`.

Tips:
- Bind text like `CPU {cpu_temp:.0f}°C` — the part inside `{}` is the binding, the rest is literal decoration; format specs (`.0f`, `.1f`) work.
- Rings render **track-only** if their binding isn’t GOOD right now — that’s intentional (no fake zero readings).
- Lock complex groups you’ve positioned: select → `Ctrl+G`, they move as one and can’t be picked individually.
- Use `Undo` liberally — even preset switches and imports are reversible.

---

## Telemetry bindings reference

Placeholders usable in any text element or ring binding. Only these keys are currently delivered by the daemon:

| Binding key | Unit | Typical text template |
|---|---|---|
| `{cpu_temp}` | °C | `CPU {cpu_temp}°C` |
| `{gpu_temp}` | °C | `GPU {gpu_temp}` |
| `{cpu_usage}` | % | `LOAD {cpu_usage}%` |
| `{gpu_usage}` | % | `GPU {gpu_usage}%` |
| `{cpu_freq_ghz}` | GHz | `{cpu_freq_ghz:.2f} GHz` |
| `{pump_rpm}` | RPM | `{pump_rpm} RPM` |
| `{aio_rpm}` | RPM | `FANS {aio_rpm}` |
| `{ext1_rpm}` / `{ext2_rpm}` | RPM | `EXT1 {ext1_rpm}` |
| `{ram_used_gb}` / `{ram_total_gb}` | GB | `RAM {ram_used_gb}/{ram_total_gb} GB` |
| `{net_down_kbps}` / `{net_up_kbps}` | kB/s | `↓{net_down_kbps} ↑{net_up_kbps}` |

Rules:
- A placeholder resolves to the **validated** value; anything not GOOD renders as `--` (`CPU --°C`).
- Format specs follow Python format syntax: `{cpu_temp:.1f}`, `{pump_rpm:5d}` …
- Ring gauges map `(value − min) / (max − min)` onto the arc angle; invalid data ⇒ track-only arc.
- The pipeline knows more keys (`liquid_temp`, `gpu_vram_gb`, `disk_*`, …) — bindings for them simply show `--` until the daemon provides them.

---

## Importing LCD-Wiki `.qdt` themes

lcdwiki.com distributes cooler-screen themes as `.qdt` packages (round screens are named
`480X480-1.qdt` … `480X480-7.qdt`). **Load .qdt / layout** in the Studio imports them:

1. The container is sniffed and unpacked — ZIP, gzip-wrapped, bare descriptor text, or
   opaque binaries where images are recovered by magic-byte carving (PNG/JPEG/BMP).
2. Layout descriptors (JSON / XML / INI variants) are parsed into normalized widgets.
3. Variables (`CPU_Temp`, `fanSpeed1`, `GPU_Load`, …) are mapped onto canonical bindings
   via alias tables + regex fallbacks; anything unmapped is reported so you can bind it
   manually.
4. Widgets convert into native editable layers — rings, bound text, images, placeholder
   shapes for unknown constructs. Images land in `~/.cache/spartacus/qdt/`.
5. A summary dialog lists every lossy/ambiguous conversion note. Edit freely, then send
   or save like any other design.

No formal `.qdt` spec exists publicly; the reader is deliberately evidence-based and never
crashes on unknown content — worst case you get a placeholder plus a note.

---

## Live Mode (stream to the panel)

Choose 15 / 30 / 60 FPS, press **START LIVE**:

- Rendering + JPEG encoding + USB transfer happen on a worker pool — the GUI never blocks
- Only one frame is in flight; late ticks are *dropped* (counted), never queued, keeping latency bounded at the chosen FPS
- Every frame renews the daemon’s **LCD takeover window** (20 s), suspending the built-in dashboard while you stream; when you stop, the dashboard resumes automatically
- If nothing validated is available to draw, a lightweight keepalive refreshes the panel instead of shipping a stale frame

The status label reports `live: N sent · M dropped` in real time.

---

## Telemetry quality system

Every metric passes one pipeline before any consumer (cards, sparkline history, LCD
bindings, Live frames) sees it:

| State | Meaning | Rendered as |
|---|---|---|
| `GOOD` | fresh sample inside physical bounds | value |
| `STALE` | no accepted update > 1000 ms (1500 ms for RPM/net) | `--` + age |
| `INVALID` | NaN/∞, out-of-bounds, negative RPM, absurd net rate | `--` + reason |
| `OUTLIER` | sliding-median rejected spike (45→95→46 °C) | `--`; excluded from history |
| `UNAVAILABLE` | sensor absent from the snapshot | `--` |

Design rules enforced everywhere:
- CPU usage comes from `/proc/stat` deltas, network rates from byte-counter deltas with rollover protection
- The outlier filter is a **median**, not an EMA: genuine fast ramps pass untouched, single-frame glitches don’t
- Sustained new levels are adopted after repeated confirmation — the filter re-centers instead of latching
- Nothing ever falls back to “last good” silently or renders `0` for missing data

---

## Files & formats

| Path | Purpose |
|---|---|
| `$XDG_RUNTIME_DIR/spartacus.sock` | IPC socket (daemon ↔ GUI) |
| `~/.config/spartacus/curves.toml` | persisted fan curves (pump + 6 fan channels) |
| `~/.config/spartacus/config.toml` | optional daemon config (theme, refresh interval) |
| `~/.cache/spartacus/qdt/<hash>/` | assets extracted from imported QDT themes |
| `*.slayout.json` | portable LCD Studio designs (layout model v2) |

---

## IPC API reference

JSON-RPC 2.0, newline-delimited, over the UNIX socket. The GUI’s `core/ipc/client.py`
wraps all of this; anything that can speak JSON-RPC can too.

| Method | Params | Result |
|---|---|---|
| `GetStatus` | `{}` | usb_connected, temps, RPMs, usage, ram/disk/net, `fan_control_auto` |
| `GetTelemetry` | `{}` | full flat snapshot keyed by canonical binding keys |
| `GetDiagnostics` | `{}` | daemon health summary |
| `SendLcdFrame` | `{jpeg_b64}` | `{accepted:true}` — baseline JPEG gate + 20 s takeover |
| `LcdKeepalive` | `{}` | refresh retained frame without re-send |
| `LcdSetConfig` | `{orientation?, brightness?}` | applied values (no-op writes skipped, NVM) |
| `SetPumpSpeed` | `{speed}` | clamped ≥ 40 %, switches to manual |
| `SetFanSpeed` | `{fan, speed}` | channel 0–3, switches to manual |
| `SetFans` | `{pump,aio,ext1,ext2,ramp?}` | all four duties, switches to manual |
| `SetFanCurve` | `{channel, points:[{t,pwm}]}` | sorted/validated points stored + persisted, resumes auto |
| `SetLighting` | `{mode,color?,speed?,saturation?}` | effect update |
| `SetMotherboardSync` | `{enable}` | asymmetric motherboard hand-over |
| `GetConfig` / `SetConfig` | `{}` / config | daemon settings |

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
│ ipc/server.rs     JSON-RPC ⇄ command channel ⇄ monitor task │
└──────────────────────────┬──────────────────────────────────┘
                           │ UNIX socket
┌──────────────────────────▼──────────────────────────────────┐
│ src/gui (PyQt6)                                             │
│  core/ipc       async client + TelemetryWorker thread       │
│  core/telemetry ★ validation pipeline → TelemetryModel      │
│  core/lcd       layout model · renderer · exporter · live   │
│                 scene · undo · qdt importer · templates     │
│  ui/pages       Overview Cooling Fans Lighting Studio       │
│                 Diagnostics Settings                        │
└─────────────────────────────────────────────────────────────┘
```

Deep-dive design document: [`docs/UPGRADE_PLAN.md`](docs/UPGRADE_PLAN.md).

## Protocol summary

Reverse-engineered; the authoritative wire specification lives at
[gnumbix/deepcool-spartacus-cpp-lib](https://github.com/gnumbix/deepcool-spartacus-cpp-lib).

- **Display control** (bulk EP `0x04`, 46 B): signature `AA 2E`, cmd byte, params, `sum16` LE trailer. Cmds: `0x05` session, `0x04` orientation+brightness (NVM), `0x01` native temp/usage.
- **Image stream** (bulk EP `0x02`): 480×480 **baseline JPEG** only, framed `Start` / `trans`×N / `DCLdfinish`, exactly 512-byte packets, no ACKs.
- **Logo watchdog:** panel reverts to its logo after ~15 s without data; keepalives refresh the retained frame cheaply.
- **Linker report** (HID, 64 B, id `0x10`): complete stateless state per transfer, `sum8([1:37])`, marker `0x16`, big-endian tachometers at `[29:37]`. Passive polls use a neutralized report (motherboard sources; EXT2 stays software).

## Safety invariants

1. Pump duty floor **40 %** — enforced by GUI client, IPC layer, curve sanitizer and controller
2. Manual vs automatic fan ownership is explicit; they can never interleave writes
3. Brightness clamped `[0,100]`; orientation `0..3` upright=`0x01`; NVM writes skipped when unchanged
4. Full 64-byte Linker report resent on every change with recomputed checksums
5. Connecting never takes over fans/lighting — monitoring stays passive until asked
6. LCD frames must pass the JPEG skeleton gate before touching USB; GUI content holds a 20 s takeover window, then the dashboard returns

## Building from source

Rust stable + `pkg-config libusb-1.0` (Arch: `sudo pacman -S rust libusb`), Python ≥ 3.11 with `PyQt6` and `Pillow`.

```bash
cd src/daemon && cargo build --release     # daemon binary
cd src/gui && python3 main.py              # GUI from source tree
```

> 💡 On unreliable/removable storage build out-of-tree:
> `CARGO_TARGET_DIR=/tmp/spartacus-target cargo build --release`

## Tests

```bash
python3 -m unittest discover -s tests          # 67 tests: pipeline, QDT, undo,
                                               # curves, renderer, IPC round-trip,
                                               # full-stack GUI vs mock daemon
cd src/daemon && cargo test                    # 13 tests: golden vectors,
                                               # curve parser, override gate
```

The full-stack suite launches the real Qt app against a mock daemon over a real UNIX
socket — no hardware needed.

## Troubleshooting

| Symptom | Fix |
|---|---|
| GUI shows `● Disconnected` | daemon not running: start it first; check socket exists |
| `DeviceNotFoundError` / connect fails | official DeepCool software running? udev rule installed? replug after installing rule |
| Panel shows DeepCool logo | nothing sent within ~15 s — press SEND TO LCD again or enable Live Mode |
| All values `-- ● STALE` | telemetry collector lost sensors; check `SPARTACUS_LOG=debug` daemon output |
| Slider changes revert | automatic curve loop owns duties — apply a curve to resume auto, curves then follow temperature |
| Ring/text shows `--` on panel but works in preview | binding not GOOD at render time — see Diagnostics page for the reason |
| Import dialog lists notes | expected: QDT import reports every ambiguous conversion instead of guessing silently |

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
