# Spartacus Control Center - Complete Setup Guide

Welcome! This guide walks you through building and running the DeepCool SPARTACUS control center from source.

## 🎯 What We're Building

A complete Linux control center for your DeepCool SPARTACUS liquid cooler with:
- **Background daemon** (Rust) for hardware communication
- **GUI control center** (PyQt6) for monitoring and control
- **System tray** integration with quick-access profiles
- **480×480 LCD display** renderer
- **Advanced fan curve** editor
- **ARGB LED** control with multiple effects

---

## 📋 Prerequisites

### Install Required Packages

```bash
sudo pacman -S base-devel rust cargo python python-pyqt6 libusb hidapi imagemagick git
```

Verify installations:
```bash
cargo --version     # Should show: cargo 1.x.x
python --version    # Should show: Python 3.x.x
convert --version   # ImageMagick (shows many lines)
```

---

## 🚀 Step-by-Step Build

### Step 1: Clone the Repository

```bash
cd ~/Projects  # or your preferred location
git clone https://github.com/yourusername/spartacus-control-center.git
cd spartacus-control-center
```

### Step 2: Build the Rust Daemon

```bash
cd src/daemon

# Build in release mode (optimized)
cargo build --release

# This will take 2-5 minutes on first build
# Binary location: target/release/spartacus-daemon
```

**What's building?**
- USB communication layer (LCD Display + Linker Controller)
- JSON-RPC IPC server (for GUI communication)
- Telemetry collector (CPU/GPU temps, system stats)
- Cooling control logic (fan curves, watchdog)

### Step 3: Generate Icon PNGs

```bash
cd ../..  # Back to project root
python3 scripts/generate_icons.py
```

This creates 48×48, 128×128, 256×256, and 512×512 PNG icons from the SVG source.

**Check output**:
```bash
ls assets/icons/*/spartacus-control.png
# Should show 4 PNG files at different sizes
```

### Step 4: Verify Build Artifacts

```bash
# Check daemon binary exists
ls -lh src/daemon/target/release/spartacus-daemon
# Should be 10-20 MB (depends on strip settings)

# Check icons were generated
ls -lh assets/icons/*/
# Should show 4 subdirectories with PNGs
```

---

## ⚙️ Installation

### Method A: System-Wide Installation (Recommended)

```bash
# Navigate to project root
cd ~/Projects/spartacus-control-center

# Run installation script
sudo chmod +x scripts/install.sh
sudo ./scripts/install.sh
```

**This installs**:
- ✓ Daemon to `/usr/bin/spartacus-daemon`
- ✓ GUI to `/usr/share/spartacus/`
- ✓ Launcher to `/usr/bin/spartacus-control-center`
- ✓ systemd service to `/usr/lib/systemd/user/`
- ✓ udev rules to `/etc/udev/rules.d/`
- ✓ Desktop launcher to `/usr/share/applications/`
- ✓ Icons to `/usr/share/icons/hicolor/`

### Method B: Run Without Installing (Development)

```bash
# Just copy daemon binary to accessible location
mkdir -p ~/bin
cp src/daemon/target/release/spartacus-daemon ~/bin/

# Add to PATH if needed
export PATH=~/bin:$PATH

# Or run directly
~/bin/spartacus-daemon
```

---

## 🔧 Post-Installation Configuration

### Step 1: Enable Daemon Service

```bash
# Enable automatic startup when you log in
systemctl --user enable spartacus-daemon

# Start it now
systemctl --user start spartacus-daemon

# Verify it's running
systemctl --user status spartacus-daemon
```

**Expected output** (should show "active (running)"):
```
● spartacus-daemon.service - DeepCool Spartacus Control Center Daemon
     Loaded: loaded (/usr/lib/systemd/user/spartacus-daemon.service; enabled)
     Active: active (running) since [time]
       Main PID: 12345
```

### Step 2: Load udev Rules

