// IPC Server Implementation
// UNIX Domain Socket JSON-RPC server for GUI communication

use crate::DaemonState;
use anyhow::{anyhow, Result};
use log::{debug, error, info};
use std::sync::Arc;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::{UnixListener, UnixStream};
use tokio::sync::RwLock;

use super::{DaemonStatus, JsonRpcError, JsonRpcRequest, JsonRpcResponse};

pub struct IPCServer {
    socket_path: String,
    state: Arc<RwLock<DaemonState>>,
}

impl IPCServer {
    pub fn new(state: Arc<RwLock<DaemonState>>) -> Self {
        let runtime_dir = std::env::var("XDG_RUNTIME_DIR")
            .unwrap_or_else(|_| format!("/run/user/{}", unsafe { libc::getuid() }));

        let socket_path = format!("{}/spartacus.sock", runtime_dir);

        Self { socket_path, state }
    }

    pub async fn run(&self) -> Result<()> {
        // Remove existing socket if it exists
        if std::path::Path::new(&self.socket_path).exists() {
            std::fs::remove_file(&self.socket_path)?;
        }

        let listener = UnixListener::bind(&self.socket_path)?;
        info!("✓ IPC Server listening on {}", self.socket_path);

        loop {
            let (socket, _) = listener.accept().await?;
            let state = self.state.clone();

            tokio::spawn(async move {
                if let Err(e) = handle_client(socket, state).await {
                    error!("Client handler error: {}", e);
                }
            });
        }
    }
}

async fn handle_client(socket: UnixStream, state: Arc<RwLock<DaemonState>>) -> Result<()> {
    let (reader, mut writer) = socket.into_split();
    let mut buf_reader = BufReader::new(reader);
    let mut line = String::new();

    while buf_reader.read_line(&mut line).await? > 0 {
        let line_trimmed = line.trim();

        if line_trimmed.is_empty() {
            line.clear();
            continue;
        }

        debug!("Received RPC request: {}", line_trimmed);

        // Parse JSON-RPC request
        match serde_json::from_str::<JsonRpcRequest>(line_trimmed) {
            Ok(request) => {
                let response = handle_rpc_request(&request, &state).await;
                let response_json = serde_json::to_string(&response)?;
                writer.write_all(response_json.as_bytes()).await?;
                writer.write_all(b"\n").await?;
            }
            Err(e) => {
                let error_response = JsonRpcResponse {
                    jsonrpc: "2.0".to_string(),
                    result: None,
                    error: Some(JsonRpcError {
                        code: -32700,
                        message: format!("Parse error: {}", e),
                        data: None,
                    }),
                    id: 0,
                };
                let response_json = serde_json::to_string(&error_response)?;
                writer.write_all(response_json.as_bytes()).await?;
                writer.write_all(b"\n").await?;
            }
        }

        line.clear();
    }

    Ok(())
}

async fn handle_rpc_request(
    request: &JsonRpcRequest,
    state: &Arc<RwLock<DaemonState>>,
) -> JsonRpcResponse {
    let method = match super::RPCMethod::from_str(&request.method) {
        Some(m) => m,
        None => {
            return JsonRpcResponse {
                jsonrpc: "2.0".to_string(),
                result: None,
                error: Some(JsonRpcError {
                    code: -32601,
                    message: format!("Method not found: {}", request.method),
                    data: None,
                }),
                id: request.id,
            }
        }
    };

    let state_guard = state.read().await;
    let result = match method {
        super::RPCMethod::GetStatus => {
            let status = DaemonStatus {
                usb_connected: state_guard.usb_connected,
                pump_rpm: state_guard.pump_rpm,
                fan_rpm: state_guard.fan_rpm,
                cpu_temp: state_guard.cpu_temp,
                gpu_temp: state_guard.gpu_temp,
                rgb_enabled: state_guard.rgb_enabled,
            };
            Ok(serde_json::to_value(status).unwrap())
        }
        super::RPCMethod::SetPumpSpeed => {
            if let Some(speed) = request.params.get("speed").and_then(|v| v.as_u64()) {
                Ok(serde_json::json!({ "success": true, "speed": speed }))
            } else {
                Err(JsonRpcError {
                    code: -32602,
                    message: "Invalid parameters".to_string(),
                    data: None,
                })
            }
        }
        super::RPCMethod::SetFanSpeed => {
            if let (Some(fan_index), Some(speed)) = (
                request.params.get("fan").and_then(|v| v.as_u64()),
                request.params.get("speed").and_then(|v| v.as_u64()),
            ) {
                Ok(serde_json::json!({ "success": true, "fan": fan_index, "speed": speed }))
            } else {
                Err(JsonRpcError {
                    code: -32602,
                    message: "Invalid parameters".to_string(),
                    data: None,
                })
            }
        }
        super::RPCMethod::SetRGBMode => {
            if let Some(mode) = request.params.get("mode").and_then(|v| v.as_str()) {
                Ok(serde_json::json!({ "success": true, "mode": mode }))
            } else {
                Err(JsonRpcError {
                    code: -32602,
                    message: "Invalid parameters".to_string(),
                    data: None,
                })
            }
        }
        _ => {
            Err(JsonRpcError {
                code: -32603,
                message: "Internal error".to_string(),
                data: None,
            })
        }
    };

    match result {
        Ok(result) => JsonRpcResponse {
            jsonrpc: "2.0".to_string(),
            result: Some(result),
            error: None,
            id: request.id,
        },
        Err(error) => JsonRpcResponse {
            jsonrpc: "2.0".to_string(),
            result: None,
            error: Some(error),
            id: request.id,
        },
    }
}
