//! runtime.rs — Desktop ↔ factory-runtime 最小运行时桥 (Phase 15A-3a)。
//!
//! 架构约束 (用户强制, 必须遵守):
//! 1. Desktop Shell 永远不是业务层 — 本模块只有 start/stop/status/logs,
//!    无任何 business command (禁 Agent/Organization/Workflow/Task/Decision 逻辑)
//! 2. Runtime 唯一控制 — 所有操作只经 `factory-runtime` CLI 子进程
//!    (Rust 禁止直接 spawn Core/Console, 禁止直接管理 uvicorn);
//!    命令路径可用 env `DESKTOP_RUNTIME_CMD` 覆盖 (测试注入 fake)
//! 3. 数据目录保持 `<data_root>` (不新建额外目录), 全部状态由 factory-runtime 管理
//!
//! 命令形态 (factory-runtime CLI, 见 factory-runtime/runtime/cli.py):
//!   factory-runtime --root <root> start  --json   → 状态 JSON (含 port)
//!   factory-runtime --root <root> stop   --json   → 状态 JSON (幂等)
//!   factory-runtime --root <root> status --json   → 状态 JSON
//!   logs 由本模块直接 tail <root>/logs/{runtime,core,console}.log

use std::fs;
use std::io::Read;
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

/// 默认 factory-runtime CLI 命令 (env DESKTOP_RUNTIME_CMD 覆盖)。
pub const DEFAULT_RUNTIME_CMD: &str = "factory-runtime";

/// Console 健康检查路径。
pub const HEALTH_PATH: &str = "/api/dashboard";

/// 日志文件 (相对 <data_root>/logs/)。
pub const LOG_FILES: [&str; 3] = ["runtime.log", "core.log", "console.log"];

/// 运行中状态集合 (与 factory-runtime/runtime/state.py RUNNING_STATUSES 对齐)。
pub const RUNNING_STATUSES: [&str; 2] = ["starting", "ready"];

// --------------------------------------------------------------------------
// 错误
// --------------------------------------------------------------------------

/// bridge 域错误 (可展示给用户/UI)。
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum BridgeError {
    /// 命令不存在 / 无执行权限 (runtime unavailable)
    SpawnFailed(String),
    /// 子进程非零退出 (runtime crash / port conflict / CLI 报错)
    Exit {
        code: i32,
        stdout: String,
        stderr: String,
    },
    /// 子进程超时被强杀
    Timeout(Duration),
    /// 输出解析失败 (非法 JSON / 缺字段)
    Parse(String),
    /// 数据根不可用 (非目录 / 不可写 — permission failure)
    DataRoot(String),
    /// Console 健康检查失败 (启动后不可达)
    Health(String),
    /// runtime 进入 failed 状态 (start 后崩溃)
    RuntimeFailed(String),
}

impl std::fmt::Display for BridgeError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            BridgeError::SpawnFailed(msg) => write!(f, "runtime 命令不可用: {msg}"),
            BridgeError::Exit {
                code,
                stdout,
                stderr,
            } => write!(
                f,
                "runtime 命令失败 (exit={code}){}{}",
                if stdout.trim().is_empty() {
                    String::new()
                } else {
                    format!(" stdout: {}", stdout.trim())
                },
                if stderr.trim().is_empty() {
                    String::new()
                } else {
                    format!(" stderr: {}", stderr.trim())
                }
            ),
            BridgeError::Timeout(d) => write!(f, "runtime 命令超时 ({d:?})"),
            BridgeError::Parse(msg) => write!(f, "runtime 输出解析失败: {msg}"),
            BridgeError::DataRoot(msg) => write!(f, "数据目录不可用: {msg}"),
            BridgeError::Health(msg) => write!(f, "Console 健康检查失败: {msg}"),
            BridgeError::RuntimeFailed(msg) => write!(f, "runtime 状态异常: {msg}"),
        }
    }
}

