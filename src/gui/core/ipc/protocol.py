"""JSON-RPC method names and payload helpers shared with the Rust daemon.

Wire format: newline-delimited JSON-RPC 2.0 over
``$XDG_RUNTIME_DIR/spartacus.sock``. The daemon is the sole owner of USB;
every method here maps 1:1 onto ``src/daemon/src/ipc/mod.rs::RPCMethod``
(see docs/UPGRADE_PLAN.md §8 for the daemon-side signatures).
"""

from __future__ import annotations

import base64

# -- queries -------------------------------------------------------------------

GET_STATUS = "GetStatus"
GET_TELEMETRY = "GetTelemetry"          # extended snapshot incl. sensor names/timestamps
GET_DIAGNOSTICS = "GetDiagnostics"      # poll counts, checksum failures, reconnects

# -- LCD -------------------------------------------------------------------------

SEND_LCD_FRAME = "SendLcdFrame"         # {jpeg_b64} → {accepted}
LCD_KEEPALIVE = "LcdKeepalive"          # {} → {ok}   (logo-watchdog refresh)
LCD_SET_CONFIG = "LcdSetConfig"         # {orientation?, brightness?}

# -- cooling / fans ---------------------------------------------------------------

SET_PUMP_SPEED = "SetPumpSpeed"
SET_FAN_SPEED = "SetFanSpeed"
SET_FANS = "SetFans"                    # {pump,aio,ext1,ext2,ramp}
SET_FAN_CURVE = "SetFanCurve"           # {channel, points:[{t,pwm}], hysteresis}

# -- lighting ----------------------------------------------------------------------

SET_RGB_MODE = "SetRGBMode"
SET_LIGHTING = "SetLighting"            # {mode,color?,speed?,saturation?,brightness?}
SET_MOTHERBOARD_SYNC = "SetMotherboardSync"  # {enable}

# -- config --------------------------------------------------------------------------

GET_CONFIG = "GetConfig"
SET_CONFIG = "SetConfig"

#: Safety mirror of the daemon's hardcoded limits (daemon re-validates anyway).
PUMP_DUTY_FLOOR = 40
BRIGHTNESS_MIN, BRIGHTNESS_MAX = 0, 100


class RpcError(Exception):
    """Raised by :meth:`DaemonClient.call` when the daemon returns an error."""

    def __init__(self, code: int, message: str):
        super().__init__(f"RPC {code}: {message}")
        self.code = code


def encode_frame(jpeg_bytes: bytes) -> dict:
    """Package a rendered frame for SendLcdFrame."""
    return {"jpeg_b64": base64.b64encode(jpeg_bytes).decode("ascii")}


def decode_frame(payload: bytes | bytearray) -> bytes:
    return base64.b64decode(payload)


def clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))
