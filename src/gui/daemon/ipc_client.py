"""
IPC Client for Spartacus Control Center
Communicates with the daemon via UNIX Domain Socket JSON-RPC
"""

import json
import socket
import os
from pathlib import Path
from typing import Optional, Dict, Any


class IPCClient:
    """JSON-RPC client for daemon communication"""

    def __init__(self):
        self.socket = None
        self.socket_path = self._get_socket_path()
        self.request_id = 0

    def _get_socket_path(self) -> str:
        """Get UNIX domain socket path"""
        runtime_dir = os.environ.get(
            "XDG_RUNTIME_DIR",
            f"/run/user/{os.getuid()}"
        )
        return f"{runtime_dir}/spartacus.sock"

    def connect(self) -> bool:
        """Connect to daemon IPC socket"""
        try:
            if self.socket:
                self.socket.close()

            self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.socket.connect(self.socket_path)
            self.socket.settimeout(5.0)
            return True
        except (FileNotFoundError, ConnectionRefusedError, OSError):
            self.socket = None
            return False

    def is_connected(self) -> bool:
        """Check if connected to daemon"""
        if not self.socket:
            return False

        try:
            # Try a simple GetStatus request to verify connection
            self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
            return True
        except:
            return False

    def close(self):
        """Close IPC connection"""
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None

    def _send_request(self, method: str, params: Dict[str, Any] = None) -> Optional[Dict]:
        """Send JSON-RPC request and get response"""
        if not self.connect():
            return None

        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": self.request_id,
        }

        try:
            request_json = json.dumps(request) + "\n"
            self.socket.sendall(request_json.encode())

            # Read response
            response_data = b""
            while True:
                chunk = self.socket.recv(4096)
                if not chunk:
                    break
                response_data += chunk
                if b"\n" in response_data:
                    break

            response_str = response_data.decode().strip()
            if response_str:
                response = json.loads(response_str)
                if "result" in response:
                    return response["result"]
                elif "error" in response:
                    print(f"RPC Error: {response['error']}")
                    return None

        except (socket.timeout, json.JSONDecodeError, Exception) as e:
            self.close()
            return None

        return None

    def get_status(self) -> Optional[Dict]:
        """Get current daemon status"""
        return self._send_request("GetStatus")

    def set_pump_speed(self, speed: int) -> bool:
        """Set pump speed (0-100%)"""
        result = self._send_request("SetPumpSpeed", {"speed": speed})
        return result is not None and result.get("success", False)

    def set_fan_speed(self, fan_index: int, speed: int) -> bool:
        """Set individual fan speed (0-100%)"""
        result = self._send_request("SetFanSpeed", {"fan": fan_index, "speed": speed})
        return result is not None and result.get("success", False)

    def set_rgb_mode(self, mode: str, speed: int = 50, brightness: int = 255) -> bool:
        """Set ARGB LED mode"""
        result = self._send_request(
            "SetRGBMode",
            {"mode": mode, "speed": speed, "brightness": brightness}
        )
        return result is not None and result.get("success", False)