impl std::error::Error for BridgeError {}

// --------------------------------------------------------------------------
// 状态 / 日志类型
// --------------------------------------------------------------------------

/// factory-runtime status JSON 的结构化视图
/// (与 factory-runtime/runtime/state.py RuntimeState.to_dict + status() 对齐)。
#[derive(Debug, Clone, Default, PartialEq, serde::Serialize)]
pub struct RuntimeStatus {
    /// idle|starting|ready|stopping|stopped|failed
    pub status: String,
    pub pid: Option<i64>,
    pub port: Option<u16>,
    pub version: String,
    pub started_at: Option<String>,
    pub stopped_at: Option<String>,
    pub core_alive: bool,
    pub console_alive: bool,
    pub core_exit_code: Option<i32>,
    pub console_exit_code: Option<i32>,
}

impl RuntimeStatus {
    pub fn is_running(&self) -> bool {
        RUNNING_STATUSES.contains(&self.status.as_str())
    }
}

/// 日志读取结果 (<data_root>/logs/ 三个文件尾部)。
#[derive(Debug, Clone, Default, PartialEq, serde::Serialize)]
pub struct LogBundle {
    pub root: PathBuf,
    pub runtime: Vec<String>,
    pub core: Vec<String>,
    pub console: Vec<String>,
}

impl LogBundle {
    pub fn is_empty(&self) -> bool {
        self.runtime.is_empty() && self.core.is_empty() && self.console.is_empty()
    }
}

// --------------------------------------------------------------------------
// Bridge
// --------------------------------------------------------------------------

/// 与 factory-runtime CLI 的最小桥。
///
/// 全部操作经 `Command::new(cmd)` 子进程; `envs` 为附加环境变量
/// (测试注入 FAKE_RUNTIME_* 用, 不改进程全局环境 — 保证测试可并行)。
#[derive(Debug, Clone)]
pub struct Bridge {
    cmd: String,
    envs: Vec<(String, String)>,
    start_timeout: Duration,
    stop_timeout: Duration,
    status_timeout: Duration,
}

impl Bridge {
    /// 默认时间: start 90s (含 runtime 健康等待) / stop 30s / status 10s。
    pub fn new(cmd: impl Into<String>) -> Self {
        Self::with_timeouts(
            cmd,
            Duration::from_secs(90),
            Duration::from_secs(30),
            Duration::from_secs(10),
            Duration::from_secs(10),
        )
    }

    /// 测试用: 自定义各命令超时 (挂起/超时场景)。
    pub fn with_timeouts(
        cmd: impl Into<String>,
        start_timeout: Duration,
        stop_timeout: Duration,
        status_timeout: Duration,
        _logs_timeout: Duration,
    ) -> Self {
        Self {
            cmd: cmd.into(),
            envs: Vec::new(),
            start_timeout,
            stop_timeout,
            status_timeout,
        }
    }

    /// 命令路径解析: env DESKTOP_RUNTIME_CMD 覆盖, 否则默认。
    pub fn from_env() -> Self {
        match std::env::var("DESKTOP_RUNTIME_CMD") {
            Ok(c) if !c.trim().is_empty() => Self::new(c),
            _ => Self::new(DEFAULT_RUNTIME_CMD),
        }
    }

    /// 附加子进程环境变量 (测试注入 fake 行为, 不影响进程全局 env)。
    pub fn with_env(mut self, key: &str, value: &str) -> Self {
        self.envs.push((key.to_string(), value.to_string()));
        self
    }

    pub fn cmd(&self) -> &str {
        &self.cmd
    }

    // ------------------------------------------------------------- 命令

