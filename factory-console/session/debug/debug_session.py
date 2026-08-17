"""factory-console/session/debug/debug_session.py — DebugSession/DebugAttempt + DebugSessionStore (S10-068 Part 2, G1)。

统一 Pipeline 状态机: ANALYZING → ROOT_CAUSE_IDENTIFIED → STRATEGY_SELECTED →
REPAIRING → VALIDATING → RETRYING → SUCCESS / BLOCKED / WAITING_FOR_REVIEW。

设计: docs/sprint10/S10-068-part2-design.md §2
边界:
- 纯标准库 (dataclasses/json/uuid/pathlib), 零模块依赖
- DebugSessionStore 持久化 workspace/debug_sessions.json (失败安全:
  缺失/损坏 → 空列表; 落盘异常 → 静默, 不中断调试流)
- 状态机 transition 校验非法流转 (ValueError — 校验铁律); from_dict 宽松兼容
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ...memory.experience_store import DEFAULT_WORKSPACE

# ---------------------------------------------------------------- 状态常量

SESSION_ANALYZING = "ANALYZING"
SESSION_ROOT_CAUSE_IDENTIFIED = "ROOT_CAUSE_IDENTIFIED"
SESSION_STRATEGY_SELECTED = "STRATEGY_SELECTED"
SESSION_REPAIRING = "REPAIRING"
SESSION_VALIDATING = "VALIDATING"
SESSION_RETRYING = "RETRYING"
SESSION_SUCCESS = "SUCCESS"
SESSION_BLOCKED = "BLOCKED"
SESSION_WAITING_FOR_REVIEW = "WAITING_FOR_REVIEW"

#: 全部合法状态 (统计/校验口径)
SESSION_STATUSES: tuple[str, ...] = (
    SESSION_ANALYZING,
    SESSION_ROOT_CAUSE_IDENTIFIED,
    SESSION_STRATEGY_SELECTED,
    SESSION_REPAIRING,
    SESSION_VALIDATING,
    SESSION_RETRYING,
    SESSION_SUCCESS,
    SESSION_BLOCKED,
    SESSION_WAITING_FOR_REVIEW,
)

#: 终止态 (不可再流转)
_TERMINAL_STATUSES: frozenset[str] = frozenset(
    (SESSION_SUCCESS, SESSION_BLOCKED)
)

#: 合法流转表 (ANALYZING → ... → SUCCESS/BLOCKED/WAITING_FOR_REVIEW)
_TRANSITIONS: dict[str, frozenset[str]] = {
    SESSION_ANALYZING: frozenset(
        (SESSION_ROOT_CAUSE_IDENTIFIED, SESSION_STRATEGY_SELECTED, SESSION_BLOCKED)
    ),
    SESSION_ROOT_CAUSE_IDENTIFIED: frozenset(
        (SESSION_STRATEGY_SELECTED, SESSION_BLOCKED)
    ),
    SESSION_STRATEGY_SELECTED: frozenset(
        (SESSION_REPAIRING, SESSION_VALIDATING, SESSION_BLOCKED,
         SESSION_WAITING_FOR_REVIEW)
    ),
    SESSION_REPAIRING: frozenset(
        (SESSION_VALIDATING, SESSION_SUCCESS, SESSION_BLOCKED,
         SESSION_WAITING_FOR_REVIEW)
    ),
    SESSION_VALIDATING: frozenset(
        (SESSION_SUCCESS, SESSION_RETRYING, SESSION_BLOCKED)
    ),
    SESSION_RETRYING: frozenset(
        (SESSION_STRATEGY_SELECTED, SESSION_REPAIRING, SESSION_BLOCKED,
         SESSION_WAITING_FOR_REVIEW)
    ),
    SESSION_SUCCESS: frozenset(),
    SESSION_BLOCKED: frozenset(),
    SESSION_WAITING_FOR_REVIEW: frozenset(
        (SESSION_REPAIRING, SESSION_STRATEGY_SELECTED, SESSION_BLOCKED,
         SESSION_SUCCESS)
    ),
}

#: 调试会话历史文件名 (workspace 级)
DEBUG_SESSIONS_FILE = "debug_sessions.json"


def _now_iso() -> str:
    """UTC 当前时间 ISO 格式 (时间戳)。"""
    return datetime.now(timezone.utc).isoformat()


def can_transition(current: str, target: str) -> bool:
    """状态机合法性判定 (未知状态 → False; 终止态 → False)。"""
    allowed = _TRANSITIONS.get(str(current or ""))
    if allowed is None:
        return False
    return str(target or "") in allowed


# ---------------------------------------------------------------- DebugAttempt

@dataclass
class DebugAttempt:
    """一次修复尝试 (G1 — 策略执行记录, strategy_history 单元)。

    attempt_number:    第几次尝试 (从 1 起)
    strategy:          本次策略 (FixStrategy.value, 如 "FIX_CODE")
    strategy_reason:   为什么选这个策略 (adaptation 依据)
    validation_command: 验证命令 (pytest / npm test / ...)
    validation_result:  验证结果 (ValidationResult.to_dict() | {"success": bool})
    status:            "passed" / "failed" / "pending"
    timestamps:        {"started_at", "finished_at"} (UTC ISO)
    cost:              本次尝试成本 (USD)
    """

    attempt_number: int = 1
    strategy: str = ""
    strategy_reason: str = ""
    validation_command: str = ""
    validation_result: Any = None
    status: str = "pending"
    timestamps: dict[str, str] = field(default_factory=dict)
    cost: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """序列化 (strategy_history 落盘/API 响应口径)。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> "DebugAttempt":
        """反序列化 (失败安全: 非 dict → ValueError; 字段缺省兜底)。"""
        if not isinstance(data, dict):
            raise ValueError(
                f"DebugAttempt.from_dict 需要 dict, 收到 {type(data).__name__}"
            )
        try:
            number = int(data.get("attempt_number") or 1)
        except (TypeError, ValueError):
            number = 1
        try:
            cost = float(data.get("cost") or 0.0)
        except (TypeError, ValueError):
            cost = 0.0
        ts = data.get("timestamps") or {}
        return cls(
            attempt_number=number,
            strategy=str(data.get("strategy") or ""),
            strategy_reason=str(data.get("strategy_reason") or ""),
            validation_command=str(data.get("validation_command") or ""),
            validation_result=data.get("validation_result"),
            status=str(data.get("status") or "pending"),
            timestamps=dict(ts) if isinstance(ts, dict) else {},
            cost=cost,
        )


