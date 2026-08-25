"""factory-console/audit/trace_context.py — trace_id/correlation_id 上下文贯穿 (S10-120 K-4)。

一次请求从入口到执行全程同一 trace_id (审计/执行/成本可追踪):
- ContextVar (线程安全, with 块退出自动恢复 — 不跨请求泄漏)
- new_trace_id(): uuid4 hex 确定性生成
- get_trace_id() / get_correlation_id(): contextvar → str; 无上下文/异常 → ""
  (失败安全, 向后兼容 — 旧路径零变化)
- set_trace / trace_context: 设置当前上下文 (with 自动恢复)
- child_correlation(trace_id): 父子关联 — 子动作 correlation_id = f"{trace_id}:{n}"
  (n 进程内递增, 线程安全; 同一 trace 多个子动作 correlation 唯一可排序)

边界:
- 纯标准库 (contextvars/uuid/threading), 零新依赖
- 无上下文路径 → "" (不伪造不泄漏; 审计/执行/成本旧行为零变化)
- 失败安全铁律: contextvar 读取任何异常 → "" 不崩

设计: docs/sprint10/S10-120-k4-trace-plan.md §1
"""

from __future__ import annotations

import threading
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Optional

#: 当前 trace_id 上下文 (线程安全; 无上下文 → None → get 返回 "")
_trace_var: ContextVar[Optional[str]] = ContextVar("factory_trace_id", default=None)
#: 当前 correlation_id 上下文 (父子关联 — 子动作共享父 trace, 带 :n 序号)
_correlation_var: ContextVar[Optional[str]] = ContextVar(
    "factory_correlation_id", default=None
)

#: 子关联序号表 (child_correlation: trace_id → 已生成子序号; 线程安全)。
#: 有界 — 进程长期运行 (API 服务) 防无界增长: 超限清空重建 (旧 trace 已结束)。
_child_seq: dict[str, int] = {}
_child_seq_lock = threading.Lock()
_CHILD_SEQ_MAX = 4096


def new_trace_id() -> str:
    """生成新 trace_id (uuid4 hex — 确定性: 32 字符小写 hex, 无横杠)。"""
    return uuid.uuid4().hex


def get_trace_id() -> str:
    """当前上下文 trace_id; 无上下文/异常 → "" (失败安全, 不崩)。"""
    try:
        return _trace_var.get() or ""
    except Exception:  # noqa: BLE001 — 失败安全铁律
        return ""


def get_correlation_id() -> str:
    """当前上下文 correlation_id; 无上下文/异常 → "" (失败安全, 不崩)。"""
    try:
        return _correlation_var.get() or ""
    except Exception:  # noqa: BLE001 — 失败安全铁律
        return ""


def set_trace(trace_id: str, correlation_id: str = "") -> None:
    """设置当前上下文 trace/correlation (进程内立即生效)。

    注意: 不自动恢复 — 需要 with 语义用 trace_context; set_trace 适合
    无法使用 with 的既有调用路径 (入口统一用 trace_context)。
    """
    _trace_var.set(str(trace_id or ""))
    _correlation_var.set(str(correlation_id or ""))


@contextmanager
def trace_context(trace_id: str, correlation_id: str = "") -> Iterator[None]:
    """入口用上下文管理器: with 块内设置 trace/correlation, 退出自动恢复。

    - 不跨请求泄漏: with 退出 → reset 恢复调用前上下文 (嵌套/线程安全)
    - 入口 (CLI dispatch / fastapi 请求 / CLI 命令 / exec runtime) 用它包整个请求
    - 失败安全: 即使块内异常也保证恢复
    """
    trace = str(trace_id or "")
    corr = str(correlation_id or "")
    token_t = _trace_var.set(trace)
    token_c = _correlation_var.set(corr)
    try:
        yield
    finally:
        _trace_var.reset(token_t)
        _correlation_var.reset(token_c)


def child_correlation(trace_id: str) -> str:
    """父子关联: 子动作 correlation_id = f"{trace_id}:{n}"。

    n 为该 trace 已生成的子序号 +1 (进程内递增, 线程安全) — 同一 trace 的
    多个子动作 correlation 唯一且可排序 (get_chain 相关事件/父子链可寻)。
    失败安全: 异常 → f"{trace_id}:1"。
    """
    trace = str(trace_id or "")
    try:
        with _child_seq_lock:
            n = _child_seq.get(trace, 0) + 1
            _child_seq[trace] = n
            if len(_child_seq) > _CHILD_SEQ_MAX:  # 有界: 防长期运行无界增长
                _child_seq.clear()
                _child_seq[trace] = n
            return f"{trace}:{n}"
    except Exception:  # noqa: BLE001 — 失败安全
        return f"{trace}:1"