    /// 启动: `factory-runtime --root <root> start --json`。
    /// 返回状态 (ready + port)。CLI 内部已做健康等待; failed → Err。
    pub fn runtime_start(&self, data_root: &Path) -> Result<RuntimeStatus, BridgeError> {
        self.ensure_data_root(data_root)?;
        let out = self.run(
            &[
                "--root",
                data_root.to_str().ok_or_else(|| {
                    BridgeError::Parse(format!("data_root 非 UTF-8: {}", data_root.display()))
                })?,
                "start",
                "--json",
            ],
            self.start_timeout,
        )?;
        let st = parse_status(&out.stdout)?;
        if st.status == "failed" {
            return Err(BridgeError::RuntimeFailed(
                "start 后 runtime 进入 failed 状态".into(),
            ));
        }
        Ok(st)
    }

    /// 停止: `factory-runtime --root <root> stop --json` (幂等)。
    pub fn runtime_stop(&self, data_root: &Path) -> Result<RuntimeStatus, BridgeError> {
        let out = self.run(
            &[
                "--root",
                data_root.to_str().ok_or_else(|| {
                    BridgeError::Parse(format!("data_root 非 UTF-8: {}", data_root.display()))
                })?,
                "stop",
                "--json",
            ],
            self.stop_timeout,
        )?;
        parse_status(&out.stdout)
    }

    /// 状态: `factory-runtime --root <root> status --json`。
    pub fn runtime_status(&self, data_root: &Path) -> Result<RuntimeStatus, BridgeError> {
        let out = self.run(
            &[
                "--root",
                data_root.to_str().ok_or_else(|| {
                    BridgeError::Parse(format!("data_root 非 UTF-8: {}", data_root.display()))
                })?,
                "status",
                "--json",
            ],
            self.status_timeout,
        )?;
        parse_status(&out.stdout)
    }

    /// 重启: `stop` (幂等) → `start` (健康等待)。用于 System Recovery。
    /// 组合语义, 不经 CLI restart — 保证 stop 失败/残留可被 start 覆盖。
    pub fn runtime_restart(&self, data_root: &Path) -> Result<RuntimeStatus, BridgeError> {
        let _ = self.runtime_stop(data_root)?;
        let st = self.runtime_start(data_root)?;
        if st.status == "failed" {
            return Err(BridgeError::RuntimeFailed(
                "重启后 runtime 进入 failed 状态".into(),
            ));
        }
        Ok(st)
    }

    /// 日志: 直接 tail <data_root>/logs/{runtime,core,console}.log
    /// (缺失文件 → 空; 不可读 → Err)。不调用 CLI — logs 属本地文件读取。
    pub fn runtime_logs(&self, data_root: &Path, lines: usize) -> Result<LogBundle, BridgeError> {
        let logs_dir = data_root.join("logs");
        let mut bundle = LogBundle {
            root: data_root.to_path_buf(),
            ..Default::default()
        };
        for name in LOG_FILES {
            let path = logs_dir.join(name);
            let target = match name {
                "runtime.log" => &mut bundle.runtime,
                "core.log" => &mut bundle.core,
                _ => &mut bundle.console,
            };
            *target = match read_tail(&path, lines) {
                Ok(v) => v,
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => Vec::new(),
                Err(e) => {
                    return Err(BridgeError::DataRoot(format!(
                        "读取日志 {} 失败: {e}",
                        path.display()
                    )))
                }
            };
        }
        Ok(bundle)
    }

    // ------------------------------------------------------------- 内部

    /// data_root 校验: 存在且为目录 + 可写探测 (permission failure 前置拦截)。
    pub fn ensure_data_root(&self, data_root: &Path) -> Result<(), BridgeError> {
        if data_root.exists() && !data_root.is_dir() {
            return Err(BridgeError::DataRoot(format!(
                "不是目录: {}",
                data_root.display()
            )));
        }
        if !data_root.exists() {
            fs::create_dir_all(data_root).map_err(|e| {
                BridgeError::DataRoot(format!("创建失败 {}: {e}", data_root.display()))
            })?;
        }
        let probe = data_root.join(format!(".write_probe_{}", std::process::id()));
        match fs::File::create(&probe) {
            Ok(_) => {
                let _ = fs::remove_file(&probe);
            }
            Err(e) => {
                return Err(BridgeError::DataRoot(format!(
                    "不可写 {}: {e}",
                    data_root.display()
                )))
            }
        }
        Ok(())
    }