# ---------------------------------------------------------------- DebugSession

@dataclass
class DebugSession:
    """一次自主调试会话 (G1 — 统一 Pipeline 状态机载体)。

    debug_id:              会话唯一 id (uuid hex)
    project_id / task_id / agent_id: 归属 (项目/任务/Agent)
    failure_id:            失败记录 id (execution_records 关联)
    error_summary:         错误信息摘要 (主输入)
    error_type:            ErrorAnalyzer.classify 结果
    evidence:              证据链 (根因 evidence + 检索摘要)
    root_cause:            RootCause.to_dict() | RootCause 实例
    root_cause_confidence: 根因置信度 0-1
    retrieved_experiences: 检索到的历史经验 (list[dict])
    selected_strategy:     当前策略 (FixStrategy.value)
    attempt_number:        已尝试次数 (从 0 起, 每次 repair +1)
    strategy_history:      尝试记录 (list[DebugAttempt])
    validation_command / validation_result: 验证命令与结果
    status:                状态机状态 (SESSION_STATUSES)
    budget_usage:          RepairSafety 决策记录 {"decision", "reason", ...}
    timestamps:            {"created_at", "updated_at", ...}
    trace_id:              DebugTrace 关联 id (audit 追溯)
    """

    debug_id: str
    error_summary: str = ""
    project_id: str = ""
    task_id: str = ""
    agent_id: str = ""
    failure_id: str = ""
    error_type: str = ""
    evidence: list[str] = field(default_factory=list)
    root_cause: Any = None
    root_cause_confidence: float = 0.0
    retrieved_experiences: list[Any] = field(default_factory=list)
    selected_strategy: str = ""
    attempt_number: int = 0
    strategy_history: list[Any] = field(default_factory=list)
    validation_command: str = ""
    validation_result: Any = None
    status: str = SESSION_ANALYZING
    budget_usage: dict[str, Any] = field(default_factory=dict)
    timestamps: dict[str, str] = field(default_factory=dict)
    trace_id: str = ""

    # ------------------------------------------------------------ 状态机

    def transition(self, target: str) -> "DebugSession":
        """状态流转 (非法 → ValueError — 校验铁律)。"""
        if not can_transition(self.status, target):
            raise ValueError(
                f"非法状态流转: {self.status} → {target} "
                f"(合法: {sorted(_TRANSITIONS.get(self.status, ()))})"
            )
        self.status = str(target)
        ts = dict(self.timestamps or {})
        ts["updated_at"] = _now_iso()
        if target == SESSION_SUCCESS:
            ts["succeeded_at"] = _now_iso()
        if target in (SESSION_BLOCKED, SESSION_WAITING_FOR_REVIEW):
            ts[f"{target.lower()}_at"] = _now_iso()
        self.timestamps = ts
        return self

    @property
    def is_terminal(self) -> bool:
        """是否终止态 (SUCCESS/BLOCKED — 不可再流转)。"""
        return self.status in _TERMINAL_STATUSES

    # ------------------------------------------------------------ 序列化

    def to_dict(self) -> dict[str, Any]:
        """序列化 (debug_sessions.json 落盘/API 响应口径)。"""
        root = self.root_cause
        if root is not None and hasattr(root, "to_dict"):
            root = root.to_dict()
        return {
            "debug_id": self.debug_id,
            "error_summary": self.error_summary,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "failure_id": self.failure_id,
            "error_type": self.error_type,
            "evidence": list(self.evidence),
            "root_cause": root,
            "root_cause_confidence": self.root_cause_confidence,
            "retrieved_experiences": [
                r.to_dict() if hasattr(r, "to_dict") else r
                for r in self.retrieved_experiences
            ],
            "selected_strategy": self.selected_strategy,
            "attempt_number": self.attempt_number,
            "strategy_history": [
                a.to_dict() if hasattr(a, "to_dict") else a
                for a in self.strategy_history
            ],
            "validation_command": self.validation_command,
            "validation_result": self.validation_result,
            "status": self.status,
            "budget_usage": dict(self.budget_usage or {}),
            "timestamps": dict(self.timestamps or {}),
            "trace_id": self.trace_id,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "DebugSession":
        """反序列化 (失败安全: 非 dict → ValueError; 字段缺省兜底)。"""
        if not isinstance(data, dict):
            raise ValueError(
                f"DebugSession.from_dict 需要 dict, 收到 {type(data).__name__}"
            )
        status = str(data.get("status") or SESSION_ANALYZING)
        if status not in SESSION_STATUSES:
            status = SESSION_ANALYZING
        try:
            confidence = float(data.get("root_cause_confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        try:
            attempts = int(data.get("attempt_number") or 0)
        except (TypeError, ValueError):
            attempts = 0
        history = data.get("strategy_history") or []
        if not isinstance(history, (list, tuple)):
            history = []
        attempts_list: list[DebugAttempt] = []
        for item in history:
            try:
                attempts_list.append(
                    item if isinstance(item, DebugAttempt) else DebugAttempt.from_dict(item)
                )
            except ValueError:
                continue
        root = data.get("root_cause")
        from .root_cause import RootCause as _RootCause  # 本地导入避免顶层循环

        if isinstance(root, dict) and root.get("cause") is not None:
            try:
                root = _RootCause.from_dict(root)
            except ValueError:
                root = None
        exps = data.get("retrieved_experiences") or []
        if not isinstance(exps, (list, tuple)):
            exps = []
        ts = data.get("timestamps") or {}
        return cls(
            debug_id=str(data.get("debug_id") or f"dbg-{uuid.uuid4().hex[:12]}"),
            error_summary=str(data.get("error_summary") or ""),
            project_id=str(data.get("project_id") or ""),
            task_id=str(data.get("task_id") or ""),
            agent_id=str(data.get("agent_id") or ""),
            failure_id=str(data.get("failure_id") or ""),
            error_type=str(data.get("error_type") or ""),
            evidence=[str(e) for e in (data.get("evidence") or [])],
            root_cause=root,
            root_cause_confidence=max(0.0, min(1.0, confidence)),
            retrieved_experiences=list(exps),
            selected_strategy=str(data.get("selected_strategy") or ""),
            attempt_number=attempts,
            strategy_history=attempts_list,
            validation_command=str(data.get("validation_command") or ""),
            validation_result=data.get("validation_result"),
            status=status,
            budget_usage=dict(data.get("budget_usage") or {}),
            timestamps=dict(ts) if isinstance(ts, dict) else {},
            trace_id=str(data.get("trace_id") or ""),
        )


# ---------------------------------------------------------------- DebugSessionStore

def debug_sessions_file(workspace: Any = None) -> Path:
    """workspace/debug_sessions.json (缺省 → ~/.factory/debug_sessions.json)。"""
    root = Path(workspace) if workspace is not None else DEFAULT_WORKSPACE
    return root / DEBUG_SESSIONS_FILE


class DebugSessionStore:
    """调试会话持久化 (G1): create/update/get/list → debug_sessions.json。

    create(session) — 新建会话落盘 (debug_id 空 → 自动生成);
    update(session) — 按 debug_id 覆盖更新 (未知 id → 追加, 宽松);
    get(debug_id)   — 单会话 (未知 → None);
    list(limit)     — 全部会话 (最新在前);
    save()/load()   — 落盘/读取 (失败安全: 缺失/损坏 → [], 不抛)。
    """

    def __init__(self, workspace: Any = None) -> None:
        self._file: Path = debug_sessions_file(workspace)

    # ------------------------------------------------------------ 变更

    def create(self, session: Any) -> DebugSession:
        """新建会话 (debug_id 空 → 生成; 落盘; 返回会话)。"""
        item = session if isinstance(session, DebugSession) else DebugSession.from_dict(session)
        if not item.debug_id:
            item.debug_id = f"dbg-{uuid.uuid4().hex[:12]}"
        ts = dict(item.timestamps or {})
        if not ts.get("created_at"):
            ts["created_at"] = _now_iso()
            ts["updated_at"] = _now_iso()
        item.timestamps = ts
        entries = self.load()
        entries.append(item.to_dict())
        self.save(entries)
        return item

    def update(self, session: Any) -> DebugSession:
        """按 debug_id 覆盖更新 (未知 id → 追加, 宽松兼容)。"""
        item = session if isinstance(session, DebugSession) else DebugSession.from_dict(session)
        entries = self.load()
        replaced = False
        for i, entry in enumerate(entries):
            if entry.get("debug_id") == item.debug_id:
                entries[i] = item.to_dict()
                replaced = True
                break
        if not replaced:
            entries.append(item.to_dict())
        self.save(entries)
        return item

    # ------------------------------------------------------------ 查询

    def get(self, debug_id: Any) -> Optional[DebugSession]:
        """按 debug_id 读会话 (未知 → None, 失败安全)。"""
        target = str(debug_id or "")
        if not target:
            return None
        for entry in self.load():
            if str(entry.get("debug_id") or "") == target:
                try:
                    return DebugSession.from_dict(entry)
                except ValueError:
                    return None
        return None

    def list(self, limit: int = 50) -> list[DebugSession]:
        """全部会话 (最新在前; limit<=0 → 空列表)。"""
        entries = self.load()
        entries.sort(key=lambda e: e.get("timestamps", {}).get("created_at", ""), reverse=True)
        return [DebugSession.from_dict(e) for e in entries[: max(0, int(limit or 0))]]

    def count(self) -> int:
        """会话总数 (失败安全)。"""
        return len(self.load())

    # ------------------------------------------------------------ 读/写

    def save(self, entries: Any) -> None:
        """整表落盘 (失败安全: 读写异常 → 静默, 不中断调试流)。"""
        if not isinstance(entries, list):
            entries = []
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            self._file.write_text(
                json.dumps(entries, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001 — 失败安全
            pass

    def load(self) -> list[dict[str, Any]]:
        """读回全部会话 (缺失/损坏 → [], 失败安全)。"""
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — 失败安全
            return []
        if not isinstance(data, list):
            return []
        return [e for e in data if isinstance(e, dict) and e.get("debug_id")]

    def file_path(self) -> Path:
        """当前落盘文件路径 (审计/展示)。"""
        return Path(self._file)
