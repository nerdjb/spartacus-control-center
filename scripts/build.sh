#!/bin/bash
# Build script for Spartacus Control Center
# Usage: ./scripts/build.sh

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

echo "╔════════════════════════════════════════╗"
echo "║  Spartacus Control Center - Build      ║"
echo "╚════════════════════════════════════════╝"
echo ""

# Check dependencies
echo "[1/4] Checking dependencies..."
for cmd in cargo rustc python3 imagemagick; do
    if ! command -v "$cmd" &> /dev/null; then
        echo "❌ Error: $cmd is not installed"
        exit 1
    fi
done
echo "✓ All dependencies found"

# Build Rust daemon
echo ""
echo "[2/4] Building Rust daemon..."
cd "$PROJECT_DIR/src/daemon"
cargo build --release
echo "✓ Daemon built: target/release/spartacus-daemon"

# Generate icon PNGs
echo ""
echo "[3/4] Generating icon PNGs from SVG..."
cd "$PROJECT_DIR"
python3 scripts/generate_icons.py
echo "✓ Icons generated"

# Create necessary directories
echo ""
echo "[4/4] Setting up directory structure..."
mkdir -p "$PROJECT_DIR"/{bin,dist}
cp "$PROJECT_DIR/src/daemon/target/release/spartacus-daemon" "$PROJECT_DIR/bin/"
echo "✓ Build complete!"

echo ""
echo "════════════════════════════════════════"
echo "Build artifacts:"
echo "  Daemon:   bin/spartacus-daemon"
echo "  GUI:      src/gui/main.py"
echo "  Icons:    assets/icons/"
echo ""
echo "Next steps:"
echo "  1. Install systemd user service:"
echo "     systemctl --user enable --now spartacus-daemon"
echo "  2. Reload udev rules:"
echo "     sudo udevadm control --reload"
echo "  3. Run GUI:"
echo "     python3 src/gui/main.py"
echo ""
