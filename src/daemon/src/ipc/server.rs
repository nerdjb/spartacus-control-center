// IPC Server Implementation
// UNIX Domain Socket JSON-RPC server for GUI communication

use crate::DaemonState;
use anyhow::Result;
use log::{debug, error, info};
use std::sync::Arc;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::{UnixListener, UnixStream};
use tokio::sync::RwLock;
use tokio::sync::{mpsc, oneshot};

use super::{DaemonCommand, DaemonStatus, JsonRpcError, JsonRpcRequest, JsonRpcResponse};

pub struct IPCServer {
    socket_path: String,
    state: Arc<RwLock<DaemonState>>,
    commands: mpsc::Sender<DaemonCommand>,
}

impl IPCServer {
    pub fn new(state: Arc<RwLock<DaemonState>>, commands: mpsc::Sender<DaemonCommand>) -> Self {
        let runtime_dir = std::env::var("XDG_RUNTIME_DIR")
            .unwrap_or_else(|_| format!("/run/user/{}", unsafe { libc::getuid() }));

        let socket_path = format!("{}/spartacus.sock", runtime_dir);

        Self { socket_path, state, commands }
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
            let commands = self.commands.clone();

            tokio::spawn(async move {
                if let Err(e) = handle_client(socket, state, commands).await {
                    error!("Client handler error: {}", e);
                }
            });
        }
    }
}

