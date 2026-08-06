//! main.rs — AI Software Factory Desktop Shell 入口 (Phase 15A-3a)。
//!
//! 最小 lifecycle (架构约束):
//!   on_setup:     resolve data_root → runtime start (经 factory-runtime CLI)
//!                → 状态轮询 ready → Console 健康检查 (/api/dashboard)
//!                → WebView 加载 http://127.0.0.1:<port>
//!   on_window_close: runtime stop (graceful) → 退出
//!   崩溃:        status 非 ready / 健康失败 → 简单错误提示窗口
//!
//! Desktop 永远不是业务层 — 无任何 business command; 唯一入口 factory-runtime CLI。

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod runtime;
#[cfg(test)]
mod tests;

use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};

use runtime::{Bridge, BridgeError};

/// 启动流程总超时 (含 runtime 健康等待)。
pub const LAUNCH_TIMEOUT: Duration = Duration::from_secs(120);

/// 状态轮询间隔。
pub const STATUS_POLL_INTERVAL: Duration = Duration::from_millis(200);

/// 应用状态 (setup 时 manage)。
pub struct AppState {
    pub bridge: Bridge,
    pub data_root: PathBuf,
    pub shutting_down: Mutex<bool>,
}

/// 启动成功结果 (port = Console 监听端口)。
#[derive(Debug, Clone)]
pub struct Launched {
    pub port: u16,
    pub status: runtime::RuntimeStatus,
}

// --------------------------------------------------------------------------
// 最小 lifecycle (纯函数, 不依赖 GUI — 集成测试直接调用)
// --------------------------------------------------------------------------

/// 启动流程: ensure data_root → `factory-runtime start` → 轮询 ready →
/// Console 健康检查 (/api/dashboard) → 返回 port。
///
/// 失败场景: runtime unavailable / crash / port conflict / permission /
/// 超时 / 健康不可达 → BridgeError (setup 捕获后弹错误窗口)。
pub fn launch_flow(
    bridge: &Bridge,
    data_root: &Path,
    timeout: Duration,
) -> Result<Launched, BridgeError> {
    bridge.ensure_data_root(data_root)?;
    let mut st = bridge.runtime_start(data_root)?;
    let port = st.port.ok_or_else(|| {
        BridgeError::Parse(format!("start 未返回 Console 端口 (status={})", st.status))
    })?;

    let deadline = Instant::now() + timeout;
    while st.status != "ready" {
        if Instant::now() >= deadline {
            return Err(BridgeError::Timeout(timeout));
        }
        if st.status == "failed" {
            return Err(BridgeError::RuntimeFailed(
                "启动后 runtime 进入 failed 状态".into(),
            ));
        }
        std::thread::sleep(STATUS_POLL_INTERVAL);
        st = bridge.runtime_status(data_root)?;
    }

    // Console 可用性: HTTP GET /api/dashboard
    if !runtime::http_health(port, Duration::from_secs(3)) {
        return Err(BridgeError::Health(format!(
            "http://127.0.0.1:{port}{} 不可达",
            runtime::HEALTH_PATH
        )));
    }
    Ok(Launched { port, status: st })
}

/// 关闭流程: `factory-runtime stop` (graceful) → 校验无残留
/// (状态非运行中 + core/console pid 文件已清理)。
pub fn shutdown_flow(
    bridge: &Bridge,
    data_root: &Path,
) -> Result<runtime::RuntimeStatus, BridgeError> {
    let _st = bridge.runtime_stop(data_root)?;
    let st2 = bridge.runtime_status(data_root)?;
    if st2.is_running() {
        return Err(BridgeError::RuntimeFailed(format!(
            "stop 后仍处于 {}",
            st2.status
        )));
    }
    for name in ["console", "core"] {
        let pid_file = data_root.join("config").join(format!("{name}.pid"));
        if pid_file.exists() {
            return Err(BridgeError::RuntimeFailed(format!(
                "stop 后残留 {name}.pid (clean shutdown 失败)"
            )));
        }
    }
    Ok(st2)
}

// --------------------------------------------------------------------------
// 解析 (env 覆盖)
// --------------------------------------------------------------------------

/// runtime 命令路径: env DESKTOP_RUNTIME_CMD 覆盖, 否则默认。
pub fn resolve_runtime_cmd() -> String {
    match std::env::var("DESKTOP_RUNTIME_CMD") {
        Ok(c) if !c.trim().is_empty() => c,
        _ => runtime::DEFAULT_RUNTIME_CMD.to_string(),
    }
}

/// 数据根: env DESKTOP_DATA_ROOT 覆盖, 否则平台规范应用数据目录
/// (macOS: ~/Library/Application Support/ai-software-factory)。
pub fn resolve_data_root(app: &tauri::App) -> PathBuf {
    if let Ok(p) = std::env::var("DESKTOP_DATA_ROOT") {
        if !p.trim().is_empty() {
            return PathBuf::from(p);
        }
    }
    app.path()
        .app_data_dir()
        .unwrap_or_else(|_| PathBuf::from("."))
}

// --------------------------------------------------------------------------
// 错误提示页 (零插件: data: URL)
// --------------------------------------------------------------------------

