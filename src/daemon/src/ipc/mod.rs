// IPC subsystem module
// Handles JSON-RPC communication over UNIX Domain Socket

pub mod server;

pub use server::IPCServer;

// JSON-RPC request/response structures
use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct JsonRpcRequest {
    pub jsonrpc: String,
    pub method: String,
    pub params: serde_json::Value,
    pub id: u64,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct JsonRpcResponse {
    pub jsonrpc: String,
    pub result: Option<serde_json::Value>,
    pub error: Option<JsonRpcError>,
    pub id: u64,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct JsonRpcError {
    pub code: i32,
    pub message: String,
    pub data: Option<serde_json::Value>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct DaemonStatus {
    pub usb_connected: bool,
    pub pump_rpm: u16,
    pub fan_rpm: [u16; 6],
    pub cpu_temp: f32,
    pub gpu_temp: f32,
    pub rgb_enabled: bool,
}

// Available JSON-RPC methods
pub enum RPCMethod {
    GetStatus,
    SetPumpSpeed,
    SetFanSpeed,
    SetRGBMode,
    GetConfig,
    SetConfig,
}

impl RPCMethod {
    pub fn from_str(s: &str) -> Option<Self> {
        match s {
            "GetStatus" => Some(Self::GetStatus),
            "SetPumpSpeed" => Some(Self::SetPumpSpeed),
            "SetFanSpeed" => Some(Self::SetFanSpeed),
            "SetRGBMode" => Some(Self::SetRGBMode),
            "GetConfig" => Some(Self::GetConfig),
            "SetConfig" => Some(Self::SetConfig),
            _ => None,
        }
    }
}
