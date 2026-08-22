# Installation Guide - Spartacus Control Center

## System Requirements

- **OS**: Arch Linux (x86_64)
- **Kernel**: Linux 5.0+
- **RAM**: 512 MB minimum
- **Dependencies**:
  - libusb
  - hidapi
  - Python 3.9+
  - PyQt6
  - Rust/Cargo (for building)
  - ImageMagick (for icon generation)

## Hardware Requirements

- DeepCool SPARTACUS 360 or 420 Liquid Cooler
- USB ports (2 devices will enumerate)

## Installation Methods

### Method 1: AUR (Recommended)

```bash
yay -S spartacus-control-center
# or
paru -S spartacus-control-center
```

This will handle all dependencies, build, and installation automatically.

### Method 2: Manual Build from Source

1. **Clone repository**:
```bash
git clone https://github.com/yourusername/spartacus-control-center.git
cd spartacus-control-center
```

2. **Build the project**:
```bash
chmod +x scripts/build.sh
./scripts/build.sh
```

3. **Install**:
```bash
sudo chmod +x scripts/install.sh
sudo ./scripts/install.sh
```

### Method 3: makepkg (PKGBUILD)

```bash
cd packaging
makepkg -si
```

## Post-Installation Setup

### 1. Enable Daemon Service

```bash
# Enable automatic startup
systemctl --user enable spartacus-daemon

# Start immediately
systemctl --user start spartacus-daemon

# Check status
systemctl --user status spartacus-daemon

# View logs
journalctl --user -u spartacus-daemon -f
```

### 2. Load udev Rules

```bash
# Reload and apply udev rules (requires root)
sudo udevadm control --reload
sudo udevadm trigger --attr-match=idVendor=3633

# Verify device access
ls -la /dev/bus/usb/*/
```

### 3. GPU Monitoring (Optional)

For NVIDIA GPUs:
```bash
sudo pacman -S nvidia-utils
```

For AMD GPUs:
```bash
sudo pacman -S rocm-core
```

## First-Time Usage

### Start the Control Center

```bash
spartacus-control-center
```

Or from application menu → Utilities → Spartacus Control Center

### Initial Connection

1. The daemon should automatically connect to your SPARTACUS hardware
2. You should see status indicators turn green
3. Temperature and RPM readings will update in real-time

## Troubleshooting

### Daemon won't start

```bash
# Check logs
journalctl --user -u spartacus-daemon -n 50

# Try starting manually
/usr/bin/spartacus-daemon
```

### USB device not found

```bash
# Check if USB device is visible
lsusb | grep 3633

# If not visible, check BIOS for USB controller settings
# Try different USB ports
```

### GUI can't connect to daemon

```bash
# Verify IPC socket exists
ls -la /run/user/$UID/spartacus.sock

# Restart daemon
systemctl --user restart spartacus-daemon

# Check socket permissions
stat /run/user/$UID/spartacus.sock
```

### Permission denied errors

```bash
# Check udev rules
ls -la /etc/udev/rules.d/99-spartacus.rules

# Reload udev
sudo udevadm control --reload
sudo udevadm trigger

# Try unplugging and replugging USB device
```

## Configuration

Configuration file: `~/.config/spartacus/config.toml` or `/etc/spartacus/config.toml`

```toml
[usb]
# USB device IDs
lcd_vendor_id = 0x3633
lcd_product_id = 0x0027
controller_vendor_id = 0x3633
controller_product_id = 0x002D
usb_timeout_ms = 5000
frame_rate = 30  # LCD refresh rate (Hz)

[cooling]
# Fan curve settings
pump_min_rpm = 1500
pump_max_rpm = 3000
fan_min_rpm = 1000
fan_max_rpm = 3000
hysteresis = 5      # Temperature hysteresis (°C)
update_interval_ms = 1000

[telemetry]
# Sensor update frequencies
hwmon_update_ms = 1000   # CPU temp
gpu_update_ms = 2000     # GPU temp
cpu_update_ms = 1000     # CPU usage
```

## Uninstallation

### If installed via AUR:
```bash
yay -R spartacus-control-center
```

### If installed manually:
```bash
sudo rm /usr/bin/spartacus-daemon
sudo rm /usr/bin/spartacus-control-center
sudo rm -rf /usr/share/spartacus
sudo rm /usr/lib/systemd/user/spartacus-daemon.service
sudo rm /etc/udev/rules.d/99-spartacus.rules
sudo rm /usr/share/applications/spartacus-control-center.desktop
sudo udevadm control --reload

# Optional: remove configuration
sudo rm -rf /etc/spartacus
```

## Common Issues & Solutions

| Issue | Solution |
|-------|----------|
| "Daemon not running" | `systemctl --user start spartacus-daemon` |
| Fans not responding | Check udev rules are loaded correctly |
| GUI freezes | Daemon may be unresponsive; restart it |
| USB timeout errors | Try different USB port or cable |
| GPU temp not reading | Ensure nvidia-utils or rocm-core installed |

## Getting Help

1. **Check logs**:
   ```bash
   journalctl --user -u spartacus-daemon -n 100
   ```

2. **Enable debug logging**:
   ```bash
   RUST_LOG=debug /usr/bin/spartacus-daemon
   ```

3. **Report issues**: Create GitHub issue with logs and system info

## Security Notes

- The daemon runs as your user (not root)
- udev rules grant USB device access to the user group
- No system-wide modifications required
- All IPC communication is local to your user session

## Performance Tips

- LCD display updates: ~30 FPS (configurable)
- Fan curve update frequency: 1000ms (1 second)
- Disable GPU monitoring if not needed to reduce CPU usage

Enjoy your SPARTACUS! 🧊❄️
