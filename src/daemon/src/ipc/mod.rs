// IPC subsystem module
// Handles JSON-RPC communication over UNIX Domain Socket

pub mod server;

pub use server::IPCServer;

// JSON-RPC request/response structures
use serde::{Deserialize, Serialize};
use tokio::sync::mpsc;
use tokio::sync::oneshot;

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
    pub cpu_usage: f32,
    pub cpu_freq_ghz: f32,
    pub gpu_usage: f32,
    pub ram_used_gb: f32,
    pub ram_total_gb: f32,
    pub disk_used_gb: f32,
    pub disk_total_gb: f32,
    pub net_up_kbps: f32,
    pub net_down_kbps: f32,
    pub fan_control_auto: bool,
}

#[derive(Debug)]
pub enum DaemonCommand {
    SendLcdFrame { jpeg: Vec<u8>, reply: oneshot::Sender<Result<(), String>> },
    LcdKeepalive { reply: oneshot::Sender<Result<(), String>> },
    LcdSetConfig { orientation: u8, brightness: u8, reply: oneshot::Sender<Result<(), String>> },
    SetFans { pump: u8, aio: u8, ext1: u8, ext2: u8, ramp: u8, reply: oneshot::Sender<Result<(), String>> },
    SetFanSpeed { channel: usize, speed: u8, reply: oneshot::Sender<Result<(), String>> },
    SetLighting { mode: String, color: [u8; 3], speed: u8, saturation: u8, reply: oneshot::Sender<Result<(), String>> },
    SetMotherboardSync { enable: bool, reply: oneshot::Sender<Result<(), String>> },
}

pub type CommandSender = mpsc::Sender<DaemonCommand>;

// Available JSON-RPC methods
pub enum RPCMethod {
    GetStatus,
    SetPumpSpeed,
    SetFanSpeed,
    SetRGBMode,
    GetConfig,
    SetConfig,
    GetTelemetry,
    GetDiagnostics,
    SendLcdFrame,
    LcdKeepalive,
    LcdSetConfig,
    SetFans,
    SetFanCurve,
    SetLighting,
    SetMotherboardSync,
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
            "GetTelemetry" => Some(Self::GetTelemetry),
            "GetDiagnostics" => Some(Self::GetDiagnostics),
            "SendLcdFrame" => Some(Self::SendLcdFrame),
            "LcdKeepalive" => Some(Self::LcdKeepalive),
            "LcdSetConfig" => Some(Self::LcdSetConfig),
            "SetFans" => Some(Self::SetFans),
            "SetFanCurve" => Some(Self::SetFanCurve),
            "SetLighting" => Some(Self::SetLighting),
            "SetMotherboardSync" => Some(Self::SetMotherboardSync),
            _ => None,
        }
    }
}
