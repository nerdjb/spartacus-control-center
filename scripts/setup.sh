#!/bin/bash
# ============================================================================
#  Spartacus Control Center — one-command user installer
#
#    ./scripts/setup.sh
#
#  What it does (no root required except the optional udev step):
#    1. checks build/runtime dependencies
#    2. builds the Rust daemon (release)
#    3. installs daemon + GUI into ~/.local (no system files touched)
#    4. installs the udev rule (asks for sudo; skippable)
#    5. installs + enables a systemd *user* service (daemon auto-starts on
#       login, restarts on crash)
#    6. creates a menu/desktop launcher "Spartacus Control Center"
# ============================================================================
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="$HOME/.local/bin"
APP_DIR="$HOME/.local/share/spartacus"
DATA_DIR="$HOME/.local/share"
SERVICE_NAME="spartacus-daemon.service"

say()  { printf '\033[1;36m▶\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m✔\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m⚠\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m✘ %s\033[0m\n' "$*"; exit 1; }

echo "╔══════════════════════════════════════════════════╗"
echo "║   Spartacus Control Center — Installer           ║"
echo "╚══════════════════════════════════════════════════╝"

# ---------------------------------------------------------------- 1. deps
say "[1/6] Checking dependencies..."
MISSING=()
command -v cargo   >/dev/null || MISSING+=("rust      (pacman -S rust)")
command -v python3 >/dev/null || MISSING+=("python3   (pacman -S python)")
command -v pkg-config >/dev/null || MISSING+=("pkg-config(pacman -S pkgconf)")
pkg-config --exists libusb-1.0 2>/dev/null || MISSING+=("libusb    (pacman -S libusb)")
python3 -c "import PyQt6"  2>/dev/null || MISSING+=("PyQt6     (pacman -S python-pyqt6)")
python3 -c "import PIL"    2>/dev/null || MISSING+=("Pillow    (pacman -S python-pillow)")
if [ ${#MISSING[@]} -gt 0 ]; then
    echo "Missing dependencies:"
    for m in "${MISSING[@]}"; do echo "   • $m"; done
    die "Install the packages above and re-run this script."
fi
ok "all dependencies present"

# ---------------------------------------------------------------- 2. build
say "[2/6] Building daemon (release)..."
(cd "$PROJECT_DIR/src/daemon" && cargo build --release --quiet) \
    || die "daemon build failed"
ok "daemon built"

# ---------------------------------------------------------------- 3. install
say "[3/6] Installing to ~/.local ..."
install -Dm755 "$PROJECT_DIR/src/daemon/target/release/spartacus-daemon" \
    "$BIN_DIR/spartacus-daemon"
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR"
cp -r "$PROJECT_DIR/src/gui/"{ui,core,daemon,models,resources,main.py} "$APP_DIR/"
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/spartacus-control-center" <<'SH'
#!/bin/bash
exec python3 "$HOME/.local/share/spartacus/main.py" "$@"
SH
chmod +x "$BIN_DIR/spartacus-control-center"
ok "installed: $BIN_DIR/spartacus-daemon + $APP_DIR"

# ---------------------------------------------------------------- 4. udev
say "[4/6] USB permissions (udev rule)..."
if [ -f /etc/udev/rules.d/99-spartacus.rules ]; then
    ok "udev rule already installed"
elif sudo -n true 2>/dev/null; then
    sudo install -Dm644 "$PROJECT_DIR/packaging/99-spartacus.rules" \
        /etc/udev/rules.d/99-spartacus.rules
    sudo udevadm control --reload-rules >/dev/null 2>&1 || true
    sudo udevadm trigger --attr-match=idVendor=3633 >/dev/null 2>&1 || true
    ok "udev rule installed"
else
    warn "needs sudo — run this once later:"
    echo "    sudo cp $PROJECT_DIR/packaging/99-spartacus.rules /etc/udev/rules.d/"
    echo "    sudo udevadm control --reload-rules && sudo udevadm trigger"
fi

# ---------------------------------------------------------------- 5. service
say "[5/6] systemd user service (daemon auto-start on login)..."
mkdir -p "$HOME/.config/systemd/user"
sed "s|ExecStart=/usr/bin/spartacus-daemon|ExecStart=$BIN_DIR/spartacus-daemon|" \
    "$PROJECT_DIR/packaging/spartacus-daemon.service" \
    > "$HOME/.config/systemd/user/$SERVICE_NAME"
systemctl --user daemon-reload
# stop a possibly manually-started daemon first — it would hold the USB
# devices and the service could never connect ("Resource busy")
pkill -f "/spartacus-daemon( |$)" 2>/dev/null || true
sleep 1
systemctl --user enable --now "$SERVICE_NAME" >/dev/null 2>&1 || true
if systemctl --user is-active --quiet "$SERVICE_NAME"; then
    ok "daemon service running (auto-starts on login)"
else
    warn "service installed but not running — start it: systemctl --user start $SERVICE_NAME"
fi

# ---------------------------------------------------------------- 6. launcher
say "[6/6] Menu / desktop launcher..."
ICON_SRC="$PROJECT_DIR/src/gui/resources/icons/128x128/spartacus-control.png"
mkdir -p "$DATA_DIR/applications" "$DATA_DIR/icons/hicolor/128x128/apps"
[ -f "$ICON_SRC" ] && cp "$ICON_SRC" "$DATA_DIR/icons/hicolor/128x128/apps/spartacus-control.png"
sed "s|Exec=spartacus-control-center|Exec=$BIN_DIR/spartacus-control-center|" \
    "$PROJECT_DIR/packaging/spartacus-control-center.desktop" \
    > "$DATA_DIR/applications/spartacus-control-center.desktop"
update-desktop-database "$DATA_DIR/applications" >/dev/null 2>&1 || true
ok "launcher created (find 'Spartacus Control Center' in your app menu)"

echo ""
echo "──────────────────────────────────────────────────────"
ok "Installation complete!"
echo "   • Panel control : daemon runs as a service (survives reboot)"
echo "   • Open the app  : menu → Spartacus Control Center"
echo "                     or: spartacus-control-center"
echo "   • Theme Studio  : design panel themes → APPLY TO DAEMON"
echo "   • Uninstall     : ./scripts/uninstall.sh --user"
echo "──────────────────────────────────────────────────────"
