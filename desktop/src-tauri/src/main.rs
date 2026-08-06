//! main.rs — AI Software Factory Desktop Shell 入口 (Phase 15A-3a + 15A-3b)。
//!
//! 产品定位 (用户强制): Desktop = AI Organization Factory Application Entry,
//! 不是 Runtime 管理工具 / 不是业务系统。业务 (Organization/Intelligence/
//! Extension) 由未来层提供 — 本壳只有 launcher UI + 状态桥。
//!
//! 最小 lifecycle (架构约束):
//!   on_setup:      resolve data_root → 加载内嵌 launcher UI (src/ui)
//!                 (launcher.js 负责首次启动流程, 经 Tauri bridge 调 runtime)
//!   commands:      runtime_start/stop/status/logs/restart + health_detail
//!                  + open_console (仅 UI 导航; 无任何 business command)
//!   on_window_close: launcher 关闭 → runtime stop (graceful) → 退出
//!                 console 窗口关闭 → 仅关窗 (runtime 保持运行)
//!
//! Desktop 永远不是业务层 — 无任何 business command; 唯一入口 factory-runtime CLI。

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod launcher;
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
// 解析 (env 覆盖 + embedded + PATH 回退链, Phase 15A-3c-2)
// --------------------------------------------------------------------------

/// 未来 remote runtime 扩展点 (Phase 16+ Organization/Cloud Runtime):
/// 预留 env 名 + 注释, 本阶段不实现 — Desktop 只经本地命令桥。
/// 接入时在 resolve_runtime_cmd_at 增加第 0 优先级 (remote endpoint 探测)。
pub const RUNTIME_REMOTE_ENDPOINT_ENV: &str = "DESKTOP_RUNTIME_REMOTE_ENDPOINT";

/// App bundle 内嵌 runtime 可执行文件探测。
///
/// Tauri 打包后资源落在 resource_dir (macOS: Contents/Resources; Linux:
/// /usr/lib/<app>; Windows: 安装目录), tauri.conf bundle.resources 指向
/// dist/factory-runtime-bundle/ → resource_dir/factory-runtime-bundle/。
/// dev 模式 resource_dir 通常无 bundle → None (回退 PATH)。
pub fn embedded_runtime_cmd(resource_dir: &Path) -> Option<String> {
    for name in ["factory-runtime-bundle", "factory-runtime-bundle.exe"] {
        let candidate = resource_dir.join("factory-runtime-bundle").join(name);
        if candidate.is_file() {
            return Some(candidate.to_string_lossy().into_owned());
        }
    }
    None
}

/// runtime 命令解析 (discovery 优先级, 用户强制):
///   1. env DESKTOP_RUNTIME_CMD (显式覆盖, 测试注入)
///   2. App bundle 内嵌 runtime (resource_dir 探测)
///   3. PATH factory-runtime (默认命令, Command::new 走 PATH)
/// 未来 remote runtime endpoint 在此扩展 (第 0 优先级, 见 RUNTIME_REMOTE_ENDPOINT_ENV)。
pub fn resolve_runtime_cmd_at(resource_dir: Option<&Path>) -> String {
    match std::env::var("DESKTOP_RUNTIME_CMD") {
        Ok(c) if !c.trim().is_empty() => return c,
        _ => {}
    }
    if let Some(dir) = resource_dir {
        if let Some(cmd) = embedded_runtime_cmd(dir) {
            return cmd;
        }
    }
    runtime::DEFAULT_RUNTIME_CMD.to_string()
}

