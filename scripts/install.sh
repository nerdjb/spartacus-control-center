#!/bin/bash
# Installation script for Spartacus Control Center
# Manual installation without AUR/PKGBUILD
# Usage: sudo ./scripts/install.sh

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "╔════════════════════════════════════════════╗"
echo "║  Spartacus Control Center - Installer      ║"
echo "╚════════════════════════════════════════════╝"
echo ""

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    echo "❌ This script must be run with sudo"
    exit 1
fi

# Install daemon binary
echo "[1/5] Installing daemon binary..."
install -Dm755 "$PROJECT_DIR/bin/spartacus-daemon" /usr/bin/spartacus-daemon
echo "✓ Installed: /usr/bin/spartacus-daemon"

# Install GUI files
echo "[2/5] Installing GUI files..."
mkdir -p /usr/share/spartacus/{ui,daemon}
cp -r "$PROJECT_DIR/src/gui"/*.py /usr/share/spartacus/
cp -r "$PROJECT_DIR/src/gui/ui"/*.py /usr/share/spartacus/ui/
cp -r "$PROJECT_DIR/src/gui/daemon"/*.py /usr/share/spartacus/daemon/

# Install launcher wrapper
cat > /usr/bin/spartacus-control-center << 'EOF'
#!/bin/bash
exec python3 /usr/share/spartacus/main.py "$@"
EOF
chmod +x /usr/bin/spartacus-control-center
echo "✓ Installed: /usr/bin/spartacus-control-center"

# Install desktop launcher
echo "[3/5] Installing desktop integration..."
install -Dm644 "$PROJECT_DIR/packaging/spartacus-control-center.desktop" \
    /usr/share/applications/spartacus-control-center.desktop

# Install icons
for size in 48 128 256 512; do
    mkdir -p "/usr/share/icons/hicolor/${size}x${size}/apps"
    cp "$PROJECT_DIR/assets/icons/${size}x${size}/spartacus-control.png" \
        "/usr/share/icons/hicolor/${size}x${size}/apps/" 2>/dev/null || true
done
echo "✓ Desktop launcher and icons installed"

# Install systemd user service (available to all users)
echo "[4/5] Installing systemd user service..."
mkdir -p /usr/lib/systemd/user
install -Dm644 "$PROJECT_DIR/packaging/spartacus-daemon.service" \
    /usr/lib/systemd/user/spartacus-daemon.service
echo "✓ Service installed to /usr/lib/systemd/user/spartacus-daemon.service"

# Install udev rules
echo "[5/5] Installing udev rules..."
install -Dm644 "$PROJECT_DIR/packaging/99-spartacus.rules" \
    /etc/udev/rules.d/99-spartacus.rules
udevadm control --reload
udevadm trigger --attr-match=idVendor=3633
echo "✓ udev rules installed and reloaded"

# Install configuration
mkdir -p /etc/spartacus
if [[ ! -f /etc/spartacus/config.toml ]]; then
    cat > /etc/spartacus/config.toml << 'EOF'
# Spartacus Control Center Configuration
[usb]
lcd_vendor_id = 0x3633
lcd_product_id = 0x0027
controller_vendor_id = 0x3633
controller_product_id = 0x002D
usb_timeout_ms = 5000
frame_rate = 30

[cooling]
pump_min_rpm = 1500
pump_max_rpm = 3000
fan_min_rpm = 1000
fan_max_rpm = 3000
hysteresis = 5
update_interval_ms = 1000

[telemetry]
hwmon_update_ms = 1000
gpu_update_ms = 2000
cpu_update_ms = 1000
EOF
    echo "✓ Default configuration created at /etc/spartacus/config.toml"
fi

echo ""
echo "════════════════════════════════════════════"
echo "Installation complete! ✓"
echo ""
echo "Next steps:"
echo "  1. Start the daemon:"
echo "     systemctl --user enable --now spartacus-daemon"
echo "  2. Launch the GUI:"
echo "     spartacus-control-center"
echo ""
echo "To check daemon status:"
echo "     systemctl --user status spartacus-daemon"
echo ""
echo "To view daemon logs:"
echo "     journalctl --user -u spartacus-daemon -f"
echo ""