    /// 子进程执行: 并发读 stdout/stderr (防管道死锁) + 超时强杀。
    fn run(&self, args: &[&str], timeout: Duration) -> Result<CmdOutput, BridgeError> {
        let mut cmd = Command::new(&self.cmd);
        cmd.args(args).stdout(Stdio::piped()).stderr(Stdio::piped());
        for (k, v) in &self.envs {
            cmd.env(k, v);
        }
        let mut child = cmd.spawn().map_err(|e| {
            let kind = e.kind();
            BridgeError::SpawnFailed(format!("{} ({kind:?})", self.cmd))
        })?;

        let mut out_pipe = child.stdout.take().expect("stdout piped");
        let mut err_pipe = child.stderr.take().expect("stderr piped");
        let out_thread = std::thread::spawn(move || {
            let mut buf = Vec::new();
            let _ = out_pipe.read_to_end(&mut buf);
            buf
        });
        let err_thread = std::thread::spawn(move || {
            let mut buf = Vec::new();
            let _ = err_pipe.read_to_end(&mut buf);
            buf
        });

        let deadline = Instant::now() + timeout;
        let status = loop {
            match child.try_wait() {
                Ok(Some(st)) => break st,
                Ok(None) => {
                    if Instant::now() >= deadline {
                        let _ = child.kill();
                        let _ = child.wait();
                        return Err(BridgeError::Timeout(timeout));
                    }
                    std::thread::sleep(Duration::from_millis(20));
                }
                Err(e) => return Err(BridgeError::SpawnFailed(format!("wait: {e}"))),
            }
        };

        let stdout = out_thread.join().unwrap_or_default();
        let _stderr = err_thread.join().unwrap_or_default(); // 读空防死锁; 内容仅错误路径用
        let code = status.code().unwrap_or(-1);
        if !status.success() {
            return Err(BridgeError::Exit {
                code,
                stdout: String::from_utf8_lossy(&stdout).into_owned(),
                stderr: String::from_utf8_lossy(&_stderr).into_owned(),
            });
        }
        Ok(CmdOutput {
            stdout: String::from_utf8_lossy(&stdout).into_owned(),
        })
    }
}

struct CmdOutput {
    stdout: String,
}

// --------------------------------------------------------------------------
// 解析 / 健康 / 日志工具 (pub 供 lifecycle 与测试复用)
// --------------------------------------------------------------------------

/// 解析 factory-runtime `--json` 输出 → RuntimeStatus (失败安全默认值)。
pub fn parse_status(json_str: &str) -> Result<RuntimeStatus, BridgeError> {
    let v: serde_json::Value = serde_json::from_str(json_str)
        .map_err(|e| BridgeError::Parse(format!("非法 JSON: {e}")))?;
    let obj = v
        .as_object()
        .ok_or_else(|| BridgeError::Parse("JSON 不是对象".into()))?;
    let get_str =
        |k: &str| -> Option<String> { obj.get(k).and_then(|x| x.as_str()).map(|s| s.to_string()) };
    let get_i64 = |k: &str| -> Option<i64> { obj.get(k).and_then(|x| x.as_i64()) };
    let get_bool = |k: &str| -> bool { obj.get(k).and_then(|x| x.as_bool()).unwrap_or(false) };
    let port = obj
        .get("port")
        .and_then(|x| x.as_u64())
        .and_then(|p| u16::try_from(p).ok());
    Ok(RuntimeStatus {
        status: get_str("status").unwrap_or_else(|| "idle".into()),
        pid: get_i64("pid"),
        port,
        version: get_str("version").unwrap_or_default(),
        started_at: get_str("started_at"),
        stopped_at: get_str("stopped_at"),
        core_alive: get_bool("core_alive"),
        console_alive: get_bool("console_alive"),
        core_exit_code: get_i64("core_exit_code").map(|v| v as i32),
        console_exit_code: get_i64("console_exit_code").map(|v| v as i32),
    })
}

