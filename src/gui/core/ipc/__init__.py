"""IPC package: protocol constants and the daemon client."""

from core.ipc.protocol import (
    RpcError,
    PUMP_DUTY_FLOOR,
    encode_frame,
    decode_frame,
)
from core.ipc.client import DaemonClient, TelemetryWorker, default_socket_path

__all__ = [
    "RpcError",
    "PUMP_DUTY_FLOOR",
    "encode_frame",
    "decode_frame",
    "DaemonClient",
    "TelemetryWorker",
    "default_socket_path",
]