```bash
# Reload all udev rules
sudo udevadm control --reload

# Trigger rule evaluation for DeepCool devices
sudo udevadm trigger --attr-match=idVendor=3633

# Verify device access
lsusb | grep 3633
# Should show your SPARTACUS devices

# Check permissions
ls -la /dev/bus/usb/*/ | grep 3633
```

### Step 3: Verify Daemon Connection

```bash
# Check daemon logs
journalctl --user -u spartacus-daemon -n 20

# Should see something like:
# ✓ All subsystems initialized and running
# ✓ IPC Server listening on /run/user/$UID/spartacus.sock
```

### Step 4: Test IPC Socket

```bash
# Verify IPC socket exists
ls -la /run/user/$UID/spartacus.sock

# Try connecting manually (for testing only)
echo '{"jsonrpc":"2.0","method":"GetStatus","params":{},"id":1}' | nc -U /run/user/$UID/spartacus.sock

# Should return a JSON response with status data
```

---

## 🎮 Launch the GUI

### Option 1: From Application Menu
```
Applications → Utilities → Spartacus Control Center
```

### Option 2: From Terminal
```bash
spartacus-control-center
```

### Option 3: Run GUI Script Directly
```bash
python3 src/gui/main.py
```

**On first launch**:
- GUI will connect to daemon
- Status bar should show "✓ Daemon connected"
- You should see real-time temperatures and RPM readings

---

## 📊 Verify Everything Works

### Checklist

```bash
# 1. Daemon is running
systemctl --user is-active spartacus-daemon
# Output: active

# 2. IPC socket exists
test -S /run/user/$UID/spartacus.sock && echo "Socket OK"
# Output: Socket OK

# 3. USB devices are recognized
lsusb | grep 3633
# Should show 2 DeepCool devices

# 4. Daemon logs are clean (no errors)
journalctl --user -u spartacus-daemon --no-pager | tail -5
# Should show "Daemon" log messages without ERRORs

# 5. GUI connects successfully
python3 src/gui/main.py
# Window should open, status bar shows "✓ Daemon connected"
```

---

## 🐛 Troubleshooting

### Problem: Daemon won't start

```bash
# Check detailed logs
journalctl --user -u spartacus-daemon -n 50

# Try running manually to see errors
/usr/bin/spartacus-daemon

# Check if another instance is running
pgrep -a spartacus-daemon
```

**Solution**: If you see USB-related errors, check Step 2 (udev rules).

### Problem: GUI can't connect to daemon

```bash
# Verify IPC socket exists
ls -la /run/user/$UID/spartacus.sock

# Restart daemon
systemctl --user restart spartacus-daemon

# Try GUI again
python3 src/gui/main.py
```

### Problem: USB device not found (lsusb shows nothing)

```bash
# Check BIOS for USB settings
# Try different USB ports
# Verify cable connection

# If using USB hub, try direct connection to motherboard
lsusb -v | grep -i deepcool
```

### Problem: "Permission denied" for USB device

```bash
# Reapply udev rules
sudo udevadm control --reload
sudo udevadm trigger --attr-match=idVendor=3633

# Unplug and replug USB devices
# Check group membership
groups $USER
# Should include 'usb' or similar
```

### Problem: Python module not found

```bash
# Install missing dependencies
pip install --user PyQt6

# Or system-wide
sudo pacman -S python-pyqt6
```

---

## 📁 Project Structure Summary

```
spartacus-control-center/
├── README.md                    # Overview
├── src/
│   ├── daemon/                  # Rust daemon (USB comm, IPC, telemetry)
│   │   ├── Cargo.toml
│   │   └── src/main.rs          # Entry point
│   │
│   └── gui/                     # Python GUI (PyQt6)
│       ├── main.py              # Application entry
│       ├── daemon/ipc_client.py # IPC communication
│       └── ui/main_window.py    # Dashboard interface
│
├── packaging/
│   ├── PKGBUILD                 # Arch Linux package definition
│   ├── 99-spartacus.rules       # udev rules (USB permissions)
│   ├── spartacus-daemon.service # systemd service
│   └── spartacus-control-center.desktop
│
├── assets/
│   ├── spartacus-control.svg    # Icon source
│   └── icons/                   # Generated PNG icons
│
├── scripts/
│   ├── build.sh                 # Build script
│   ├── install.sh               # Installation script
│   └── generate_icons.py        # SVG → PNG converter
│
└── docs/
    ├── INSTALL.md               # Detailed installation
    ├── DEVELOPMENT.md           # Developer guide
    └── QUICKSTART.md            # Quick reference
```