/// 最小 HTTP GET 健康检查 (std 实现, 零额外依赖): GET /api/dashboard。
/// 2xx 视为健康。
pub fn http_health(port: u16, timeout: Duration) -> bool {
    let addr = format!("127.0.0.1:{port}");
    let addr: std::net::SocketAddr = match addr.parse() {
        Ok(a) => a,
        Err(_) => return false,
    };
    let mut stream = match TcpStream::connect_timeout(&addr, timeout) {
        Ok(s) => s,
        Err(_) => return false,
    };
    let _ = stream.set_read_timeout(Some(timeout));
    let req = format!("GET {HEALTH_PATH} HTTP/1.1\r\nHost: {addr}\r\nConnection: close\r\n\r\n");
    use std::io::Write;
    if stream.write_all(req.as_bytes()).is_err() {
        return false;
    }
    let mut buf = [0u8; 512];
    let n = match stream.read(&mut buf) {
        Ok(n) => n,
        Err(_) => return false,
    };
    let head = String::from_utf8_lossy(&buf[..n]);
    head.starts_with("HTTP/1.1 2") || head.starts_with("HTTP/1.0 2")
}

/// 读文件尾部 N 行 (缺失 → NotFound, 非 UTF-8 字节 lossy 转换)。
pub fn read_tail(path: &Path, lines: usize) -> std::io::Result<Vec<String>> {
    let bytes = fs::read(path)?;
    let content = String::from_utf8_lossy(&bytes);
    let all: Vec<String> = content.lines().map(|s| s.to_string()).collect();
    let start = all.len().saturating_sub(lines);
    Ok(all[start..].to_vec())
}

// --------------------------------------------------------------------------
// health_detail (Phase 15A-3b: 产品级健康视图)
// --------------------------------------------------------------------------

/// 健康组件 (Runtime/Core/Console — 已实现)。
/// 未来项 Organization/Agents/Knowledge/Learning 由 UI 预留占位, 不在此解析。
#[derive(Debug, Clone, PartialEq, serde::Serialize)]
pub struct ComponentHealth {
    pub name: &'static str,
    pub ok: bool,
    pub status: String,
    pub reason: Option<String>,
    pub suggestion: Option<String>,
}

/// 产品级健康视图 (health_detail command 输出)。
/// 全部从 status JSON 解析 — Desktop 不维护任何自身状态。
#[derive(Debug, Clone, PartialEq, serde::Serialize)]
pub struct HealthDetail {
    /// 全部组件健康 (Runtime ready + Core alive + Console alive)。
    pub overall: bool,
    pub version: String,
    pub port: Option<u16>,
    /// 运行时长 (秒, 自 started_at)。
    pub uptime_secs: Option<u64>,
    /// 组件顺序固定: Runtime → Core → Console。
    pub components: Vec<ComponentHealth>,
}

