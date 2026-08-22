# Development Guide

## Project Architecture

```
Daemon (Rust)                    GUI (PyQt6)
┌─────────────────────┐         ┌──────────────────────┐
│  spartacus-daemon   │         │ spartacus-control    │
│                     │         │ -center              │
│ ┌─────────────────┐ │ UNIX-   │ ┌────────────────┐   │
│ │  USB Monitor    │◄───Domain─►│ IPC Client     │   │
│ │ (LCD+Controller)│ │ Socket   │ (JSON-RPC)     │   │
│ └─────────────────┘ │ JSON-RPC │ └────────────────┘   │
│                     │         │                       │
│ ┌─────────────────┐ │         │ ┌────────────────┐   │
│ │ Telemetry       │ │         │ │ Main Window    │   │
│ │ Collector       │ │         │ │ Dashboard      │   │
│ └─────────────────┘ │         │ └────────────────┘   │
│                     │         │                       │
│ ┌─────────────────┐ │         │ ┌────────────────┐   │
│ │ Cooling         │ │         │ │ Theme Designer │   │
│ │ Controller      │ │         │ │ (Canvas 480x480)   │
│ └─────────────────┘ │         │ └────────────────┘   │
└─────────────────────┘         │                       │
                                │ ┌────────────────┐   │
                                │ │ Tray Icon      │   │
                                │ └────────────────┘   │
                                └──────────────────────┘

System Telemetry              Hardware Control
├── hwmon (CPU temp)          ├── USB LCD Display
├── nvidia-smi (GPU temp)     ├── USB Linker Controller
├── rocm (AMD GPU)            ├── Fan Curves
└── /proc/stat (CPU usage)    └── ARGB Lighting
```

## Development Setup

### Install Build Dependencies

```bash
sudo pacman -S \
    base-devel \
    rust cargo \
    python python-pyqt6 \
    libusb hidapi \
    imagemagick \
    git

# For documentation generation
sudo pacman -S rustdoc
```

### Clone and Setup

```bash
git clone https://github.com/yourusername/spartacus-control-center.git
cd spartacus-control-center
git checkout -b feature/your-feature
```

## Building Components

### Build Daemon Only

```bash
cd src/daemon
cargo build --release
# Binary: target/release/spartacus-daemon
```

### Build and Run Daemon with Logging

```bash
RUST_LOG=debug cargo run --release
```

### Run GUI Directly

```bash
# No build needed, runs Python directly
python3 src/gui/main.py
```

### Generate Icons

```bash
python3 scripts/generate_icons.py
```

## Code Structure

### Daemon (`src/daemon/src/`)

```
main.rs                 # Entry point, task orchestration
├── config.rs          # Configuration loading
├── usb/
│   ├── mod.rs         # USB constants and types
│   ├── lcd.rs         # LCD display device (0x3633:0x0027)
│   ├── controller.rs  # Linker controller (0x3633:0x002D)
│   └── monitor.rs     # USB device monitor
├── ipc/
│   ├── mod.rs         # JSON-RPC types
│   └── server.rs      # UNIX socket IPC server
├── telemetry/
│   ├── mod.rs         # Telemetry types
│   └── collector.rs   # Temperature and usage collection
└── cooling/
    ├── mod.rs         # Cooling types
    ├── curves.rs      # Fan curve interpolation logic
    └── controller.rs  # Fan/pump control logic
```

### GUI (`src/gui/`)

```
main.py               # QApplication entry point
├── daemon/
│   ├── __init__.py
│   └── ipc_client.py # JSON-RPC client
├── ui/
│   ├── __init__.py
│   ├── main_window.py       # Dashboard, tabs
│   ├── theme_designer.py    # Canvas editor
│   ├── curve_editor.py      # Fan curve UI
│   ├── tray_icon.py         # System tray
│   └── styles.qss           # Dark theme stylesheet
├── models/
│   ├── __init__.py
│   ├── presets.py           # Theme presets
│   └── config.py            # Config structures
└── resources/
    ├── icons/               # PNG icons by size
    └── images/              # UI assets
```