async fn handle_client(socket: UnixStream, state: Arc<RwLock<DaemonState>>, commands: mpsc::Sender<DaemonCommand>) -> Result<()> {
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
                let response = handle_rpc_request(&request, &state, &commands).await;
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
    commands: &mpsc::Sender<DaemonCommand>,
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

    let state_snapshot = state.read().await.clone();
    let result = match method {
        super::RPCMethod::GetStatus => {
            let status = DaemonStatus {
                usb_connected: state_snapshot.usb_connected,
                pump_rpm: state_snapshot.pump_rpm,
                fan_rpm: state_snapshot.fan_rpm,
                cpu_temp: state_snapshot.cpu_temp,
                gpu_temp: state_snapshot.gpu_temp,
                rgb_enabled: state_snapshot.rgb_enabled,
                cpu_usage: state_snapshot.cpu_usage,
                cpu_freq_ghz: state_snapshot.cpu_freq_ghz,
                gpu_usage: state_snapshot.gpu_usage,
                ram_used_gb: state_snapshot.ram_used_gb,
                ram_total_gb: state_snapshot.ram_total_gb,
                disk_used_gb: state_snapshot.disk_used_gb,
                disk_total_gb: state_snapshot.disk_total_gb,
                net_up_kbps: state_snapshot.net_up_kbps,
                fps: state_snapshot.fps,
                frametime_ms: state_snapshot.frametime_ms,
                cpu_watts: state_snapshot.cpu_watts,
                gpu_watts: state_snapshot.gpu_watts,
                net_down_kbps: state_snapshot.net_down_kbps,
                fan_control_auto: state_snapshot.fan_control_auto,
            };
            Ok(serde_json::to_value(status).unwrap())
        }
        super::RPCMethod::GetTelemetry => {
            let s = state_snapshot.clone();
            Ok(serde_json::json!({
                "usb_connected": s.usb_connected,
                "cpu_temp": s.cpu_temp, "cpu_usage": s.cpu_usage,
                "cpu_freq_ghz": s.cpu_freq_ghz,
                "gpu_temp": s.gpu_temp, "gpu_usage": s.gpu_usage,
                "pump_rpm": s.pump_rpm, "aio_rpm": s.fan_rpm[0],
                "ext1_rpm": s.fan_rpm[1], "ext2_rpm": s.fan_rpm[2],
                "ram_used_gb": s.ram_used_gb, "ram_total_gb": s.ram_total_gb,
                "disk_used_gb": s.disk_used_gb, "disk_total_gb": s.disk_total_gb,
                "net_up_kbps": s.net_up_kbps, "net_down_kbps": s.net_down_kbps,
                "fps": s.fps, "frametime_ms": s.frametime_ms,
                "cpu_watts": s.cpu_watts, "gpu_watts": s.gpu_watts,
                "fan_control_auto": s.fan_control_auto,
            }))
        }
        super::RPCMethod::GetDiagnostics => {
            Ok(serde_json::json!({"daemon": "active", "usb_connected": state_snapshot.usb_connected}))
        }
        super::RPCMethod::SetFanSpeed => {
            if let (Some(fan_index), Some(speed)) = (
                request.params.get("fan").and_then(|v| v.as_u64()),
                request.params.get("speed").and_then(|v| v.as_u64()),
            ) {
                // Manual channel writes pause the automatic curve loop.
                state.write().await.fan_control_auto = false;
                let result = send_command(commands, |reply| DaemonCommand::SetFanSpeed {
                    channel: fan_index as usize, speed: speed.min(100) as u8, reply,
                }).await;
                result.map(|_| serde_json::json!({ "success": true, "fan": fan_index, "speed": speed, "mode": "manual" }))
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
                let mode = mode.to_string();
                let result = send_command(commands, |reply| lighting_command(&mode, &request.params, reply)).await;
                result.map(|_| serde_json::json!({ "success": true, "mode": mode }))
            } else {
                Err(JsonRpcError {
                    code: -32602,
                    message: "Invalid parameters".to_string(),
                    data: None,
                })
            }
        }
        super::RPCMethod::SetPumpSpeed => {
            if let Some(speed) = request.params.get("speed").and_then(|v| v.as_u64()) {
                // Manual pump writes pause the automatic curve loop.
                state.write().await.fan_control_auto = false;
                let result = send_command(commands, |reply| DaemonCommand::SetFanSpeed {
                    channel: 0, speed: speed.min(100).max(40) as u8, reply,
                }).await;
                result.map(|_| serde_json::json!({"success": true, "speed": speed.min(100).max(40), "mode": "manual"}))
            } else { Err(invalid_params()) }
        }
        super::RPCMethod::SendLcdFrame => {
            let encoded = request.params.get("jpeg_b64").and_then(|v| v.as_str()).ok_or_else(invalid_params);
            match encoded.and_then(|v| base64_decode(v).map_err(|e| JsonRpcError { code: -32602, message: e, data: None })) {
                Ok(jpeg) => {
                    // Reject obvious garbage before it reaches the USB path;
                    // the panel only decodes 480x480 baseline JPEGs anyway.
                    if !is_jpeg_skeleton(&jpeg) {
                        Err(param_error("SendLcdFrame payload is not a JPEG"))
                    } else {
                        // GUI takeover: hold the built-in theme stream off while
                        // GUI content is fresh (Live Mode keeps renewing this).
                        {
                            let mut state = state.write().await;
                            state.lcd_gui_override = true;
                            state.lcd_gui_override_until_ms = now_epoch_ms() + LCD_OVERRIDE_HOLD_MS;
                        }
                        send_command(commands, |reply| DaemonCommand::SendLcdFrame { jpeg, reply }).await.map(|_| serde_json::json!({"accepted": true}))
                    }
                }
                Err(e) => Err(e),
            }
        }
        super::RPCMethod::LcdKeepalive => send_command(commands, |reply| DaemonCommand::LcdKeepalive { reply }).await.map(|_| serde_json::json!({"ok": true})),
        super::RPCMethod::LcdSetConfig => {
            let orientation = request.params.get("orientation").and_then(|v| v.as_u64()).unwrap_or(1).min(3) as u8;
            let brightness = request.params.get("brightness").and_then(|v| v.as_u64()).unwrap_or(80).min(100) as u8;
            send_command(commands, |reply| DaemonCommand::LcdSetConfig { orientation, brightness, reply }).await.map(|_| serde_json::json!({"orientation": orientation, "brightness": brightness}))
        }
        super::RPCMethod::SetFans => {
            let get = |key: &str, default: u64| request.params.get(key).and_then(|v| v.as_u64()).unwrap_or(default).min(100) as u8;
            // Manual duty writes pause the automatic curve loop.
            state.write().await.fan_control_auto = false;
            send_command(commands, |reply| DaemonCommand::SetFans { pump: get("pump", 40).max(40), aio: get("aio", 50), ext1: get("ext1", 50), ext2: get("ext2", 50), ramp: get("ramp", 0).min(30), reply }).await.map(|_| serde_json::json!({"success": true, "mode": "manual"}))
        }
        super::RPCMethod::SetFanCurve => {
            let channel = request
                .params
                .get("channel")
                .and_then(|v| v.as_str())
                .unwrap_or("pump")
                .to_string();
            let parsed = request
                .params
                .get("points")
                .and_then(parse_curve_points)
                .filter(|points| points.len() >= 2);
            if let Some(mut points) = parsed {
                if channel == "pump" {
                    // Mirror the controller's safety floor at the API layer.
                    for (_, duty) in points.iter_mut() {
                        *duty = (*duty).max(40);
                    }
                }
                let known = matches!(channel.as_str(), "pump" | "aio" | "ext1" | "ext2");
                if !known {
                    Err(param_error(&format!("unknown channel '{channel}'")))
                } else {
                    // Applying a curve re-enables automatic control.
                    state.write().await.fan_control_auto = true;
                    let mut state = state.write().await;
                    match channel.as_str() {
                        "pump" => state.pump_curve = points.clone(),
                        "aio" => state.fan_curves[0] = points.clone(),
                        "ext1" => state.fan_curves[1] = points.clone(),
                        _ => state.fan_curves[2] = points.clone(),
                    }
                    let pump = state.pump_curve.clone();
                    let fans = state.fan_curves.clone();
                    drop(state);
                    if let Err(e) = crate::config::save_curves(pump, fans).await {
                        log::warn!("Failed to persist curves: {e}");
                    }
                    Ok(serde_json::json!({
                        "success": true,
                        "channel": channel,
                        "mode": "auto",
                        "points": points.iter()
                            .map(|(t, d)| serde_json::json!({"t": t, "pwm": d}))
                            .collect::<Vec<_>>(),
                    }))
                }
            } else {
                Err(param_error("curve needs at least two valid points"))
            }
        }
        super::RPCMethod::SetLighting => {
            let mode = request.params.get("mode").and_then(|v| v.as_str()).unwrap_or("off").to_string();
            send_command(commands, |reply| lighting_command(&mode, &request.params, reply)).await.map(|_| serde_json::json!({"success": true, "mode": mode}))
        }
        super::RPCMethod::SetMotherboardSync => {
            let enable = request.params.get("enable").and_then(|v| v.as_bool()).unwrap_or(false);
            send_command(commands, |reply| DaemonCommand::SetMotherboardSync { enable, reply }).await.map(|_| serde_json::json!({"success": true, "enable": enable}))
        }
        super::RPCMethod::SetTheme => {
            let name = request.params.get("name").and_then(|v| v.as_str()).unwrap_or("cards").to_string();
            send_command(commands, |reply| DaemonCommand::SetTheme { name: name.clone(), reply }).await.map(|_| serde_json::json!({"success": true, "theme": name}))
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

fn invalid_params() -> JsonRpcError { JsonRpcError { code: -32602, message: "Invalid parameters".into(), data: None } }

fn param_error(message: &str) -> JsonRpcError {
    JsonRpcError { code: -32602, message: message.to_string(), data: None }
}

/// How long a GUI frame suppresses the built-in theme stream. Live Mode
/// renews it on every tick; single sends hold, then the daemon dashboard
/// resumes automatically.
pub const LCD_OVERRIDE_HOLD_MS: u64 = 20_000;

/// Minimal JPEG sanity gate: SOI marker first, EOI marker last, plausible size.
fn is_jpeg_skeleton(bytes: &[u8]) -> bool {
    bytes.len() > 4 && bytes.starts_with(&[0xFF, 0xD8]) && bytes.ends_with(&[0xFF, 0xD9])
}

fn now_epoch_ms() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

/// Parse `[{t,pwm},...]` into sorted, strictly-increasing u8 curve points.
fn parse_curve_points(value: &serde_json::Value) -> Option<Vec<(u8, u8)>> {
    let array = value.as_array()?;
    let mut points: Vec<(u16, u16)> = array
        .iter()
        .filter_map(|entry| {
            let t = entry.get("t")?.as_f64()?.round().clamp(0.0, 120.0) as u16;
            let d = entry
                .get("pwm")
                .and_then(|v| v.as_f64())
                .unwrap_or(50.0)
                .round()
                .clamp(0.0, 100.0) as u16;
            Some((t, d))
        })
        .collect();
    if points.len() < 2 {
        return None;
    }
    points.sort_unstable();
    let mut strictly: Vec<(u8, u8)> = Vec::with_capacity(points.len());
    for (t, d) in points {
        if strictly.last().map(|(last_t, _)| *last_t) == Some(t as u8) {
            continue; // duplicate temp: keep first
        }
        strictly.push((t as u8, d as u8));
    }
    if strictly.len() < 2 {
        return None;
    }
    Some(strictly)
}

async fn send_command(commands: &mpsc::Sender<DaemonCommand>, make: impl FnOnce(oneshot::Sender<Result<(), String>>) -> DaemonCommand) -> Result<(), JsonRpcError> {
    let (reply_tx, reply_rx) = oneshot::channel();
    commands.send(make(reply_tx)).await.map_err(|_| JsonRpcError { code: -32603, message: "daemon command queue offline".into(), data: None })?;
    match reply_rx.await.map_err(|_| JsonRpcError { code: -32603, message: "daemon command dropped".into(), data: None })? {
        Ok(()) => Ok(()),
        Err(message) => Err(JsonRpcError { code: -32000, message, data: None }),
    }
}

fn base64_decode(value: &str) -> Result<Vec<u8>, String> {
    let table = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = Vec::new(); let mut buffer = 0u32; let mut bits = 0u8;
    for byte in value.bytes().filter(|b| !b.is_ascii_whitespace() && *b != b'=') {
        let index = table.iter().position(|v| *v == byte).ok_or_else(|| "invalid base64".to_string())? as u32;
        buffer = (buffer << 6) | index; bits += 6;
        if bits >= 8 { bits -= 8; out.push((buffer >> bits) as u8); buffer &= (1 << bits) - 1; }
    }
    Ok(out)
}

fn lighting_command(mode: &str, params: &serde_json::Value, reply: oneshot::Sender<Result<(), String>>) -> DaemonCommand {
    let color = params.get("color").map(|v| [v.get("r").and_then(|x| x.as_u64()).unwrap_or(0).min(255) as u8, v.get("g").and_then(|x| x.as_u64()).unwrap_or(0).min(255) as u8, v.get("b").and_then(|x| x.as_u64()).unwrap_or(0).min(255) as u8]).unwrap_or([0, 0, 0]);
    let speed = params.get("speed").and_then(|v| v.as_u64()).unwrap_or(50).min(255) as u8;
    let saturation = params.get("saturation").and_then(|v| v.as_u64()).unwrap_or(10).min(255) as u8;
    DaemonCommand::SetLighting { mode: mode.to_string(), color, speed, saturation, reply }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_curve_points_sorts_and_dedupes() {
        let value = serde_json::json!([
            {"t": 70, "pwm": 100},
            {"t": 30, "pwm": 30},
            {"t": 50, "pwm": 60},
            {"t": 50, "pwm": 99},
        ]);
        let points = parse_curve_points(&value).unwrap();
        assert_eq!(points, vec![(30, 30), (50, 60), (70, 100)]);
    }

    #[test]
    fn parse_curve_points_clamps_ranges() {
        let value = serde_json::json!([
            {"t": -10, "pwm": -20},
            {"t": 300, "pwm": 500},
        ]);
        let points = parse_curve_points(&value).unwrap();
        assert_eq!(points, vec![(0, 0), (120, 100)]);
    }

    #[test]
    fn parse_curve_points_rejects_single_point() {
        let value = serde_json::json!([{"t": 40, "pwm": 50}]);
        assert!(parse_curve_points(&value).is_none());
    }

    #[test]
    fn parse_curve_points_rejects_garbage() {
        let value = serde_json::json!(["nope", {"pwm": 1}]);
        assert!(parse_curve_points(&value).is_none());
    }
}

#[cfg(test)]
mod control_mode_tests {
    use super::*;
    use crate::DaemonState;
    use std::sync::Arc;
    use tokio::sync::{mpsc, RwLock};

    fn request(method: &str, params: serde_json::Value) -> JsonRpcRequest {
        JsonRpcRequest { jsonrpc: "2.0".into(), method: method.into(), params, id: 1 }
    }

    async fn spawn_replier(mut rx: mpsc::Receiver<DaemonCommand>) {
        while let Some(command) = rx.recv().await {
            let reply = match command {
                DaemonCommand::SetFans { reply, .. } => reply,
                DaemonCommand::SetFanSpeed { reply, .. } => reply,
                DaemonCommand::SendLcdFrame { reply, .. } => reply,
                DaemonCommand::LcdKeepalive { reply } => reply,
                DaemonCommand::LcdSetConfig { reply, .. } => reply,
                DaemonCommand::SetLighting { reply, .. } => reply,
                DaemonCommand::SetMotherboardSync { reply, .. } => reply,
                DaemonCommand::SetTheme { reply, .. } => reply,
            };
            let _ = reply.send(Ok(()));
        }
    }

    #[tokio::test]
    async fn manual_writes_flip_auto_off_and_curve_flips_back() {
        let state = Arc::new(RwLock::new(DaemonState::default()));
        let (tx, rx) = mpsc::channel(8);
        tokio::spawn(spawn_replier(rx));

        assert!(state.read().await.fan_control_auto);

        let response = handle_rpc_request(
            &request("SetFans", serde_json::json!({"pump": 55})),
            &state, &tx).await;
        assert!(response.error.is_none());
        assert!(!state.read().await.fan_control_auto);

        let response = handle_rpc_request(
            &request("SetFanCurve", serde_json::json!({
                "channel": "pump",
                "points": [{"t": 30, "pwm": 40}, {"t": 70, "pwm": 100}],
            })),
            &state, &tx).await;
        assert!(response.error.is_none(), "{:?}", response.error);
        assert!(state.read().await.fan_control_auto);
        assert_eq!(state.read().await.pump_curve, vec![(30, 40), (70, 100)]);
    }

    #[tokio::test]
    async fn send_lcd_frame_sets_override_window() {
        let state = Arc::new(RwLock::new(DaemonState::default()));
        let (tx, rx) = mpsc::channel(8);
        tokio::spawn(spawn_replier(rx));

        let jpeg_b64 = "/9jgEf/Z"; // [FF D8 E0 11 FF D9] — minimal valid skeleton
        let response = handle_rpc_request(
            &request("SendLcdFrame", serde_json::json!({ "jpeg_b64": jpeg_b64 })),
            &state, &tx).await;
        assert!(response.error.is_none(), "{:?}", response.error);
        let state = state.read().await;
        assert!(state.lcd_gui_override);
        assert!(state.lcd_gui_override_until_ms > now_epoch_ms());
    }

    #[test]
    fn jpeg_skeleton_gate() {
        assert!(is_jpeg_skeleton(&[0xFF, 0xD8, 0x00, 0xFF, 0xD9]));
        assert!(!is_jpeg_skeleton(&[0xFF, 0xD9, 0xFF, 0xD8])); // reversed
        assert!(!is_jpeg_skeleton(b"fake"));                    // not a JPEG
        assert!(!is_jpeg_skeleton(&[0xFF, 0xD8]));              // too short
    }
}