---

## 🎛️ First-Time Usage Tips

1. **Control Center will open to Dashboard tab** - Shows real-time CPU/GPU temps and fan/pump RPMs

2. **Cooling tab** - Adjust pump and fan speeds directly with sliders (0-100%)

3. **RGB Control tab** - Switch between LED modes (Static, Rainbow, Wave, Breathing, Temp-based)

4. **Themes tab** - Select preset LCD display layouts or open the designer

5. **Minimize to tray** - Close the window (not the × button) to minimize to system tray

6. **Right-click tray icon** - Quick access to profiles and settings

---

## 🔄 Common Commands Reference

```bash
# Start daemon
systemctl --user start spartacus-daemon

# Stop daemon
systemctl --user stop spartacus-daemon

# Restart daemon (reload configs)
systemctl --user restart spartacus-daemon

# View live daemon logs
journalctl --user -u spartacus-daemon -f

# View recent logs (last 50 lines)
journalctl --user -u spartacus-daemon -n 50

# Disable automatic startup
systemctl --user disable spartacus-daemon

# Check daemon status
systemctl --user status spartacus-daemon

# Launch GUI
spartacus-control-center

# Run GUI with debug logging
RUST_LOG=debug /usr/bin/spartacus-daemon &  # in terminal 1
python3 src/gui/main.py                     # in terminal 2
```

---

## 📖 Next Steps

- **Customize fan curves**: Cooling tab → Edit pump/fan curves
- **Design LCD themes**: Themes tab → Open Theme Designer
- **Configure ARGB effects**: RGB Control → Select effects and colors
- **Create profiles**: GUI (future version) → Save/load cooling profiles

---

## ✅ Verification Checklist

After following this guide:

- [ ] Rust daemon built successfully (`src/daemon/target/release/spartacus-daemon` exists)
- [ ] PNG icons generated (`assets/icons/*/spartacus-control.png` exist)
- [ ] Daemon installed system-wide (`which spartacus-daemon` works)
- [ ] systemd service enabled (`systemctl --user status spartacus-daemon` shows active)
- [ ] udev rules loaded (can `lsusb | grep 3633`)
- [ ] IPC socket accessible (`/run/user/$UID/spartacus.sock` exists)
- [ ] GUI launches successfully (`spartacus-control-center` starts)
- [ ] GUI shows "Daemon connected" in status bar
- [ ] Temperatures update in real-time
- [ ] Fan/pump controls respond to slider input

---

## 🆘 Getting Help

### Check Resources
1. [INSTALL.md](docs/INSTALL.md) - Detailed installation troubleshooting
2. [DEVELOPMENT.md](docs/DEVELOPMENT.md) - Architecture and development
3. [QUICKSTART.md](docs/QUICKSTART.md) - Quick reference commands

### Debug Steps
1. View daemon logs: `journalctl --user -u spartacus-daemon -f`
2. Check USB devices: `lsusb -v | grep -i deepcool`
3. Test IPC: `echo '{"jsonrpc":"2.0","method":"GetStatus","params":{},"id":1}' | nc -U /run/user/$UID/spartacus.sock`
4. Run GUI with debug: `RUST_LOG=debug python3 src/gui/main.py`

### Report Issues
Create a GitHub issue with:
- Daemon logs (last 20 lines)
- `lsusb -v` output
- Your Linux distribution and kernel version
- USB device connectivity status

---

**Congratulations!** 🎉 You now have a fully functional DeepCool SPARTACUS control center running on Arch Linux!

Enjoy your liquid cooling! 🧊❄️