/// 从 RuntimeStatus 生成健康视图 (reason/suggestion 用用户语言)。
pub fn health_detail(st: &RuntimeStatus) -> HealthDetail {
    let (rt_ok, rt_reason, rt_suggestion) = match st.status.as_str() {
        "ready" => (true, None, None),
        "starting" => (false, Some("工厂正在初始化".into()), Some("请稍候…".into())),
        "stopping" => (false, Some("工厂正在关闭".into()), None),
        "stopped" => (
            false,
            Some("工厂服务已停止".into()),
            Some("点击「打开 Factory Console」或使用「系统恢复」重启".into()),
        ),
        "failed" => (
            false,
            Some("工厂服务运行异常".into()),
            Some("请使用「系统恢复」重启工厂".into()),
        ),
        _ => (
            false,
            Some("工厂尚未启动".into()),
            Some("请点击「打开 Factory Console」启动工厂".into()),
        ),
    };
    let runtime = ComponentHealth {
        name: "Runtime",
        ok: rt_ok,
        status: st.status.clone(),
        reason: rt_reason,
        suggestion: rt_suggestion,
    };
    let core = ComponentHealth {
        name: "Core",
        ok: st.core_alive,
        status: if st.core_alive {
            "alive".into()
        } else {
            "down".into()
        },
        reason: if st.core_alive {
            None
        } else {
            Some("核心服务未运行".into())
        },
        suggestion: if st.core_alive {
            None
        } else {
            Some("请重启工厂服务".into())
        },
    };
    let console = ComponentHealth {
        name: "Console",
        ok: st.console_alive,
        status: if st.console_alive {
            "alive".into()
        } else {
            "down".into()
        },
        reason: if st.console_alive {
            None
        } else {
            Some("控制台未运行".into())
        },
        suggestion: if st.console_alive {
            None
        } else {
            Some("请重启工厂服务".into())
        },
    };
    let components = vec![runtime, core, console];
    let overall = components.iter().all(|c| c.ok);
    HealthDetail {
        overall,
        version: st.version.clone(),
        port: st.port,
        uptime_secs: uptime_secs_at(st.started_at.as_deref(), now_unix()),
        components,
    }
}

/// 当前 Unix 秒 (测试可用 uptime_secs_at 注入 now)。
pub fn now_unix() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0)
}

/// uptime 秒数: started_at (ISO8601) 相对 now_unix 的差值 (纯函数, 可测)。
pub fn uptime_secs_at(started_at: Option<&str>, now_unix: i64) -> Option<u64> {
    let t = parse_iso8601_secs(started_at?)?;
    Some((now_unix - t).max(0) as u64)
}

/// 解析最小 ISO8601 时间戳 "YYYY-MM-DDTHH:MM:SS" (+ 可选 Z / 秒小数截断)。
/// 无外部依赖 (std 手写)。解析失败 → None。
pub fn parse_iso8601_secs(s: &str) -> Option<i64> {
    let t = s
        .strip_suffix('Z')
        .or_else(|| s.strip_suffix("+00:00"))
        .unwrap_or(s);
    let t = t.split('.').next().unwrap_or(t); // 截断小数秒
    if t.len() < 19 || t.as_bytes()[10] != b'T' {
        return None;
    }
    let (date, time) = t.split_at(10);
    let mut dit = date.split('-');
    let y: i64 = dit.next()?.parse().ok()?;
    let m: i64 = dit.next()?.parse().ok()?;
    let d: i64 = dit.next()?.parse().ok()?;
    let mut tit = time[1..].split(':');
    let hh: i64 = tit.next()?.parse().ok()?;
    let mm: i64 = tit.next()?.parse().ok()?;
    let ss: i64 = tit.next()?.parse().ok()?;
    if !(1..=12).contains(&m) || !(1..=31).contains(&d) || hh > 23 || mm > 59 || ss > 61 {
        return None;
    }
    Some(days_from_civil(y, m, d) * 86400 + hh * 3600 + mm * 60 + ss)
}

/// 公历 → 1970-01-01 起天数 (Howard Hinnant 算法)。
fn days_from_civil(y: i64, m: i64, d: i64) -> i64 {
    let y = if m <= 2 { y - 1 } else { y };
    let era = if y >= 0 { y } else { y - 399 } / 400;
    let yoe = y - era * 400;
    let mp = (m + 9) % 12;
    let doy = (153 * mp + 2) / 5 + d - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    era * 146097 + doe - 719468
}

#[cfg(test)]
mod tests {
    // 测试集中在 src/tests.rs (crate 级, 含 fake runtime 集成)。
}
