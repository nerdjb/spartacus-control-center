# SPARTACUS Control Center — GUI v2 Implementation Plan

**Scope:** Rebuild the PyQt6 GUI into a modern hardware suite with an interactive 480×480
LCD Studio, QDT theme import, and a single validated telemetry pipeline.
**Hard rule:** all USB I/O stays in the Rust daemon (`src/daemon`). The GUI never touches
libusb/HID. Every hardware write is an IPC RPC validated against daemon-side limits
(pump duty floor ~40 %, brightness `[0,100]`, baseline JPEG 480×480 only — per
[gnumbix/deepcool-spartacus-cpp-lib](https://github.com/gnumbix/deepcool-spartacus-cpp-lib) §7).

> Stack note: this repository's GUI is **PyQt6 / Python** (`src/gui`) and its daemon is Rust.
> The class layout below is therefore Python/Qt; the only C++ in the system is the reference
> library `libspartacus`, whose wire format the daemon already implements 1:1.

---

## 1. Architecture

```
┌────────────────────────────── src/daemon (Rust, unchanged authority) ──────────────────────────┐
│  usb/lcd.rs      3633:0027 bulk EP0x02 image stream, EP0x04 control (session/config/native)   │
│  usb/controller.rs 3633:002D HID report 0x10 (fans, ARGB, tach BE @29..37)                     │
│  usb/monitor.rs  reconnect + passive RPM polls (~2 Hz) + logo-watchdog keepalive               │
│  telemetry/collector.rs  /proc/stat deltas, sysfs temps/freq/ram/disk/net                      │
│  cooling/{curves,controller}.rs  curve evaluation + SAFETY LIMITS (pump floor)                 │
│  ipc/server.rs   JSON-RPC over $XDG_RUNTIME_DIR/spartacus.sock                                 │
└──────────────────────────────────────────┬────────────────────────────────────────────────────┘
                                           │ JSON-RPC (newline-delimited)
┌──────────────────────────────────────────▼────────────────────────────────────────────────────┐
│ src/gui                                                                                       │
│  core/ipc        async client worker (QThread), request queue, watchdog                        │
│  core/telemetry  ★ VALIDATION PIPELINE (pure python): validator → filters → quality model     │
│  core/lcd        layout model, QPainter renderer, JPEG exporter, undo stack, qdt importer     │
│  ui/pages        Overview · Cooling · Fans · Lighting · LCD Studio · Diagnostics · Settings    │
│  ui/widgets      Sparkline, QualityBadge, StatusPill, ColorWheel, CurveEditor, LayerList …     │
└───────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Data flow (telemetry):**
`hardware sensor → daemon collector → GetStatus/GetTelemetry RPC → TelemetryPipeline.validate()
→ TelemetryModel (Qt) → {Overview UI, sparklines, Diagnostics view, LCD renderer preview,
SendToLcd/LiveMode frames}`.
Nothing renders a raw sample. The LCD exporter consumes **only** `ValidatedValue`s.

**Data flow (LCD frame):**
`Layout model → LcdRenderer (QPainter, exact 480×480) → LcdExporter (baseline JPEG, quality 90)
→ ipc.SendLcdFrame(base64_jpeg) → daemon usb/lcd.rs START/trans×N/DCLdfinish → panel`.
Daemon re-verifies size == 480×480 baseline and recomputes sum16 before streaming.

---

## 2. New file structure

```
src/gui/
├── main.py                        # entry point (rewired to app.shell.AppShell)
├── app/
│   ├── __init__.py
│   ├── shell.py                   # AppShell(QMainWindow): sidebar + topbar + page router
│   ├── router.py                  # PageRouter: nav selection ⇄ stacked pages, SEND TO LCD gating
│   └── state.py                   # AppState: connection flags, dirty-layout flag, live-mode fps
├── core/
│   ├── __init__.py
│   ├── ipc/
│   │   ├── __init__.py
│   │   ├── protocol.py            # method names, payload builders/parsers, error codes
│   │   └── client.py              # IpcWorker(QThread) + DaemonClient facade (async, queued)
│   ├── telemetry/
│   │   ├── __init__.py
│   │   ├── quality.py             # MetricQuality enum + helpers
│   │   ├── specs.py               # MetricSpec table: bounds, units, staleness windows
│   │   ├── filters.py             # SlidingMedianFilter (outlier guard), EmaSmoother (gauges only)
│   │   ├── validator.py           # MetricValidator: NaN/inf/range/steps → ValidatedValue
│   │   ├── pipeline.py            # TelemetryPipeline: ingest(), poll(), stats, rejection log
│   │   ├── model.py               # TelemetryModel(QObject): signals, display text, history
│   │   └── diagnostics.py         # SensorDiagnostics rows for the diagnostics table
│   └── lcd/
│       ├── __init__.py
│       ├── model.py               # LcdLayout + elements (Text/Image/Ring/Shape/Background/Group)
│       ├── bindings.py            # TemplateString "{cpu_temp}°C" ⇄ ValidatedValue resolution
│       ├── renderer.py            # LcdRenderer: QPainter render → QImage(480×480), masks
│       ├── exporter.py            # LcdExporter: QImage→baseline JPEG→IPC frame, checksum pre-check
│       ├── undo.py                # UndoStack: command pattern (move/edit/z-order/add/remove)
│       ├── scene.py               # LcdCanvasScene/QGraphicsView: drag, snap, guides, multiselect
│       ├── live.py                # LiveModeController: QTimer-driven FPS stream (GUI-thread safe)
│       └── qdt/
│           ├── __init__.py
│           ├── container.py       # container sniffing: ZIP / gzip / bare config / binary carve
│           ├── parser.py          # QdtParser → QdtTheme{screen, widgets[], assets{}, unresolved[]}
│           ├── mapper.py          # TelemetryMapper: QDT var names → canonical metric keys
│           └── conversion.py      # qdt→LcdLayout conversion (rings/text/images/shapes/bg)
├── ui/
│   ├── styles.qss                 # design-system tokens (§3)
│   ├── widgets/
│   │   ├── sparkline.py           # QGraphics polyline sparkline w/ fade-in on update
│   │   ├── quality_badge.py       # "● GOOD (83 ms)" pill, color per MetricQuality
│   │   ├── status_pill.py         # Connected / Daemon Active / Pipeline LIVE indicators
│   │   ├── color_wheel.py         # RGB wheel picker + hex/rgb fields
│   │   └── metric_card.py         # big-number card used across Overview/Cooling
│   └── pages/
│       ├── overview.py            # modular cards + sparklines + per-metric quality badges
│       ├── cooling.py             # channel cards, profile combo, safety boundary overlay
│       ├── fans.py                # interactive spline curve editor (CurveEditor widget)
│       ├── lighting.py            # modes, color wheel, speed/sat/brightness, MB sync toggle
│       ├── lcd_studio.py          # canvas + toolbox + inspector + layer list + preview/send
│       ├── diagnostics.py         # sensor table: raw vs validated, latency, rejects, reasons
│       └── settings.py            # daemon unit, start-on-boot, LCD brightness/orientation
└── daemon/ipc_client.py           # compat shim re-exporting core.ipc.client.DaemonClient
```

---

## 3. Design system (`ui/styles.qss`)

| Token | Value | Use |
|---|---|---|
| `--bg` | `#121417` | window background |
| `--panel` | `#1B1E23` | cards, sidebar, inspector |
| `--border` | `#2A2E35` | 1 px rounded borders (8 px radius) |
| `--accent-cyan` | `#00F0FF` | primary accent, active nav, focus rings |
| `--accent-blue` | `#0066FF` | secondary actions, links |
| `--accent-purple` | `#8A2BE2` | LCD Studio selection/highlights |
| `--accent-green` | `#00FF66` | GOOD quality, LIVE pipeline |
| Quality colors | GOOD `#00FF66` · STALE `#FFB454` · INVALID `#FF4D5E` · OUTLIER `#B26BFF` · UNAVAILABLE `#5C6470` |

Typography: Inter/DejaVu Sans; telemetry numerals 28–34 pt tabular; labels 10–11 pt uppercase
letter-spaced. Micro-animations: `QGraphicsOpacityEffect` fade (120 ms) on value change,
pulse keyframe on status pills via `QPropertyAnimation`. No web-dashboard grids of identical
gauge tiles; asymmetric card mosaic on Overview. Icons come from existing repo SVG assets
(`assets/spartacus-control.svg`); no emoji.

---

## 4. Navigation & top bar (`app/shell.py`)

Sidebar (fixed 220 px): Overview · Cooling · Fans · Lighting · LCD Studio · Telemetry
Diagnostics · Settings. Active item: cyan left rail + `--panel` background.

TopBar: logo+device name (`GetStatus.device_name`) · ConnectionPill · DaemonPill ·
PipelinePill (`Pipeline LIVE` when pipeline age < 2 s else `STALE`) · global **SEND TO LCD**
button (enabled when current page is LCD Studio or `AppState.layout_dirty`).

---

## 5. Pages — behavior contracts

### Overview
Cards: CPU (temp/usage/freq + sparkline), GPU (temp/usage/VRAM/core-clock + sparkline),
RAM (used/total/%), Disk & Net (rw usage, up/down rates), Cooling Summary (pump/AIO/EXT1/EXT2 RPM).
Every numeric field pairs with a `QualityBadge`: `47 °C ● GOOD (83 ms)` where `(83 ms)`
is inter-sample latency. Non-GOOD ⇒ text `--` and badge shows state + reason.

### Cooling / Fans
Channels Pump/AIO/EXT1/EXT2; profiles Silent/Balanced/Performance/Custom.
CurveEditor: temperature (x, 20–95 °C) → PWM % (y); monotonic spline through draggable points;
overlays current temp cursor + computed target PWM + measured RPM; shaded forbidden region
below pump floor (40 %) labeled *daemon-enforced*. Writes go through `SetFanCurve`; the daemon
clamps again (`cooling/curves.rs`) and returns the applied values which the UI displays —
the UI never assumes success.

### Lighting
Modes Static/Rainbow/Breathing/Temperature-Reactive/Off mapped to report effect bytes
(`kAlwaysOn/kRainbow/kBreathing`, Off ⇒ static black + fans retained). MB ARGB sync toggle
sends the asymmetric motherboard-sync table (ch3 stays software) exactly as §5.4 of the spec.

### LCD Studio (main feature)
- Fixed 480×480 logical canvas inside `LcdCanvasScene` (QGraphicsView); mask toggle circle/square;
  zoom 25/50/75/100(default)/150/200 %; pan (space/middle-drag); grid overlay + snap (1/2/4/8 px);
  center snapping (x=240, y=240, both) with cyan guide lines; alignment guides; rubber-band multi-select;
  Ctrl+G group / Ctrl+Shift+U ungroup; full UndoStack (`Ctrl+Z/Y`, 200 steps).
- Elements: Text (font family w/ preview, size, weight, align, letter-spacing, opacity, color);
  Telemetry-bound text via `{key}` templates; Ring/Gauge (radius, thickness, start/end angle,
  track/active color, gradient, min/max, smoothing); Image (PNG/JPEG/SVG import, scale, rotation,
  crop rect, keep-aspect, alpha); Shapes (rect, rounded rect, ellipse, line, arc); Background
  (solid / linear gradient / radial gradient / image).
- Layer list: drag reorder, bring forward/backward, front/back, visibility, lock, duplicate,
  delete, rename. Locked items are unpickable on canvas.
- Editor Mode vs Realistic Preview (render composited into a pump-block PNG frame).
- SEND TO LCD → `LcdExporter.render_frame()` → `ipc.SendLcdFrame`; button shows progress and
  disables while a frame upload is in flight.
- LIVE MODE → `LiveModeController` at user-set 15/30/60 fps: renders on a QTimer into a
  preallocated QImage, encodes JPEG off the hot path via `QThreadPool`, streams via daemon.
  The 15 s logo watchdog means LiveMode also emits a lightweight `LcdKeepalive` when throttled.

### Telemetry Diagnostics
Table rows per sensor: name (`k10temp`, `amdgpu`, `coretemp`, `spartacus-linker`), raw value,
validated value, latency ms, samples total, rejected total, outlier triggers, last rejection
reason (ring buffer, 256 entries). Export button dumps JSON log.

### Settings
LCD brightness/orientation (writes `LcdSetConfig` only on change — NVM wear), live fps,
IPC socket override, start-minimized, theme reset.

---

## 6. Validated telemetry pipeline (critical)

States: `GOOD · STALE (>1000 ms no good sample) · INVALID (NaN/inf/out-of-range/negative-RPM/
sensor missing) · OUTLIER (median-filter rejected spike) · UNAVAILABLE (metric absent from
daemon snapshot or device disconnected)`.

Sanitization contract:
- CPU usage: produced by `/proc/stat` **deltas** in the daemon (already implemented,
  `collector.rs::cpu_usage`). Pipeline treats snapshots without a delta field as INVALID.
- Network rates: byte-counter deltas; rollover/reset protection lives daemon-side; pipeline
  rejects rates > `max_link_kbps` (default 2 500 000 kB/s) as INVALID.
- Outlier filter: sliding **median** (window 5) with jump-guard `max_jump_per_s`; a genuine
  steep ramp passes because consecutive samples shift the median with them; a single-frame
  spike (45→150→46) is rejected as OUTLIER and never enters history/sparklines.
- Fallback rendering: non-GOOD ⇒ UI shows `--`; LCD binding resolves to neutral/disabled state
  (ring at track-only, text dimmed). Never `0 °C`, never frozen last-good frame.

Public API (stdlib-only, fully unit-testable):

```python
from core.telemetry.pipeline import TelemetryPipeline
p = TelemetryPipeline.default()                    # specs.py metric table
vals = p.ingest({"cpu_temp": 47.0, "pump_rpm": 2450}, now_ms=1000)
v = vals["cpu_temp"]                               # ValidatedValue(value, quality, age_ms…)
vals = p.poll(now_ms=2500)                         # re-evaluates STALE for quiet metrics
p.stats                                            # totals + per-key counters + reason log
```

`TelemetryModel(QObject)` wraps it with signals `metric_changed(str)`,
`quality_changed(str, object)` and accessors `text("cpu_temp", "{:.0f} °C") -> "--"`.

---

## 7. QDT integration (lcdwiki.com themes)

No public formal spec exists for `.qdt`, so the importer is a **layered, evidence-driven
reader** (each layer logs what it saw; unknowns surface in the UI instead of crashing):

1. `container.sniff()` — detect ZIP (`PK\x03\x04` / EOCD scan), gzip, bare INI/XML/JSON text,
   else binary-carve mode (magic-scan PNG/JPEG/BMP payloads for asset recovery).
2. `parser.QdtParser.parse()` — extract assets to `~/.cache/spartacus/qdt/<hash>/`;
   parse layout descriptors (`.json` / `.xml` / `.ini`) into normalized `QdtWidget`s
   (kind, rect, z, asset ref, color(s), variable binding, angle range).
   Screen shape from filename convention `480X480-N.qdt` ⇒ circular mask preset.
3. `mapper.TelemetryMapper` — alias tables + regex fallback map QDT variable names
   (`CPU_Temp`, `cpuTemp`, `fanSpeed1`, `GPU_Load`…) onto canonical keys from
   `specs.py`; unmapped variables are reported for manual binding in Studio.
4. `conversion.qdt_to_layout()` — emit native `LcdLayout` elements (ring gauges, bound text,
   images, shapes, background). User edits freely, saves as SPARTACUS `.slayout.json`, or sends
   straight to the LCD. Built-in editable presets (Apple Style, MSI Style, Black Tech,
   Minimal Cyber, Dual Ring, Triple Ring) ship in `templates.py` as generated layouts.

Golden tests build synthetic `.qdt` fixtures (ZIP+INI+PNG bytes) so parsing is regression-tested
without shipping third-party assets.

---

## 8. IPC additions (daemon, Rust)

Extend `RPCMethod` and `handle_rpc_request` (`src/daemon/src/ipc/`):

| Method | Params → Result | Daemon action |
|---|---|---|
| `GetTelemetry` | `{}` → full snapshot incl. per-field source names + timestamps | read `DaemonState` |
| `SendLcdFrame` | `{jpeg_b64, quality}` → `{accepted}` | validate 480×480 baseline + len, stream START/trans/FINISH |
| `LcdKeepalive` | `{}` → `{ok}` | resend session-start control packet (watchdog §4.5) |
| `LcdSetConfig` | `{orientation?, brightness?}` → applied values | skip no-op (NVM), clamp |
| `SetFans` | `{pump,aio,ext1,ext2,ramp}` → clamped values | enforce pump ≥ 40 % |
| `SetFanCurve` | `{channel, points:[{t,pwm}], hysteresis}` → applied | store + evaluate loop |
| `SetLighting` | `{mode, color?, speed?, saturation?}` | build report, sum8 |
| `SetMotherboardSync` | `{enable}` | asymmetric table §5.4 |
| `GetDiagnostics` | `{}` | poll counts, checksum fails, reconnects |

GUI-side `core/ipc/client.py` mirrors these; every call returns `(ok, result|error)` and the
worker thread never blocks the UI thread.

---

## 9. Milestones

| Phase | Content | Exit criteria |
|---|---|---|
| M1 | Telemetry pipeline + model + diagnostics data (+tests) | all quality transitions unit-tested; UI renders `--` on stale |
| M2 | Shell (sidebar/topbar/design system) + Overview | live dashboard with badges & sparklines |
| M3 | IPC v2 (client worker + daemon methods above) | SendLcdFrame round-trip verified vs golden vectors |
| M4 | Cooling/Fans/Lighting pages | curves enforced ≤ daemon limits; MB-sync asymmetry honored |
| M5 | LCD Studio MVP (scene, layers, undo, text/ring/image, send) | edit → send visible on panel |
| M6 | QDT importer + templates + realistic preview + live mode | `.qdt` fixture suite green; 30 fps live stable ≥ 30 min |
| M7 | Diagnostics polish, settings persistence, packaging | PKGBUILD updated; docs regenerated |

Testing: `python -m unittest discover tests` (pipeline, QDT, bindings, exporter math),
golden-vector parity tests for frames mirroring the C++ lib vectors, manual hardware checklist
per milestone (watchdog refresh, NVM-write discipline, pump floor).
