"""factory-console/session/conflicts.py — FileOwnership + ConflictDetector + ConflictResolver (S10-056/S10-057)。

文件冲突检测 (设计 §2.7): FileOwnership 记录 task → files 归属;
ConflictDetector 检测同文件多任务修改 → ConflictRecord (status "open" 保留,
只检测不解决 — 边界 §7), 落盘 conflicts.json (~/.factory/teams/)。

S10-057 (Team Production Validation): ConflictResolver — 冲突解决策略
(dependency_delay / task_reorder / serial_execution), 输出 resolutions +
ordered_tasks (重排) + serial_groups (同文件串行), 落盘 conflict_resolution.json
(projects/<slug>/)。只策略解决 (排序/串行), 暂不自动 merge (设计 §P0)。

组件:
- FileOwnership — claim(project_dir, task_id, files) / owned_by(file) / clear()
- ConflictRecord — {task_a, task_b, file, detected_at, status: "open"}
- ConflictDetector — detect(project_dir, task_id, files) → list[ConflictRecord]
  (同文件已被其他 task claim → 冲突记录, 去重; 未归属文件 → 顺带 claim) /
  list() / save() / load() (失败安全: 缺失/损坏 → 空记录)
- ConflictResolver — resolve(conflicts, plan_tasks, strategy?) → {strategy,
  resolutions, ordered_tasks, serial_groups} / detect_and_resolve(plan_tasks) /
  save() / load() (失败安全) — 同文件冲突 → 策略 (依赖延迟/重排/串行) 落盘
  conflict_resolution.json

设计: docs/sprint10/S10-056-team-design.md §2.7 / §4;
docs/sprint10/S10-057-team-production-design.md §P0
边界:
- 纯标准库 (json/pathlib/dataclasses), 零模块依赖; 失败安全, 永不抛
- 只检测不解决: 冲突记录 status 恒为 "open", 不做自动 merge/解决
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

#: 默认冲突文件 (~/.factory/teams/conflicts.json — 设计 §4 资产口径)
DEFAULT_CONFLICTS_FILE = Path.home() / ".factory" / "teams" / "conflicts.json"

#: 默认冲突解决文件 (~/.factory/teams/conflict_resolution.json — 设计 §4 资产口径;
#: 项目级解决记录 → projects/<slug>/conflict_resolution.json, 由调用方显式指定)
DEFAULT_RESOLUTION_FILE = Path.home() / ".factory" / "teams" / "conflict_resolution.json"

#: 冲突状态常量 (只检测不解决 — status 恒为 open)
CONFLICT_STATUS_OPEN = "open"

#: 冲突解决策略常量 (S10-057 设计 §P0):
#: dependency_delay — 冲突任务延迟到依赖 (先归属者) 之后
#: task_reorder     — 重排: 冲突任务重新排序 (先归属者在前)
#: serial_execution — 同文件串行: 同文件任务分组按计划顺序串行执行
STRATEGY_DEPENDENCY_DELAY = "dependency_delay"
STRATEGY_TASK_REORDER = "task_reorder"
STRATEGY_SERIAL_EXECUTION = "serial_execution"

#: 全部合法策略 (未知策略 → 失败安全回退 dependency_delay)
CONFLICT_STRATEGIES: tuple[str, ...] = (
    STRATEGY_DEPENDENCY_DELAY,
    STRATEGY_TASK_REORDER,
    STRATEGY_SERIAL_EXECUTION,
)

#: 缺省解决策略 (设计 §P0 首选: 依赖延迟)
DEFAULT_RESOLVE_STRATEGY = STRATEGY_DEPENDENCY_DELAY

#: 执行决策常量 (S10-059 P3 — Conflict → Execution Decision, 设计 §7 P3):
#: NO_CONFLICT          — 无冲突, 可顺序执行
#: SERIALIZE            — 同文件冲突 → 串行化 (先归属者先执行, 后执行者等待)
#: RETRY_WITH_CONTEXT   — 无文件冲突但上下文缺失 → 携带最新上下文重试
#: REQUEST_REVIEW       — 需人工评审 (冲突无法自动解决)
DECISION_NO_CONFLICT = "NO_CONFLICT"
DECISION_SERIALIZE = "SERIALIZE"
DECISION_RETRY_WITH_CONTEXT = "RETRY_WITH_CONTEXT"
DECISION_REQUEST_REVIEW = "REQUEST_REVIEW"

#: 全部合法执行决策 (未知 → 失败安全回退 NO_CONFLICT)
EXECUTION_DECISIONS: tuple[str, ...] = (
    DECISION_NO_CONFLICT,
    DECISION_SERIALIZE,
    DECISION_RETRY_WITH_CONTEXT,
    DECISION_REQUEST_REVIEW,
)


def _now_iso() -> str:
    """UTC 当前时间 ISO 格式 (冲突检测时间戳)。"""
    return datetime.now(timezone.utc).isoformat()


class FileOwnership:
    """task → files 归属记录 (按项目隔离: {project: {file: task_id}})。

    claim(project_dir, task_id, files): 记录归属 (文件归一化为项目相对路径,
    非项目内路径保留原样; 同文件新 task → 覆盖, 记录最新归属)。
    owned_by(file): 查询文件归属 task (跨项目精确匹配 → 文件名兜底);
    未归属 → None。clear(): 清空全部归属。
    """

    def __init__(self, data: Optional[dict[str, Any]] = None) -> None:
        self._ownership: dict[str, dict[str, str]] = {}
        if isinstance(data, dict):
            for project, store in data.items():
                if isinstance(store, dict):
                    self._ownership[str(project)] = {
                        str(k): str(v) for k, v in store.items()
                    }

    @staticmethod
    def _norm(project_dir: Any, file: Any) -> str:
        """文件归一化: 项目内 → 相对路径; 其他 → 原样字符串。"""
        try:
            return str(Path(file).resolve().relative_to(Path(project_dir).resolve()))
        except (ValueError, OSError):  # noqa: BLE001 — 非项目内路径 → 原样
            return str(file)

    def claim(self, project_dir: Any, task_id: str, files: list[str]) -> None:
        """记录 task → files 归属 (文件级幂等覆盖; 缺省 files → 无操作)。"""
        if not files:
            return
        project = str(project_dir)
        store = self._ownership.setdefault(project, {})
        for file in files:
            store[self._norm(project_dir, file)] = str(task_id)

    def owned_by(self, file: Any) -> Optional[str]:
        """文件归属 task_id; 未归属 → None (跨项目精确 → 文件名兜底)。"""
        key = str(file)
        for store in self._ownership.values():
            if key in store:
                return store[key]
        base = Path(key).name
        for store in self._ownership.values():
            if base in store:
                return store[base]
        return None

    def clear(self) -> None:
        """清空全部归属记录。"""
        self._ownership.clear()

    def to_dict(self) -> dict[str, dict[str, str]]:
        """归属快照 (拷贝, 不泄漏内部)。"""
        return {p: dict(s) for p, s in self._ownership.items()}


@dataclass
class ConflictRecord:
    """冲突记录 (设计 §2.7): task_a (先归属者) vs task_b (后检测者) 同文件。

    status 恒为 "open" — 只检测不解决 (边界 §7)。
    """

    task_a: str
    task_b: str
    file: str
    detected_at: str = field(default_factory=_now_iso)
    status: str = CONFLICT_STATUS_OPEN

    def to_dict(self) -> dict[str, Any]:
        """落盘格式: {task_a, task_b, file, detected_at, status} (设计 §2.7)。"""
        return {
            "task_a": self.task_a,
            "task_b": self.task_b,
            "file": self.file,
            "detected_at": self.detected_at,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "ConflictRecord":
        """读回格式 → ConflictRecord; 缺字段失败安全缺省 (status 缺省 open)。"""
        data = data if isinstance(data, dict) else {}
        return cls(
            task_a=str(data.get("task_a") or ""),
            task_b=str(data.get("task_b") or ""),
            file=str(data.get("file") or ""),
            detected_at=str(data.get("detected_at") or _now_iso()),
            status=str(data.get("status") or CONFLICT_STATUS_OPEN),
        )


class ConflictDetector:
    """冲突检测器 (设计 §2.7): 同文件多任务 → ConflictRecord (open, 不解决)。

    detect(project_dir, task_id, files): 对每个文件 — 已被其他 task 归属 →
    冲突记录 (去重: 同 task_a/task_b/file 不重复记录); 未归属 → 顺带 claim
    (当前 task 取得归属)。新冲突自动落盘。只检测不解决 (status 恒 open)。
    """

    DEFAULT_FILE = DEFAULT_CONFLICTS_FILE

    def __init__(
        self,
        conflicts_file: Optional[Path] = None,
        ownership: Optional[FileOwnership] = None,
    ) -> None:
        self._file = (
            Path(conflicts_file) if conflicts_file is not None else self.DEFAULT_FILE
        )
        self._ownership = ownership if ownership is not None else FileOwnership()
        self._records: list[ConflictRecord] = []
        self._load()

    # ------------------------------------------------------------ 检测

    def detect(
        self, project_dir: Any, task_id: str, files: list[str]
    ) -> list[ConflictRecord]:
        """检测文件冲突 (同文件已被其他 task claim → 记录; 未归属 → claim)。"""
        new_records: list[ConflictRecord] = []
        for file in files or []:
            owner = self._ownership.owned_by(file)
            if owner is None:
                self._ownership.claim(project_dir, task_id, [file])
            elif owner != str(task_id):
                record = ConflictRecord(
                    task_a=owner, task_b=str(task_id), file=str(file)
                )
                if not self._contains(record):
                    self._records.append(record)
                    new_records.append(record)
        if new_records:
            self._save()
        return new_records

    def _contains(self, record: ConflictRecord) -> bool:
        """同 (task_a/task_b/file) 记录是否已存在 (去重)。"""
        return any(
            r.task_a == record.task_a
            and r.task_b == record.task_b
            and r.file == record.file
            for r in self._records
        )

    # ------------------------------------------------------------ 查询/落盘

    def list(self) -> list[dict[str, Any]]:
        """全部冲突记录 (检测顺序)。"""
        return [r.to_dict() for r in self._records]

    def _load(self) -> None:
        data: Any = None
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — 失败安全: 缺失/损坏 → 空记录
            data = None
        if isinstance(data, list):
            self._records = [
                ConflictRecord.from_dict(r) for r in data if isinstance(r, dict)
            ]
        else:
            self._records = []

    def load(self, file: Optional[Path] = None) -> "ConflictDetector":
        """(重)加载冲突记录 (缺省当前文件); 返回 self 支持链式。"""
        if file is not None:
            self._file = Path(file)
        self._load()
        return self

    def _save(self) -> Path:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(
            json.dumps(
                [r.to_dict() for r in self._records], ensure_ascii=False, indent=2
            )
            + "\n",
            encoding="utf-8",
        )
        return self._file

    def save(self, file: Optional[Path] = None) -> Path:
        """落盘 conflicts.json (可指定文件); 返回文件路径。"""
        if file is not None:
            self._file = Path(file)
        return self._save()


class ConflictResolver:
    """冲突解决器 (S10-057 设计 §P0 + S10-059 P3): 同文件冲突 → 策略解决 +
    执行决策, 落盘 conflict_resolution.json。

    resolve(conflicts, plan_tasks, strategy?): 冲突列表 (ConflictRecord.to_dict
    兼容: {task_a, task_b, file}) + 计划任务 (含 id) → {strategy, resolutions:
    [{file, task_a, task_b, strategy}], ordered_tasks: [重排后的 task ids],
    serial_groups: [同文件串行分组]} + S10-059 执行决策 (decision/reason/
    conflicting_tasks — 供 orchestrator 消费, 向后兼容: 旧字段原样保留)。
    三种策略 (设计 §P0):

    - dependency_delay — 冲突任务 (task_b) 延迟到先归属者 (task_a) 之后
      (稳定拓扑: 加 a→b 边, 其余顺序保持)
    - task_reorder     — 重排: 同样保证 a 在 b 前 (记录策略为 reorder)
    - serial_execution — 同文件串行: 保证 a 在 b 前 + serial_groups 分组
      (同文件任务按计划顺序串行)

    classify(conflicts, *, review_required, missing_context) → 执行决策:
    NO_CONFLICT / SERIALIZE / RETRY_WITH_CONTEXT / REQUEST_REVIEW (设计 §7 P3)。

    detect_and_resolve(plan_tasks): 计划级冲突预检测 (FileOwnership 模拟归属,
    不落盘 conflicts.json) → resolve。strategy 可为全局字符串或
    {file: strategy} 按文件覆盖 (未知策略 → 回退 dependency_delay, 失败安全)。
    save()/load(): conflict_resolution.json 落盘/读取 (缺失/损坏 → 空, 失败安全)。
    """

    DEFAULT_FILE = DEFAULT_RESOLUTION_FILE

    STRATEGY_DEPENDENCY_DELAY = STRATEGY_DEPENDENCY_DELAY
    STRATEGY_TASK_REORDER = STRATEGY_TASK_REORDER
    STRATEGY_SERIAL_EXECUTION = STRATEGY_SERIAL_EXECUTION
    STRATEGIES = CONFLICT_STRATEGIES
    DEFAULT_STRATEGY = DEFAULT_RESOLVE_STRATEGY

    #: S10-059 P3: 执行决策常量 (供调用方引用)
    DECISION_NO_CONFLICT = DECISION_NO_CONFLICT
    DECISION_SERIALIZE = DECISION_SERIALIZE
    DECISION_RETRY_WITH_CONTEXT = DECISION_RETRY_WITH_CONTEXT
    DECISION_REQUEST_REVIEW = DECISION_REQUEST_REVIEW
    DECISIONS = EXECUTION_DECISIONS

    def __init__(self, resolution_file: Optional[Path] = None) -> None:
        self._file = (
            Path(resolution_file) if resolution_file is not None else self.DEFAULT_FILE
        )
        self._resolutions: list[dict[str, Any]] = []
        self._ordered_tasks: list[str] = []
        self._serial_groups: list[list[str]] = []
        self._strategy: str = DEFAULT_RESOLVE_STRATEGY
        # S10-059 P3: 执行决策 (decision/reason/conflicting_tasks)
        self._decision: str = DECISION_NO_CONFLICT
        self._decision_reason: str = ""
        self._conflicting_tasks: list[str] = []
        self._load()

    # ------------------------------------------------------------ 分类/解决

    @staticmethod
    def classify(
        conflicts: list[dict[str, Any]],
        *,
        review_required: bool = False,
        missing_context: bool = False,
    ) -> str:
        """冲突 → 执行决策分类 (S10-059 P3, 设计 §7 P3)。

        优先级: 同文件冲突 → SERIALIZE (最高, 物理写权限互斥); 无冲突且
        review_required → REQUEST_REVIEW (人工评审优先于自动重试); 无冲突且
        missing_context → RETRY_WITH_CONTEXT (携带最新上下文重试); 其余 →
        NO_CONFLICT。未知输入失败安全 → NO_CONFLICT。
        """
        if conflicts:
            return DECISION_SERIALIZE
        if review_required:
            return DECISION_REQUEST_REVIEW
        if missing_context:
            return DECISION_RETRY_WITH_CONTEXT
        return DECISION_NO_CONFLICT

    @staticmethod
    def _normalize_strategy(strategy: Any, default: str = DEFAULT_RESOLVE_STRATEGY) -> str:
        """策略归一化: 合法策略 → 原样; 未知/空 → 缺省 (失败安全)。"""
        if isinstance(strategy, str) and strategy in CONFLICT_STRATEGIES:
            return strategy
        return default

    @staticmethod
    def _conflict_fields(conflict: Any) -> tuple[str, str, str]:
        """冲突 dict → (file, task_a, task_b); 缺字段失败安全缺省空串。"""
        if not isinstance(conflict, dict):
            return ("", "", "")
        return (
            str(conflict.get("file") or ""),
            str(conflict.get("task_a") or ""),
            str(conflict.get("task_b") or ""),
        )

    def _dedupe(self, conflicts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """同 (file/task_a/task_b) 冲突去重 (保留首现)。"""
        seen: set[tuple[str, str, str]] = set()
        out: list[dict[str, Any]] = []
        for c in conflicts:
            key = self._conflict_fields(c)
            if not any(key):  # 空冲突 (缺全部字段) → 跳过
                continue
            if key in seen:
                continue
            seen.add(key)
            out.append(c)
        return out

    @staticmethod
    def _stable_order(ids: list[str], edges: list[tuple[str, str]]) -> list[str]:
        """稳定拓扑排序 (Kahn): edges (a→b: a 先于 b); 稳定 — 无冲突任务保持
        原始相对顺序 (新入队节点按原始计划位置稳定插入); 环 → 剩余按原顺序追加。"""
        order = [t for t in ids if t]
        if not order:
            return []
        node_set = set(order)
        pos = {t: i for i, t in enumerate(order)}
        indegree = {t: 0 for t in order}
        dependents: dict[str, list[str]] = {t: [] for t in order}
        for a, b in edges:
            if a in node_set and b in node_set and a != b:
                dependents[a].append(b)
                indegree[b] += 1
        queue = [t for t in order if indegree[t] == 0]
        result: list[str] = []
        while queue:
            node = queue.pop(0)
            result.append(node)
            for nxt in dependents[node]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    # 稳定插入: 按原始计划位置入队 (保持无冲突任务相对顺序)
                    idx = 0
                    while idx < len(queue) and pos[queue[idx]] < pos[nxt]:
                        idx += 1
                    queue.insert(idx, nxt)
        for t in order:
            if t not in result:
                result.append(t)
        return result

    def _strategy_for(
        self, strategy: Any, file: str, default: str = DEFAULT_RESOLVE_STRATEGY
    ) -> str:
        """按文件取策略: strategy 为 dict → 文件覆盖; 字符串 → 全局; None → 缺省。"""
        if isinstance(strategy, dict):
            return self._normalize_strategy(strategy.get(file), default)
        return self._normalize_strategy(strategy, default)

    def resolve(
        self,
        conflicts: list[dict[str, Any]],
        plan_tasks: list[dict[str, Any]],
        strategy: Any = None,
    ) -> dict[str, Any]:
        """解决冲突 (设计 §P0 + S10-059 P3): 输出策略/重排/串行分组 + 执行决策,
        落盘 conflict_resolution.json。

        conflicts: 冲突记录列表 (ConflictRecord.to_dict / {task_a, task_b, file});
        plan_tasks: 计划任务 (含 id); strategy: None (缺省 dependency_delay) |
        全局策略字符串 | {file: strategy} 按文件覆盖。
        返回 {strategy, resolutions: [{file, task_a, task_b, strategy}],
        ordered_tasks: [重排后 task ids], serial_groups: [同文件串行分组],
        decision: NO_CONFLICT/SERIALIZE (执行决策), reason: 可解释原因,
        conflicting_tasks: [冲突任务 ids]} — 旧字段原样保留 (向后兼容)。
        """
        deduped = self._dedupe(list(conflicts or []))
        ids = [str(t.get("id") or "") for t in (plan_tasks or [])]
        ids = [tid for tid in ids if tid]
        node_set = set(ids)
        default_strategy = self._normalize_strategy(
            strategy if isinstance(strategy, str) else None,
            DEFAULT_RESOLVE_STRATEGY,
        )
        resolutions: list[dict[str, Any]] = []
        edges: list[tuple[str, str]] = []
        seen_edges: set[tuple[str, str]] = set()
        by_file: dict[str, set[str]] = {}
        for conflict in deduped:
            file, task_a, task_b = self._conflict_fields(conflict)
            if not file and not task_a and not task_b:
                continue
            strat = self._strategy_for(strategy, file, default_strategy)
            resolutions.append(
                {"file": file, "task_a": task_a, "task_b": task_b, "strategy": strat}
            )
            if task_a in node_set and task_b in node_set and task_a != task_b:
                if (task_a, task_b) not in seen_edges:
                    seen_edges.add((task_a, task_b))
                    edges.append((task_a, task_b))
            if file:
                by_file.setdefault(file, set()).update(
                    t for t in (task_a, task_b) if t in node_set
                )
        ordered_tasks = self._stable_order(ids, edges)
        serial_groups: list[list[str]] = []
        for file in sorted(by_file):
            group = [tid for tid in ordered_tasks if tid in by_file[file]]
            if len(group) > 1:
                serial_groups.append(group)
        # ---- S10-059 P3: 执行决策 (decision/reason/conflicting_tasks — 可解释)
        conflicting_tasks: list[str] = []
        if resolutions:
            first = resolutions[0]
            for r in resolutions:
                for side in ("task_a", "task_b"):
                    tid = str(r.get(side) or "")
                    if tid and tid not in conflicting_tasks:
                        conflicting_tasks.append(tid)
            decision = DECISION_SERIALIZE
            reason = (
                f"{first.get('task_a')} and {first.get('task_b')} both require "
                f"write access to {first.get('file')}"
            )
        else:
            decision = DECISION_NO_CONFLICT
            reason = f"无冲突: {len(ids)} 任务可顺序执行"
        payload = {
            "strategy": default_strategy,
            "resolutions": resolutions,
            "ordered_tasks": ordered_tasks,
            "serial_groups": serial_groups,
            "decision": decision,
            "reason": reason,
            "conflicting_tasks": conflicting_tasks,
        }
        self._resolutions = resolutions
        self._ordered_tasks = ordered_tasks
        self._serial_groups = serial_groups
        self._strategy = default_strategy
        self._decision = decision
        self._decision_reason = reason
        self._conflicting_tasks = conflicting_tasks
        self._save()
        return payload

    def detect_and_resolve(
        self, plan_tasks: list[dict[str, Any]], strategy: Any = None
    ) -> dict[str, Any]:
        """计划级冲突预检测 + 解决 (不写 conflicts.json — 归属仅内存模拟)。

        按计划顺序模拟 FileOwnership claim: 同文件已被其他任务归属 → 冲突
        {file, task_a, task_b} → resolve (策略解决 + 落盘 conflict_resolution.json)。
        """
        ownership = FileOwnership()
        conflicts: list[dict[str, Any]] = []
        for task in plan_tasks or []:
            task_id = str(task.get("id") or "")
            if not task_id:
                continue
            for file in [
                str(f) for f in (task.get("files") or []) if not isinstance(f, dict)
            ]:
                owner = ownership.owned_by(file)
                if owner is None:
                    ownership.claim(Path("."), task_id, [file])
                elif owner != task_id:
                    conflicts.append({"file": file, "task_a": owner, "task_b": task_id})
        return self.resolve(conflicts, plan_tasks, strategy=strategy)

    # ------------------------------------------------------------ 查询/落盘

    def list(self) -> list[dict[str, Any]]:
        """本次/最近一次解决记录 (resolutions 列表, 拷贝)。"""
        return [dict(r) for r in self._resolutions]

    def ordered_tasks(self) -> list[str]:
        """重排后的任务顺序 (最近一次解决)。"""
        return list(self._ordered_tasks)

    def serial_groups(self) -> list[list[str]]:
        """同文件串行分组 (最近一次解决)。"""
        return [list(g) for g in self._serial_groups]

    def execution_decision(self) -> dict[str, Any]:
        """最近一次执行决策 (S10-059 P3): {decision, reason, conflicting_tasks}。"""
        return {
            "decision": self._decision,
            "reason": self._decision_reason,
            "conflicting_tasks": list(self._conflicting_tasks),
        }

    def _load(self) -> None:
        data: Any = None
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — 失败安全: 缺失/损坏 → 空解决
            data = None
        if isinstance(data, dict):
            self._strategy = self._normalize_strategy(
                data.get("strategy"), DEFAULT_RESOLVE_STRATEGY
            )
            self._resolutions = [
                dict(r)
                for r in (data.get("resolutions") or [])
                if isinstance(r, dict)
            ]
            self._ordered_tasks = [
                str(t) for t in (data.get("ordered_tasks") or []) if not isinstance(t, dict)
            ]
            self._serial_groups = [
                [str(t) for t in (g or []) if not isinstance(t, dict)]
                for g in (data.get("serial_groups") or [])
                if isinstance(g, list)
            ]
            # S10-059 P3: 执行决策字段 (旧文件无 → 失败安全缺省)
            decision = str(data.get("decision") or "")
            self._decision = (
                decision if decision in EXECUTION_DECISIONS else DECISION_NO_CONFLICT
            )
            self._decision_reason = str(data.get("reason") or "")
            self._conflicting_tasks = [
                str(t)
                for t in (data.get("conflicting_tasks") or [])
                if not isinstance(t, dict)
            ]
        else:
            self._strategy = DEFAULT_RESOLVE_STRATEGY
            self._resolutions = []
            self._ordered_tasks = []
            self._serial_groups = []
            self._decision = DECISION_NO_CONFLICT
            self._decision_reason = ""
            self._conflicting_tasks = []

    def load(self, file: Optional[Path] = None) -> "ConflictResolver":
        """(重)加载 conflict_resolution.json (缺省当前文件); 返回 self 链式。"""
        if file is not None:
            self._file = Path(file)
        self._load()
        return self

    def _save(self) -> Path:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(
            json.dumps(
                {
                    "strategy": self._strategy,
                    "resolutions": self._resolutions,
                    "ordered_tasks": self._ordered_tasks,
                    "serial_groups": self._serial_groups,
                    "decision": self._decision,
                    "reason": self._decision_reason,
                    "conflicting_tasks": self._conflicting_tasks,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return self._file

    def save(self, file: Optional[Path] = None) -> Path:
        """落盘 conflict_resolution.json (可指定文件); 返回文件路径。"""
        if file is not None:
            self._file = Path(file)
        return self._save()