/// runtime 命令路径: 无 resource_dir 上下文 (测试/纯函数路径) — 等价
/// resolve_runtime_cmd_at(None) (env > PATH)。
pub fn resolve_runtime_cmd() -> String {
    resolve_runtime_cmd_at(None)
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

/// 简单错误提示页 (启动失败 / 崩溃时兜底展示, 用户语言, 无技术细节)。
pub fn error_html(message: &str) -> String {
    let body = html_escape(message);
    format!(
        "<!doctype html><html><head><meta charset=\"utf-8\"><style>\
         body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#1e1e1e;\
         color:#eee;padding:40px;line-height:1.6}}h1{{font-size:20px}}pre{{white-space:pre-wrap;\
         background:#2a2a2a;padding:16px;border-radius:8px;font-size:13px}}\
         </style></head><body><h1>AI Organization Factory — 启动失败</h1><pre>{body}</pre>\
         <p>请关闭窗口后重新打开应用重试。</p></body></html>"
    )
}

// --------------------------------------------------------------------------
// Tauri commands — 最小桥 (start/stop/status/logs/restart/health_detail/
// open_console; 无任何 business command)
// --------------------------------------------------------------------------
//
// 全部命令从 AppState 读 data_root (JS 不传路径); 错误统一经 friendly_error
// 转为用户语言 (禁暴露 Python/Rust/uvicorn/subprocess 等细节)。

/// 序列化错误兜底 (不可达路径 — serde_json 对固定结构不会失败)。
fn json_err(e: serde_json::Error) -> String {
    format!("Factory startup failed: 数据编码错误 ({e})")
}

#[tauri::command]
fn cmd_runtime_start(state: tauri::State<AppState>) -> Result<String, String> {
    let bridge = state.bridge.clone();
    let st = bridge
        .runtime_start(&state.data_root)
        .map_err(|e| launcher::friendly_error(&e))?;
    serde_json::to_string(&st).map_err(json_err)
}

#[tauri::command]
fn cmd_runtime_stop(state: tauri::State<AppState>) -> Result<String, String> {
    let bridge = state.bridge.clone();
    let st = bridge
        .runtime_stop(&state.data_root)
        .map_err(|e| launcher::friendly_error(&e))?;
    serde_json::to_string(&st).map_err(json_err)
}

#[tauri::command]
fn cmd_runtime_status(state: tauri::State<AppState>) -> Result<String, String> {
    let bridge = state.bridge.clone();
    let st = bridge
        .runtime_status(&state.data_root)
        .map_err(|e| launcher::friendly_error(&e))?;
    serde_json::to_string(&st).map_err(json_err)
}

#[tauri::command]
fn cmd_runtime_logs(state: tauri::State<AppState>, lines: Option<usize>) -> Result<String, String> {
    let bridge = state.bridge.clone();
    let bundle = bridge
        .runtime_logs(&state.data_root, lines.unwrap_or(200))
        .map_err(|e| launcher::friendly_error(&e))?;
    serde_json::to_string(&bundle).map_err(json_err)
}

/// System Recovery: stop (幂等) → start (健康等待)。
#[tauri::command]
fn cmd_runtime_restart(state: tauri::State<AppState>) -> Result<String, String> {
    let bridge = state.bridge.clone();
    let st = bridge
        .runtime_restart(&state.data_root)
        .map_err(|e| launcher::friendly_error(&e))?;
    serde_json::to_string(&st).map_err(json_err)
}

/// 产品级健康视图: Runtime/Core/Console 组件状态 + uptime/version/port。
#[tauri::command]
fn cmd_health_detail(state: tauri::State<AppState>) -> Result<String, String> {
    let bridge = state.bridge.clone();
    let st = bridge
        .runtime_status(&state.data_root)
        .map_err(|e| launcher::friendly_error(&e))?;
    let hd = runtime::health_detail(&st);
    serde_json::to_string(&hd).map_err(json_err)
}

/// 打开 Factory Console 窗口 (加载 http://127.0.0.1:<port>)。
/// 纯 UI 导航命令 — 不触碰任何业务数据。
#[tauri::command]
fn cmd_open_console(app: tauri::AppHandle, port: u16) -> Result<(), String> {
    let url = format!("http://127.0.0.1:{port}");
    let parsed: tauri::Url = url.parse().map_err(|e| format!("无法打开控制台 ({e})"))?;
    WebviewWindowBuilder::new(&app, "console", WebviewUrl::External(parsed))
        .title("AI Organization Factory — Console")
        .inner_size(1280.0, 800.0)
        .min_inner_size(960.0, 600.0)
        .build()
        .map(|_| ())
        .map_err(|e| format!("无法打开控制台窗口 ({e})"))
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
            cmd_runtime_logs,
            cmd_runtime_restart,
            cmd_health_detail,
            cmd_open_console
        ])
        .setup(|app| {
            let data_root = resolve_data_root(app);
            // discovery: env > embedded (resource_dir) > PATH (15A-3c-2)
            let resource_dir = app.path().resource_dir().ok();
            let bridge = Bridge::new(resolve_runtime_cmd_at(resource_dir.as_deref()));
            eprintln!(
                "desktop: data_root={} runtime_cmd={}",
                data_root.display(),
                bridge.cmd()
            );
            app.manage(AppState {
                bridge,
                data_root,
                shutting_down: Mutex::new(false),
            });

            // Launcher 窗口 (内嵌资源 src/ui) — 首次启动流程由 launcher.js 驱动
            WebviewWindowBuilder::new(app, "launcher", WebviewUrl::App("launcher.html".into()))
                .title("AI Organization Factory")
                .inner_size(1120.0, 780.0)
                .min_inner_size(900.0, 640.0)
                .build()?;
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                let state = window.app_handle().state::<AppState>();
                let label = window.label().to_string();
                if label != "launcher" {
                    // Console 窗口关闭 → 仅关窗, runtime 保持运行 (回到 launcher)
                    return;
                }
                // Launcher 关闭 → graceful stop (SIGTERM 语义在 factory-runtime 内) → 退出
                let mut shutting_down = state.shutting_down.lock().unwrap();
                if *shutting_down {
                    return; // 已触发 graceful, 放行关闭
                }
                *shutting_down = true;
                api.prevent_close();
                let bridge = state.bridge.clone();
                let data_root = state.data_root.clone();
                let app_handle = window.app_handle().clone();
                std::thread::spawn(move || {
                    if let Err(e) = shutdown_flow(&bridge, &data_root) {
                        eprintln!("desktop: shutdown error: {e}");
                    }
                    app_handle.exit(0);
                });
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
