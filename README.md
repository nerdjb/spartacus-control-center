# Spartacus Control Center - DeepCool SPARTACUS 360/420 Linux Control

A Linux control center and driver for the **DeepCool SPARTACUS 360/420** AIO liquid cooler.
The daemon implements the fully reverse-engineered USB protocol and is **hardware-verified**:
it drives the 480×480 pump-cap LCD and reads live tachometry from the Linker controller.

## Hardware Support

- **DeepCool SPARTACUS 360**: 360mm radiator AIO
- **DeepCool SPARTACUS 420**: 420mm radiator AIO

The pump cap enumerates as two independent USB devices:

| Device                  | VID:PID     | Transport              | Function                                  |
|-------------------------|-------------|------------------------|-------------------------------------------|
| Display Controller      | `3633:0027` | Vendor bulk            | 480×480 circular LCD                      |
| Fan & Lighting "Linker" | `3633:002d` | HID interrupt          | Pump/fans PWM, ARGB lighting, tachometry  |

> ⚠️ The product ID `002d` must be written **lowercase** in udev rules — sysfs reports hex in
> lowercase and udev matching is case-sensitive.

## Status

**Working (hardware-verified):**

- ✅ LCD image streaming — baseline JPEG encoded on the fly, framed as
  `Start` / `trans` ×N / `DCLdfinish` 512-byte packets on bulk EP `0x02`
- ✅ LCD control channel — session start/stop, orientation+brightness config,
  native telemetry mode (46-byte packets on bulk EP `0x04`)
- ✅ Logo-watchdog keepalive — panel reverts to its logo after ~15 s without data;
  static screens are refreshed well inside that window
- ✅ Linker passive tachometry — pump/AIO/EXT1/EXT2 RPM polled ~2 Hz using a neutral
  "all channels to motherboard" report so monitoring can never change fan speeds or lighting
- ✅ Linker control — full 64-byte report (`0x10`) with sum8 checksum: fan duties,
  rainbow/breathing/always-on ARGB effects, motherboard sync
- ✅ Packet builders verified against golden test vectors from the reference spec

**In progress / planned:**

- PyQt6 GUI polish, theme designer canvas
- IPC-driven screen themes (daemon currently renders a built-in status dashboard)

## Architecture

```
spartacus-control-center/
├── src/
│   ├── daemon/                    # Rust backend daemon
│   │   └── src/
│   │       ├── main.rs            # entry point + minimal logger
│   │       ├── usb/
│   │       │   ├── mod.rs         # device constants, endpoints, sum16/sum8 checksums
│   │       │   ├── lcd.rs         # display: JPEG streaming + control channel
│   │       │   ├── controller.rs  # linker: report encode/decode, passive polls
│   │       │   └── monitor.rs     # connect/reconnect, RPM polling, frame keepalive
│   │       ├── ipc/server.rs      # JSON-RPC over UNIX domain socket for the GUI
│   │       ├── telemetry/collector.rs
│   │       ├── cooling/           # fan curve evaluation (device writes stay explicit)
│   │       └── config.rs
│   └── gui/                       # PyQt6 control center (dark theme, tray icon)
├── packaging/
│   ├── PKGBUILD
│   ├── 99-spartacus.rules         # udev access rules
│   ├── spartacus-daemon.service   # systemd user service
│   └── spartacus-control-center.desktop
├── docs/
└── scripts/
```

## Protocol Summary

Reverse engineered; see [gnumbix/deepcool-spartacus-cpp-lib](https://github.com/gnumbix/deepcool-spartacus-cpp-lib)
for the full specification this implementation follows.

**Display (`3633:0027`)**

- Control packets (bulk EP `0x04`, 46 bytes): signature `AA 2E`, command byte,
  parameter block, `sum16` trailer (little-endian).
  Commands: `0x05` session enable/disable · `0x04` orientation+brightness · `0x01` native CPU temp/usage.
- Image stream (bulk EP `0x02`): every frame is a 480×480 **baseline** JPEG sent as exactly-512-byte
  packets — `Start` header (size, sum16, chunk count), `trans` data chunks (505-byte payload at offset 7),
  `DCLdfinish` terminator. No ACKs; the panel decodes and shows on FINISH.
- Orientation and brightness persist in panel NVM — the daemon skips no-op config writes.

**Linker (`3633:002d`)**

- One stateless 64-byte report (id `0x10`, header `68 05 02 20 08`) carries all control state;
  every field is populated on every transfer, checksum = `sum8` of bytes `[1:37]`, marker `0x16`.
- Tachometers are big-endian at offsets `[29:37]`.
- Passive status polls send a *neutralized* report (all outputs handed to the motherboard,
  EXT fan 2 kept software per the protocol's asymmetric sync table).

## Safety Invariants

1. Pump duty floor ~40% enforced at the API layer — the pump cools the CPU.
2. Brightness clamped to `[0, 100]`; upright orientation is `0x01`.
3. Config packets sent only when values change (they write panel NVM).
4. Full 64-byte Linker report re-sent on every change, checksums recomputed.
5. Connecting never takes over fans/lighting — monitoring stays passive until
   control is explicitly requested.

## Building

Requires a Rust toolchain (stable) and `pkg-config` + `libusb-1.0` development files.

```bash
# Arch Linux
sudo pacman -S rust libusb

./scripts/build.sh          # builds daemon (+ GUI assets when available)
# or directly:
cd src/daemon && cargo build --release
cd src/daemon && cargo test --release   # runs checksum golden-vector tests
```

> 💡 If your source tree lives on an unreliable/removable drive, build out-of-tree:
> `CARGO_TARGET_DIR=/tmp/spartacus-target cargo build --release`.
> Corrupted build artifacts on flaky storage cause bizarre compiler ICEs and phantom
> type errors in unrelated crates.

## Installation

### Arch Linux

```bash
cd packaging
makepkg -si
```

### Manual

```bash
sudo cp packaging/99-spartacus.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
sudo cp src/daemon/target/release/spartacus-daemon /usr/local/bin/

# run as a user service
mkdir -p ~/.config/systemd/user
cp packaging/spartacus-daemon.service ~/.config/systemd/user/
systemctl --user enable --now spartacus-daemon.service
```

Verify it works:

```bash
SPARTACUS_LOG=debug spartacus-daemon
# expect: "LCD Display connected", "Linker Controller connected",
#         "Tachometry: pump=..." every ~500 ms, and a dashboard on the pump cap LCD
```

## Running the GUI

```bash
cd src/gui
python main.py
```

Requires Python 3.11+, PyQt6, and the daemon running (IPC socket `$XDG_RUNTIME_DIR/spartacus.sock`).

## License

MIT / GPL v3

## References

Based on reverse-engineering work from:

- nerdjb/deepcool-spartacus
- gnumbix/deepcool-spartacus-cpp-lib (protocol specification)
- philling-dev/deepcool-digital-linux
- HydroScreen
- Nortank12/deepcool-digital-linux
- Algorithm0/deepcool-digital-info
