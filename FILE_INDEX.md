# Project Index & File Reference

## 📚 Complete File Manifest

This document lists all generated files and their purposes.

---

## 🔴 Root Level

| File | Purpose |
|------|---------|
| [README.md](README.md) | Project overview, features, quick start |
| [SETUP_INSTRUCTIONS.md](SETUP_INSTRUCTIONS.md) | **START HERE** - Complete step-by-step setup guide |

---

## 📂 `/src/daemon/` - Rust Backend Daemon

**Purpose**: Low-level USB communication, telemetry collection, fan curve logic

### Configuration & Build
| File | Purpose |
|------|---------|
| [Cargo.toml](src/daemon/Cargo.toml) | Rust dependencies and project metadata |
| [Cargo.lock](src/daemon/Cargo.lock) | Locked dependency versions (auto-generated) |

### Source Code
| File | Purpose |
|------|---------|
| [src/main.rs](src/daemon/src/main.rs) | Entry point, task orchestration |
| [src/config.rs](src/daemon/src/config.rs) | Configuration loading (TOML parsing) |
| [src/usb/mod.rs](src/daemon/src/usb/mod.rs) | USB constants and device types |
| [src/usb/lcd.rs](src/daemon/src/usb/lcd.rs) | LCD display device (0x3633:0x0027) control |
| [src/usb/controller.rs](src/daemon/src/usb/controller.rs) | Linker controller (0x3633:0x002D) control |
| [src/usb/monitor.rs](src/daemon/src/usb/monitor.rs) | USB device monitor & discovery |
| [src/ipc/mod.rs](src/daemon/src/ipc/mod.rs) | JSON-RPC protocol definitions |
| [src/ipc/server.rs](src/daemon/src/ipc/server.rs) | UNIX socket IPC server implementation |
| [src/telemetry/mod.rs](src/daemon/src/telemetry/mod.rs) | Telemetry data structures |
| [src/telemetry/collector.rs](src/daemon/src/telemetry/collector.rs) | CPU/GPU temp and system stat collection |
| [src/cooling/mod.rs](src/daemon/src/cooling/mod.rs) | Cooling logic module |
| [src/cooling/curves.rs](src/daemon/src/cooling/curves.rs) | Fan curve interpolation & hysteresis |
| [src/cooling/controller.rs](src/daemon/src/cooling/controller.rs) | Fan/pump speed control logic |

---

## 🐍 `/src/gui/` - Python PyQt6 GUI Application

**Purpose**: User-facing control center with validated telemetry, LCD Studio, QDT import

### Main Application
| File | Purpose |
|------|---------|
| [main.py](src/gui/main.py) | Application entry point, system tray |
| [daemon/ipc_client.py](src/gui/daemon/ipc_client.py) | Compat shim → `core.ipc.client` |

### Core logic (`core/`, Qt-independent unless noted)
| Path | Purpose |
|------|---------|
| `core/ipc/{protocol,client}.py` | JSON-RPC contract + thread-safe client, `TelemetryWorker` |
| `core/telemetry/{quality,specs,filters,validator,pipeline}.py` | Validated pipeline (GOOD/STALE/INVALID/OUTLIER/UNAVAILABLE) |
| `core/telemetry/{model,diagnostics}.py` | Qt signal adapter, diagnostics rows |
| `core/hardware/curves.py` | Fan-curve math mirroring daemon semantics (pump floor) |
| `core/lcd/model.py` | `.slayout.json` layout model (text/image/ring/shape/group) |
| `core/lcd/{renderer,exporter,live}.py` | Exact 480×480 render, JPEG export + send, Live Mode FPS streaming |
| `core/lcd/{scene,undo}.py` | Studio canvas (multi-select/groups/guides), undo stack |
| `core/lcd/qdt/{container,parser,mapper,conversion}.py` | LCD Wiki `.qdt` import pipeline |

### UI
| Path | Purpose |
|------|---------|
| `ui/main_window.py` | v2 shell: sidebar, top bar, 7 pages incl. LCD Studio & Diagnostics |
| `ui/widgets/fan_curve_editor.py` | Draggable fan curve editor with live duty preview |
| `ui/styles.qss` | Graphite/cyan design system |

