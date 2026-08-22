# Quick Start Guide

## 5-Minute Setup (If Already Built)

### Already built? Just run:

```bash
# 1. Enable and start daemon
systemctl --user enable --now spartacus-daemon

# 2. Verify it's running
systemctl --user status spartacus-daemon

# 3. Launch GUI
spartacus-control-center
```

## Build from Scratch (15 minutes)

### Clone and build:

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/spartacus-control-center.git
cd spartacus-control-center

# 2. Build everything
chmod +x scripts/build.sh
./scripts/build.sh

# 3. Install system-wide
sudo chmod +x scripts/install.sh
sudo ./scripts/install.sh

# 4. Start services
systemctl --user enable --now spartacus-daemon

# 5. Run the GUI
spartacus-control-center
```

## Verify Installation

```bash
# Check daemon is running
systemctl --user status spartacus-daemon

# Check IPC socket exists
ls -la /run/user/$UID/spartacus.sock

# View recent logs
journalctl --user -u spartacus-daemon -n 20
```

## Common Commands

```bash
# Stop daemon
systemctl --user stop spartacus-daemon

# Restart daemon
systemctl --user restart spartacus-daemon

# View live logs
journalctl --user -u spartacus-daemon -f

# Disable automatic startup
systemctl --user disable spartacus-daemon

# Debug mode (verbose logging)
RUST_LOG=debug /usr/bin/spartacus-daemon
```

## Troubleshooting Quick Reference

| Problem | Command |
|---------|---------|
| Daemon won't start | `journalctl --user -u spartacus-daemon -n 50` |
| USB device not found | `lsusb \| grep 3633` |
| Can't connect to daemon | `systemctl --user restart spartacus-daemon` |
| GUI won't launch | `python3 /usr/share/spartacus/main.py` |

For detailed help, see [INSTALL.md](INSTALL.md)