/// 百分号编码 (RFC 3986 unreserved 保留; UTF-8 字节逐字节编码)。
pub fn percent_encode(input: &str) -> String {
    let mut out = String::with_capacity(input.len() * 3);
    for b in input.bytes() {
        match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                out.push(b as char)
            }
            _ => out.push_str(&format!("%{b:02X}")),
        }
    }
    out
}

/// HTML 转义 (错误消息注入前)。
pub fn html_escape(input: &str) -> String {
    input
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
}

/// 简单错误提示页 (启动失败 / 崩溃时展示)。
pub fn error_html(message: &str) -> String {
    let body = html_escape(message);
    format!(
        "<!doctype html><html><head><meta charset=\"utf-8\"><style>\
         body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#1e1e1e;\
         color:#eee;padding:40px;line-height:1.6}}h1{{font-size:20px}}pre{{white-space:pre-wrap;\
         background:#2a2a2a;padding:16px;border-radius:8px;font-size:13px}}\
         </style></head><body><h1>AI Software Factory — 启动失败</h1><pre>{body}</pre>\
         <p>请确认 factory-runtime 已安装 (pip install -e factory-runtime) 且数据目录可写, \
         然后关闭窗口重试。</p></body></html>"
    )
}

// --------------------------------------------------------------------------
// Tauri commands — 最小桥 (start/stop/status/logs, 无 business command)
// --------------------------------------------------------------------------

#[tauri::command]
fn cmd_runtime_start(data_root: String) -> Result<String, String> {
    let bridge = Bridge::from_env();
    let st = bridge
        .runtime_start(Path::new(&data_root))
        .map_err(|e| e.to_string())?;
    serde_json::to_string(&st).map_err(|e| e.to_string())
}

#[tauri::command]
fn cmd_runtime_stop(data_root: String) -> Result<String, String> {
    let bridge = Bridge::from_env();
    let st = bridge
        .runtime_stop(Path::new(&data_root))
        .map_err(|e| e.to_string())?;
    serde_json::to_string(&st).map_err(|e| e.to_string())
}

#[tauri::command]
fn cmd_runtime_status(data_root: String) -> Result<String, String> {
    let bridge = Bridge::from_env();
    let st = bridge
        .runtime_status(Path::new(&data_root))
        .map_err(|e| e.to_string())?;
    serde_json::to_string(&st).map_err(|e| e.to_string())
}

#[tauri::command]
fn cmd_runtime_logs(data_root: String, lines: Option<usize>) -> Result<String, String> {
    let bridge = Bridge::from_env();
    let bundle = bridge
        .runtime_logs(Path::new(&data_root), lines.unwrap_or(50))
        .map_err(|e| e.to_string())?;
    serde_json::to_string(&bundle).map_err(|e| e.to_string())
}

// --------------------------------------------------------------------------
// 入口
// --------------------------------------------------------------------------

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            cmd_runtime_start,
            cmd_runtime_stop,
            cmd_runtime_status,
            cmd_runtime_logs
        ])
        .setup(|app| {
            let data_root = resolve_data_root(app);
            let bridge = Bridge::from_env();
            eprintln!(
                "desktop: data_root={} runtime_cmd={}",
                data_root.display(),
                bridge.cmd()
            );

            match launch_flow(&bridge, &data_root, LAUNCH_TIMEOUT) {
                Ok(launched) => {
                    eprintln!("desktop: runtime ready, console on port {}", launched.port);
                    let url = format!("http://127.0.0.1:{}", launched.port);
                    let parsed: tauri::Url = url
                        .parse()
                        .map_err(|e| format!("WebView URL 解析失败 {url}: {e}"))?;
                    WebviewWindowBuilder::new(app, "main", WebviewUrl::External(parsed))
                        .title("AI Software Factory")
                        .inner_size(1280.0, 800.0)
                        .min_inner_size(960.0, 600.0)
                        .build()?;
                }
                Err(e) => {
                    // 崩溃 / 启动失败 → 简单错误提示窗口
                    eprintln!("desktop: runtime launch failed: {e}");
                    let html = error_html(&format!("Runtime 启动失败\n\n{e}"));
                    let url = format!("data:text/html,{}", percent_encode(&html));
                    let parsed: tauri::Url = url
                        .parse()
                        .map_err(|e| format!("错误页 URL 解析失败: {e}"))?;
                    WebviewWindowBuilder::new(app, "error", WebviewUrl::External(parsed))
                        .title("AI Software Factory — 启动失败")
                        .inner_size(680.0, 420.0)
                        .build()?;
                }
            }
            app.manage(AppState {
                bridge,
                data_root,
                shutting_down: Mutex::new(false),
            });
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                let state = window.app_handle().state::<AppState>();
                let mut shutting_down = state.shutting_down.lock().unwrap();
                if *shutting_down {
                    return; // 已触发 graceful, 放行关闭
                }
                *shutting_down = true;
                api.prevent_close();
                let bridge = state.bridge.clone();
                let data_root = state.data_root.clone();
                let app_handle = window.app_handle().clone();
                let label = window.label().to_string();
                std::thread::spawn(move || {
                    // graceful stop (SIGTERM 语义在 factory-runtime 内), 完成后再关窗
                    if let Err(e) = shutdown_flow(&bridge, &data_root) {
                        eprintln!("desktop: shutdown error: {e}");
                    }
                    if let Some(w) = app_handle.get_webview_window(&label) {
                        let _ = w.close();
                    }
                });
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