### Tests (`tests/`, stdlib unittest)
| File | Coverage |
|------|----------|
| `test_telemetry_pipeline.py` | Validation states, outlier filter, staleness, stats |
| `test_telemetry_model.py` | Qt adapter signals, badges, LIVE flag |
| `test_qdt_parser.py` | Container sniffing, parsing, mapping, conversion |
| `test_undo_and_curves.py` | Undo stack, curve interpolation/sanitization/floor |
| `test_lcd_renderer.py` | Exact-size frames, baseline JPEG, rotation/opacity |
| `test_bindings.py` | LCD template strings vs non-GOOD data |
| `test_ipc_roundtrip.py` | Client ↔ mock daemon over real UNIX socket |
| `test_full_stack.py` | Real MainWindow + mock daemon end-to-end |

---

## 📦 `/packaging/` - Arch Linux Package & Deployment

**Purpose**: Package definition, system integration, udev rules

| File | Purpose |
|------|---------|
| [PKGBUILD](packaging/PKGBUILD) | Arch Linux package build definition |
| [spartacus.install](packaging/spartacus.install) | PKGBUILD install hooks (post-install, uninstall) |
| [99-spartacus.rules](packaging/99-spartacus.rules) | **CRITICAL**: udev rules for USB device access |
| [spartacus-daemon.service](packaging/spartacus-daemon.service) | systemd user service definition |
| [spartacus-control-center.desktop](packaging/spartacus-control-center.desktop) | Desktop launcher entry |

---

## 🎨 `/assets/` - Graphics & Resources

**Purpose**: Application icon, themes, UI assets

| File | Purpose |
|------|---------|
| [spartacus-control.svg](assets/spartacus-control.svg) | Master SVG icon (all sizes derived from this) |
| [icons/48x48/](assets/icons/48x48/) | Small icon PNG (48×48) |
| [icons/128x128/](assets/icons/128x128/) | Medium icon PNG (128×128) |
| [icons/256x256/](assets/icons/256x256/) | Large icon PNG (256×256) |
| [icons/512x512/](assets/icons/512x512/) | Extra-large icon PNG (512×512) |

---

## 🛠️ `/scripts/` - Build & Installation Scripts

**Purpose**: Automation for building and installing the project

| File | Purpose |
|------|---------|
| [build.sh](scripts/build.sh) | Compiles daemon, generates icons, creates package |
| [install.sh](scripts/install.sh) | System-wide installation (requires sudo) |
| [generate_icons.py](scripts/generate_icons.py) | Converts SVG to PNG at 4 resolutions |

---

## 📖 `/docs/` - Documentation

**Purpose**: Guides, troubleshooting, development references

| File | Purpose |
|------|---------|
| [INSTALL.md](docs/INSTALL.md) | Detailed installation guide with troubleshooting |
| [QUICKSTART.md](docs/QUICKSTART.md) | Quick command reference (5-minute setup) |
| [DEVELOPMENT.md](docs/DEVELOPMENT.md) | Architecture, dev setup, JSON-RPC API reference |

---

## 🚀 Quick File Locations

### For End Users
```
README.md ←─── Read this first
SETUP_INSTRUCTIONS.md ←─── Then follow this
docs/INSTALL.md ←─── For troubleshooting
docs/QUICKSTART.md ←─── For common commands
```

### For Developers
```
src/daemon/ ←─── Backend (Rust)
src/gui/ ←─── Frontend (Python)
docs/DEVELOPMENT.md ←─── Architecture & API docs
packaging/PKGBUILD ←─── Distribution format
```

### Critical Files (System Integration)
```
packaging/99-spartacus.rules ←─── USB permissions (installed to /etc/udev/rules.d/)
packaging/spartacus-daemon.service ←─── Auto-start service (installed to ~/.config/systemd/user/)
packaging/PKGBUILD ←─── Package definition (for AUR, makepkg)
```

---

## 📊 Build Artifacts Generated

After running `./scripts/build.sh`:

