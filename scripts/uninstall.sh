#!/bin/bash
# Uninstallation script for Spartacus Control Center
# Reverses scripts/install.sh (manual installs without AUR/PKGBUILD).
# Usage:
#   sudo ./scripts/uninstall.sh            # remove program files, KEEP user data
#   sudo ./scripts/uninstall.sh --purge    # also wipe configs, curves and caches

set -e

# --user mode: reverse scripts/setup.sh (no root needed)
if [[ "${1:-}" == "--user" ]]; then
    echo "Removing user-local installation..."
    systemctl --user disable --now spartacus-daemon.service 2>/dev/null || true
    rm -f ~/.config/systemd/user/spartacus-daemon.service
    systemctl --user daemon-reload 2>/dev/null || true
    pkill -x spartacus-daemon 2>/dev/null || true
    pkill -f "spartacus/main.py" 2>/dev/null || true
    rm -rf ~/.local/share/spartacus
    rm -f ~/.local/bin/spartacus-daemon ~/.local/bin/spartacus-control-center
    rm -f ~/.local/share/applications/spartacus-control-center.desktop
    rm -f ~/.local/share/icons/hicolor/128x128/apps/spartacus-control.png
    echo "✔ User installation removed (themes and curves in ~/.config/spartacus kept)."
    echo "  Add --purge --user to also wipe themes, curves and the theme selection."
    [[ "${2:-}" == "--purge" ]] && rm -rf ~/.config/spartacus && echo "✔ User data wiped."
    exit 0
fi

echo "╔════════════════════════════════════════════╗"
echo "║  Spartacus Control Center - Uninstaller    ║"
echo "╚════════════════════════════════════════════╝"
echo ""

if [[ $EUID -ne 0 ]]; then
    echo "❌ This script must be run with sudo"
    exit 1
fi

PURGE=false
[[ "${1:-}" == "--purge" ]] && PURGE=true

# [1/6] Stop everything that may hold the USB devices
echo "[1/6] Stopping daemon and GUI..."
systemctl --user stop spartacus-daemon.service 2>/dev/null || true
if [[ -n "${SUDO_USER:-}" ]]; then
    sudo -u "$SUDO_USER" systemctl --user stop spartacus-daemon.service 2>/dev/null || true
fi
pkill -x spartacus-daemon 2>/dev/null || true
pkill -f "spartacus/main.py" 2>/dev/null || true
sleep 0.5
echo "✓ Processes stopped"

# [2/6] Disable + remove the systemd user unit
echo "[2/6] Removing systemd user service..."
rm -f /usr/lib/systemd/user/spartacus-daemon.service
systemctl daemon-reload 2>/dev/null || true
if [[ -n "${SUDO_USER:-}" ]]; then
    sudo -u "$SUDO_USER" systemctl --user daemon-reload 2>/dev/null || true
    sudo -u "$SUDO_USER" systemctl --user reset-failed spartacus-daemon.service 2>/dev/null || true
fi
echo "✓ Service removed"

# [3/6] Program files
echo "[3/6] Removing program files..."
rm -f  /usr/bin/spartacus-daemon
rm -f  /usr/bin/spartacus-control-center
rm -rf /usr/share/spartacus
echo "✓ Removed: /usr/bin/spartacus-{daemon,control-center}, /usr/share/spartacus"

# [4/6] Desktop integration
echo "[4/6] Removing desktop integration..."
rm -f /usr/share/applications/spartacus-control-center.desktop
for size in 48 128 256 512; do
    rm -f "/usr/share/icons/hicolor/${size}x${size}/apps/spartacus-control.png"
done
update-desktop-database /usr/share/applications 2>/dev/null || true
gtk-update-icon-cache -qf /usr/share/icons/hicolor 2>/dev/null || true
echo "✓ Launcher and icons removed"

# [5/6] udev rules
echo "[5/6] Removing udev rules..."
rm -f /etc/udev/rules.d/99-spartacus.rules
udevadm control --reload 2>/dev/null || true
udevadm trigger --attr-match=idVendor=3633 2>/dev/null || true
echo "✓ udev rule removed and reloaded"

# [6/6] System configuration (kept unless --purge: it may contain your edits)
echo "[6/6] Handling configuration..."
if $PURGE; then
    rm -rf /etc/spartacus
    echo "✓ Removed: /etc/spartacus"
else
    [[ -d /etc/spartacus ]] && echo "- Kept /etc/spartacus (use --purge to remove)"
fi
echo ""
echo "════════════════════════════════════════════"
echo "Uninstallation complete ✓"
echo ""
if $PURGE; then
    echo "--purge was given: wiping per-user data..."
    USERS=("${SUDO_USER[@]:-}")
    for user in "${USERS[@]}"; do
        home=$(getent passwd "$user" | cut -d: -f6)
        [[ -z "$home" ]] && continue
        rm -rf "$home/.config/spartacus"   # curves.toml, config.toml
        rm -rf "$home/.cache/spartacus"    # extracted QDT assets
        rm -f  "$home/.config/Spartacus/ControlCenter.conf"  # GUI QSettings
        chown -R "$user:" "$home/.config" "$home/.cache" 2>/dev/null || true
        echo "✓ Cleaned user data for: $user"
    done
else
    echo "Per-user data was KEPT:"
    echo "  ~/.config/spartacus/   fan curves (curves.toml) + settings"
    echo "  ~/.cache/spartacus/    extracted QDT theme assets"
    echo "  ~/.config/Spartacus/   GUI window preferences"
    echo ""
    echo "Remove them manually, or re-run with: sudo $0 --purge"
fi