## JSON-RPC API Reference

### Available Methods

#### GetStatus
Get current daemon status and telemetry

**Request**:
```json
{"jsonrpc": "2.0", "method": "GetStatus", "params": {}, "id": 1}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "result": {
    "usb_connected": true,
    "pump_rpm": 2450,
    "fan_rpm": [1500, 1550, 1500, 1550, 1500, 1550],
    "cpu_temp": 52.5,
    "gpu_temp": 48.0,
    "rgb_enabled": true
  },
  "id": 1
}
```

#### SetPumpSpeed
Set pump speed (0-100%)

**Request**:
```json
{"jsonrpc": "2.0", "method": "SetPumpSpeed", "params": {"speed": 75}, "id": 2}
```

#### SetFanSpeed
Set individual fan speed (0-100%)

**Request**:
```json
{"jsonrpc": "2.0", "method": "SetFanSpeed", "params": {"fan": 0, "speed": 80}, "id": 3}
```

#### SetRGBMode
Set ARGB LED mode

**Request**:
```json
{"jsonrpc": "2.0", "method": "SetRGBMode", "params": {"mode": "rainbow", "speed": 50, "brightness": 255}, "id": 4}
```

## Testing

### Manual Testing

```bash
# Terminal 1: Start daemon
cargo run --release --manifest-path src/daemon/Cargo.toml

# Terminal 2: Test IPC connection
nc -U /run/user/$UID/spartacus.sock
# Type: {"jsonrpc":"2.0","method":"GetStatus","params":{},"id":1}

# Terminal 3: Start GUI
python3 src/gui/main.py
```

### Automated Testing

```bash
# Daemon tests
cd src/daemon
cargo test --release

# GUI tests (if implemented)
cd src/gui
python -m pytest
```

## Debugging

### Enable Verbose Logging

```bash
RUST_LOG=trace /usr/bin/spartacus-daemon
```

### Monitor USB Communication

```bash
# Watch USB device operations
watch -n1 'lsusb -v | grep -A5 3633'

# Monitor hidraw devices
tail -f /var/log/kern.log | grep hidraw
```

### Debug IPC Socket

```bash
# Monitor socket connections
watch -n1 'ss -x | grep spartacus'

# Capture socket traffic
strace -e openat,read,write /usr/bin/spartacus-daemon 2>&1 | grep sock
```

## Contributing

### Code Style

- Rust: Follow `rustfmt` and `clippy` standards
- Python: Follow PEP 8, use `black` for formatting

### Before Submitting PR

```bash
# Format Rust code
cargo fmt --all

# Check for issues
cargo clippy --all

# Run tests
cargo test --all

# Format Python
black src/gui
```

## Known Limitations

- LCD rendering currently stub (will implement full USB JPEG streaming)
- ARGB control basic implementation
- Theme designer canvas not yet interactive
- GPU detection limited to nvidia-smi / rocm

## Roadmap

- [ ] Full USB JPEG frame streaming to LCD
- [ ] Interactive theme designer with drag-and-drop
- [ ] LCDWiki `.qdt` theme importer
- [ ] Custom fan curves per profile
- [ ] Network API for remote monitoring
- [ ] OSD (On-Screen Display) integration
- [ ] Streaming stats overlay

## Resources

- **DeepCool SPARTACUS Reverse Engineering**: 
  - nerdjb/deepcool-spartacus
  - gnumbix/deepcool-spartacus-cpp-lib
  - philling-dev/deepcool-digital-linux

- **USB Documentation**:
  - https://libusb.org/
  - https://github.com/libusb/hidapi

- **Linux Kernel Thermal**:
  - `/sys/class/hwmon/` reference
  - https://www.kernel.org/doc/html/latest/admin-guide/thermal/

## Contact & Support

Create issues on GitHub for bugs, features, or questions.
