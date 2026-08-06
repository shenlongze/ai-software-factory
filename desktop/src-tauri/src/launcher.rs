//! launcher.rs — 产品级 UI 文案映射 (Phase 15A-3b)。
//!
//! 定位: Desktop = AI Organization Factory Application Entry。
//! 本模块只做「技术状态 → 用户语言」的纯函数映射, 禁暴露任何技术细节
//! (Python/Rust/uvicorn/subprocess/exit code 堆栈等) — 用户看到的是
//! "Factory startup failed: <原因摘要>", 而非内部错误。
//!
//! 测试: src/tests.rs (纯函数断言 + UI 资源静态断言)。

use crate::runtime::BridgeError;

/// UI 状态徽章文案 (READY/STARTING/FAILED/STOPPED/…)。
/// 未知状态 → 大写原值 (失败安全, 不 panic)。
pub fn status_label(status: &str) -> String {
    match status {
        "ready" => "READY".into(),
        "starting" => "STARTING".into(),
        "stopping" => "STOPPING".into(),
        "stopped" => "STOPPED".into(),
        "failed" => "FAILED".into(),
        "idle" => "IDLE".into(),
        other => other.to_uppercase(),
    }
}

/// 首次启动横幅。
#[allow(dead_code)] // 产品文案常量 — src/tests.rs 断言消费
pub const INITIALIZING_BANNER: &str = "Initializing Factory…";

/// 首次启动失败主标题 (用户语言)。
#[allow(dead_code)] // 产品文案常量 — src/tests.rs 断言消费
pub const STARTUP_FAILED_TITLE: &str = "Factory startup failed";

/// 错误 → 用户语言摘要 (禁 Python/Rust/uvicorn/subprocess/路径等细节)。
pub fn friendly_error(err: &BridgeError) -> String {
    match err {
        BridgeError::SpawnFailed(_) => {
            "Factory startup failed: 工厂运行时未安装或无法启动。请重新安装后重试。".into()
        }
        BridgeError::Exit { .. } => {
            "Factory startup failed: 工厂服务启动时发生错误。请重试; 若持续失败, 请使用「系统恢复」重启。"
                .into()
        }
        BridgeError::Timeout(_) => {
            "Factory startup failed: 工厂服务启动超时。请重试。".into()
        }
        BridgeError::Parse(_) => {
            "Factory startup failed: 工厂服务返回了无法识别的信息。请重试。".into()
        }
        BridgeError::DataRoot(_) => {
            "Factory startup failed: 数据目录不可用或不可写。请检查磁盘权限后重试。".into()
        }
        BridgeError::Health(_) => {
            "Factory startup failed: 工厂服务已启动, 但控制台暂未就绪。请重试。".into()
        }
        BridgeError::RuntimeFailed(_) => {
            "Factory startup failed: 工厂服务运行异常。请使用「系统恢复」重启工厂。".into()
        }
    }
}

/// 恢复操作完成文案 (重启成功/失败)。
#[allow(dead_code)] // 产品文案 — src/tests.rs 断言消费
pub fn recovery_result(ok: bool) -> String {
    if ok {
        "恢复完成: 工厂服务已重新就绪。".into()
    } else {
        "恢复失败: 未能重启工厂服务。请重试或检查数据目录。".into()
    }
}