```
bin/
├── spartacus-daemon             # Compiled Rust daemon binary

assets/icons/
├── 48x48/spartacus-control.png  # Small icon
├── 128x128/spartacus-control.png
├── 256x256/spartacus-control.png
└── 512x512/spartacus-control.png # Large icon

src/daemon/target/release/
└── spartacus-daemon             # Build output binary
```

---

## 🔧 Installation Target Paths

After running `sudo ./scripts/install.sh`:

```
/usr/bin/
├── spartacus-daemon              # Daemon executable
└── spartacus-control-center      # GUI launcher wrapper

/usr/share/spartacus/
├── main.py                        # GUI application
├── ui/
│   ├── main_window.py
│   ├── theme_designer.py
│   └── ...
└── daemon/
    └── ipc_client.py

/etc/udev/rules.d/
└── 99-spartacus.rules            # USB device permissions

/usr/lib/systemd/user/
└── spartacus-daemon.service      # systemd service

/usr/share/applications/
└── spartacus-control-center.desktop

/usr/share/icons/hicolor/
├── 48x48/apps/
├── 128x128/apps/
├── 256x256/apps/
└── 512x512/apps/
    └── spartacus-control.png

/etc/spartacus/
└── config.toml                   # Configuration file
```

---

## 📋 File Format Reference

### USB Device IDs
- **LCD Display**: `0x3633:0x0027` (480×480 RGB JPEG stream)
- **Linker Controller**: `0x3633:0x002D` (Pump RPM, fans, ARGB, watchdog)

### Configuration (TOML)
- **System**: `/etc/spartacus/config.toml`
- **User**: `~/.config/spartacus/config.toml`

### IPC Communication
- **Socket**: `/run/user/$UID/spartacus.sock`
- **Protocol**: JSON-RPC 2.0 over UNIX Domain Socket
- **Example**: `{"jsonrpc":"2.0","method":"GetStatus","params":{},"id":1}`

### Data Files
- **Themes**: JSON layout definitions (future: custom theme support)
- **Profiles**: Fan curve and lighting presets (future: save/load)

---

## 🎯 Dependencies Map

```
System Package Installation
├── libusb ──┐
├── hidapi ──┤
├── python ──┼──→ [GUI Application]
└── pyqt6 ───┤

Build Dependencies
├── rustc ────┐
├── cargo ────┼──→ [Daemon Binary]
├── git ──────┤
└── imagemagick

Runtime Dependencies (Daemon)
├── libusb
├── hidapi
└── systemd-libs

Runtime Dependencies (GUI)
├── python
├── pyqt6
└── (optional) nvidia-utils or rocm-core for GPU monitoring

System Integration
├── udev rules
├── systemd user service
└── desktop launcher
```

---

## ✅ Verification Checklist

### After Build (`./scripts/build.sh`)
- [ ] `src/daemon/target/release/spartacus-daemon` exists (10-20 MB)
- [ ] `assets/icons/*/spartacus-control.png` all exist
- [ ] `bin/spartacus-daemon` copied successfully

### After Install (`sudo ./scripts/install.sh`)
- [ ] `/usr/bin/spartacus-daemon` readable and executable
- [ ] `/usr/bin/spartacus-control-center` wrapper exists
- [ ] `/etc/udev/rules.d/99-spartacus.rules` exists
- [ ] `/usr/lib/systemd/user/spartacus-daemon.service` exists
- [ ] `/usr/share/icons/hicolor/*/apps/spartacus-control.png` all exist

### After First Run
- [ ] `systemctl --user status spartacus-daemon` shows "active (running)"
- [ ] `/run/user/$UID/spartacus.sock` exists
- [ ] `lsusb | grep 3633` shows 2 DeepCool devices
- [ ] GUI connects (shows "✓ Daemon connected")
- [ ] Temperature values update in real-time

---

## 📞 Support

- **Installation issues**: See [docs/INSTALL.md](docs/INSTALL.md)
- **Development**: See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)
- **Quick reference**: See [docs/QUICKSTART.md](docs/QUICKSTART.md)
- **Full setup**: See [SETUP_INSTRUCTIONS.md](SETUP_INSTRUCTIONS.md)

---

Generated: 2026-08-22 | Project: Spartacus Control Center v0.1.0
