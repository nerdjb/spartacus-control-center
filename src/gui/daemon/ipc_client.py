"""Compatibility shim — the implementation moved to core.ipc.client."""

from core.ipc.client import DaemonClient as IPCClient, TelemetryWorker
from core.ipc.protocol import RpcError

__all__ = ["IPCClient", "TelemetryWorker", "RpcError"]
