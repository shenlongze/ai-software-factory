"""factory-console/session/execution_replay.py — M5-1 执行重放引擎 (S10-113)。

设计: docs/sprint10/S10-113-execution-replay-plan.md §1
规格: M5-1 (§5.6.3 L3/L4) — dry-run 时间线重建 / re-exec 同输入重跑 /
      对比报告 (真实 diff) / L4 快照回滚 (可选)。

组件:
- ReplayEngine — 重放引擎:
  - dry_run(exec_id) -> ReplayTimeline: 读 execution_records + audit 事件,
    按 timestamp 合并重建单次执行 (步骤/agent/任务/结果/耗时 = 相邻时间戳差);
    无效 id → ReplayError 明确错误 (不瞎跑)。
  - re_exec(exec_id, runner) -> str: 从 input_snapshot 还原输入 → runner 重跑
    → 新 exec_id 记录 (含 snapshot, 可对比); input_snapshot 缺失 (旧记录)
    → ReplayError 明确错误, 不瞎跑。
  - compare(exec_id1, exec_id2, save_to=None) -> str: 两次执行真实 diff
    (步骤/结果/耗时/产物); save_to → 写 docs/sprint10/replay-compare-<id1>-<id2>.md。
  - snapshot_before / rollback (L4, 受限): 项目目录 git 快照 (stash create 基线)
    → reset --hard 回滚; 非 git 仓库/无项目目录 → ReplayError 明确。
    说明: 复用 sandbox 同一 git 快照机制 (add/diff/apply 家族), 但 sandbox
    本体操作副本 (create 拷贝 + 独立基线), 对"执行前状态回滚"语义需在
    项目仓库内直接取基线, 故用 git stash create (不修改工作区/索引,
    不落 stash ref) — 与 sandbox 的 git 机械同源, 语义如实注释。

边界:
- 只读重建 + 追加式记录, 不复制/不执行业务 (重跑由调用方 runner 注入);
- 纯标准库 (json/os/subprocess/datetime/difflib/pathlib), 零新依赖;
- 失败安全铁律: 记录/审计文件缺失或损坏 → 对应空数据, 但无效 exec_id /
  缺 input_snapshot → ReplayError 响亮报错 (诚实纪律, 不 stub/fake)。
"""

from __future__ import annotations

import difflib
import json
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from .audit import load_records

#: 审计事件类型子集 — 与单次执行相关的步骤事件 (细化时间线; 其余事件不属执行)
REPLAY_EVENT_TYPES: frozenset[str] = frozenset({
    "TASK_STARTED", "TASK_COMPLETED", "TASK_FAILED", "TASK_REPAIRED",
    "EXECUTION_STARTED", "EXECUTION_COMPLETED", "EXECUTION_FAILED",
    "EXECUTION_TASK_STARTED", "EXECUTION_TASK_COMPLETED", "EXECUTION_ROUND_COMPLETED",
    "ARTIFACT_CREATED", "TEST_PASSED", "TEST_FAILED", "EVIDENCE_CREATED",
    "PATCH_APPLIED", "CODE_VALIDATED", "DELIVERY_COMPLETED", "DELIVERY_FAILED",
})

#: 审计事件类型 → 中文标签 (时间线展示; 未知 → 原类型)
EVENT_LABELS: dict[str, str] = {
    "TASK_STARTED": "任务开始",
    "TASK_COMPLETED": "任务完成",
    "TASK_FAILED": "任务失败",
    "TASK_REPAIRED": "任务修复",
    "EXECUTION_STARTED": "执行开始",
    "EXECUTION_COMPLETED": "执行完成",
    "EXECUTION_FAILED": "执行失败",
    "EXECUTION_TASK_STARTED": "执行任务开始",
    "EXECUTION_TASK_COMPLETED": "执行任务完成",
    "EXECUTION_ROUND_COMPLETED": "执行轮完成",
    "ARTIFACT_CREATED": "产物生成",
    "TEST_PASSED": "测试通过",
    "TEST_FAILED": "测试失败",
    "EVIDENCE_CREATED": "证据生成",
    "PATCH_APPLIED": "补丁应用",
    "CODE_VALIDATED": "代码验证",
    "DELIVERY_COMPLETED": "交付完成",
    "DELIVERY_FAILED": "交付失败",
}

#: 默认审计事件匹配窗口 (秒) — agent 相同 + 时间窗内的事件视为该次执行的步骤
DEFAULT_EVENT_WINDOW_SECONDS = 600.0

#: 对比报告默认文件名模板 (docs/sprint10/replay-compare-<id1>-<id2>.md)
COMPARE_REPORT_NAME = "replay-compare-{id1}-{id2}.md"


class ReplayError(Exception):
    """重放错误 (无效 exec_id / 缺 input_snapshot / 缺对比记录 / L4 快照不可用)。

    明确错误, 不静默、不瞎跑 — 调用方 (action/command) 捕获后直接展示。
    """


def _parse_ts(value: Any) -> Optional[datetime]:
    """时间戳字符串 → datetime (ISO 8601; 解析失败 → None, 失败安全)。"""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):  # noqa: BLE001 — 失败安全
        return None


def _fmt_duration(seconds: float) -> str:
    """秒数 → 可读耗时 (0.0 → "0.0s"; 分钟/小时分级)。"""
    seconds = max(0.0, float(seconds or 0.0))
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{int(minutes)}m{seconds % 60:.0f}s"
    hours = int(minutes // 60)
    return f"{hours}h{int(minutes % 60)}m"


@dataclass
class ReplayStep:
    """时间线步骤 (记录或审计事件, 按 timestamp 排序; duration = 与上一步时间差)。"""

    timestamp: str
    kind: str            # "record" | "audit"
    event_type: str      # 原始事件类型 ("record" 表示执行记录本身)
    label: str           # 显示名 (中文/原类型)
    agent: str
    result: str
    detail: str = ""
    duration: float = 0.0  # 与上一步耗时 (秒, 真实计算)

    def line(self) -> str:
        """对比/展示用单行 (真实内容, 非占位)。"""
        return f"{self.event_type} | {self.label} | {self.agent or '-'} | {self.result or '-'} | {self.detail or '-'}"


@dataclass
class ReplayTimeline:
    """单次执行重建时间线 (dry_run 结果)。"""

    exec_id: str
    record: dict[str, Any]
    steps: list[ReplayStep] = field(default_factory=list)

    @property
    def task(self) -> str:
        return str(self.record.get("task") or "")

    @property
    def agent(self) -> str:
        return str(self.record.get("agent") or "")

    @property
    def result(self) -> str:
        return str(self.record.get("result") or "")

    @property
    def intent(self) -> str:
        return str(self.record.get("intent") or "")

    @property
    def total_duration(self) -> float:
        """总耗时 = 末步时间戳 - 首步时间戳 (真实计算; 单步 → 0.0)。"""
        if len(self.steps) < 2:
            return 0.0
        first = _parse_ts(self.steps[0].timestamp)
        last = _parse_ts(self.steps[-1].timestamp)
        if first is None or last is None:
            return 0.0
        return max(0.0, (last - first).total_seconds())

    def to_markdown(self) -> str:
        """时间线 markdown (步骤/agent/任务/结果/耗时, 可读)。"""
        lines = [
            f"# 执行重放时间线: {self.exec_id}",
            "",
            f"- 任务: {self.task or '—'}",
            f"- Agent: {self.agent or '—'}",
            f"- 意图: {self.intent or '—'}",
            f"- 结果: {self.result or '—'}",
            f"- 步骤: {len(self.steps)} · 总耗时: {_fmt_duration(self.total_duration)}",
            "",
            "## 步骤",
            "",
            "| 时间 | 类型 | 步骤 | Agent | 结果 | 耗时 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for step in self.steps:
            lines.append(
                f"| {step.timestamp} | {step.kind} | {step.label} | "
                f"{step.agent or '—'} | {step.result or '—'} | "
                f"{_fmt_duration(step.duration)} |"
            )
        return "\n".join(lines)


class ReplayEngine:
    """执行重放引擎 (M5-1): dry-run / re-exec / compare + L4 快照回滚 (受限)。"""

    def __init__(
        self,
        workspace: Path,
        records_file: Optional[Path] = None,
        event_window_seconds: float = DEFAULT_EVENT_WINDOW_SECONDS,
    ) -> None:
        """workspace: 数据工作区 (默认 ~/.factory); records_file 可注入 (测试隔离)。

        records_file 缺省 → workspace/exec/execution_records.json (同 actions 口径)。
        """
        self.workspace = Path(workspace)
        self.records_file = (
            Path(records_file)
            if records_file is not None
            else self.workspace / "exec" / "execution_records.json"
        )
        self.event_window_seconds = float(event_window_seconds)

    # ------------------------------------------------------------ 1. dry-run

    def dry_run(self, exec_id: str) -> ReplayTimeline:
        """读 records + audit 事件 → 按时间线重建单次执行 (真实重建, 非 stub)。

        无效 id → ReplayError("执行记录不存在: {id}")。
        时间线: 记录本身 + 关联审计事件 (TASK_*/EXECUTION_*/ARTIFACT_CREATED 等)
        按 timestamp 合并排序; 耗时 = 相邻时间戳差 (真实计算)。
        """
        record = self._require_record(exec_id)
        steps: list[ReplayStep] = [self._record_step(record)]
        for event in self._matching_audit_events(record):
            steps.append(self._audit_step(event))
        steps.sort(key=lambda s: _parse_ts(s.timestamp) or datetime.min)
        self._fill_durations(steps)
        return ReplayTimeline(exec_id=exec_id, record=record, steps=steps)

    # ------------------------------------------------------------ 2. re-exec

    def re_exec(self, exec_id: str, runner: Callable[[dict[str, Any]], dict[str, Any]]) -> str:
        """从 input_snapshot 还原输入 → runner 同输入重跑 → 新 exec_id 记录。

        - runner(snapshot) -> 新记录 dict (含 result_id); 引擎幂等落盘
          (result_id 已存在则不重复写 — 兼容 runner 自身已写记录的路径),
          并保证新记录含 input_snapshot (可对比)。
        - input_snapshot 缺失 (旧记录) → ReplayError("旧记录无输入快照,
          无法重跑 — 请确认记录版本") — 如实报告, 不瞎跑。
        """
        record = self._require_record(exec_id)
        snapshot = record.get("input_snapshot")
        if not isinstance(snapshot, dict):
            raise ReplayError(
                f"旧记录无输入快照, 无法重跑 — 请确认记录版本 "
                f"(v1.1.82+ 新执行记录含 input_snapshot): {exec_id}"
            )
        new_record = runner(dict(snapshot))
        if not isinstance(new_record, dict) or not new_record.get("result_id"):
            raise ReplayError("重跑失败: runner 未返回有效新记录 (缺 result_id)")
        new_record = dict(new_record)
        if "input_snapshot" not in new_record:
            new_record["input_snapshot"] = snapshot  # 保证可对比 (引擎兜底)
        self._append_record(new_record)
        return str(new_record["result_id"])

    # ------------------------------------------------------------ 3. compare

    def compare(
        self,
        exec_id1: str,
        exec_id2: str,
        save_to: Optional[Path] = None,
    ) -> str:
        """两次执行真实 diff → markdown 报告 (步骤/结果/耗时/产物)。

        任一 id 无效 → ReplayError; 报告含真实差异 (difflib 步骤 diff +
        结果/耗时/产物显式对比), 非"看起来一样"; save_to → 落盘
        (目录 → <dir>/replay-compare-<id1>-<id2>.md; 文件 → 直接写)。
        """
        if exec_id1 == exec_id2:
            raise ReplayError(f"对比失败: 两次执行不能是同一 id: {exec_id1}")
        rec1 = self._require_record(exec_id1)
        rec2 = self._require_record(exec_id2)
        tl1 = self.dry_run(exec_id1)
        tl2 = self.dry_run(exec_id2)
        report = self._format_compare(exec_id1, rec1, tl1, exec_id2, rec2, tl2)
        if save_to is not None:
            path = self._resolve_save_path(save_to, exec_id1, exec_id2)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(report, encoding="utf-8")
        return report

    # ------------------------------------------------------------ 4. L4 快照回滚 (受限)

    def snapshot_before(self, exec_id: str) -> str:
        """L4 执行前快照: 项目目录 git 状态基线 → 记录 pre_snapshot。

        - 要求记录含项目目录 (input_snapshot.context.project) 且为 git 仓库;
        - git add -A 暂存当前全状态 (含未跟踪文件) → git stash create 生成
          "当前工作区 = 执行前状态" 的提交对象 → baseline (无变更 → HEAD);
          不修改工作区, 不落 stash ref (索引暂存为快照副作用, 回滚时随
          reset --hard 一并恢复);
        - 与 sandbox 的 git 快照机制同源 (sandbox._stage_and_diff 同为
          git add -A + diff 家族; sandbox 本体操作副本, 回滚语义需在项目
          仓库直接取基线 — 语义如实注释)。
        无项目目录 / 非 git 仓库 → ReplayError (明确, 不静默)。
        """
        record = self._require_record(exec_id)
        project_dir = self._record_project_dir(record)
        if project_dir is None:
            raise ReplayError(
                f"执行记录 {exec_id} 无项目目录 (input_snapshot.context.project 缺失), "
                "无法做 L4 快照"
            )
        if not project_dir.is_dir():
            raise ReplayError(f"项目目录不存在: {project_dir} — 无法做 L4 快照")
        if not (project_dir / ".git").is_dir():
            raise ReplayError(
                f"L4 快照需要 git 仓库项目目录 (非 git 仓库无法回滚): {project_dir}"
            )
        staged = self._git(project_dir, "add", "-A")
        if staged.returncode != 0:
            raise ReplayError(
                f"L4 快照失败 (git add -A): {staged.stderr.strip()[:300]}"
            )
        proc = self._git(project_dir, "stash", "create", f"factory-replay-{exec_id}")
        if proc.returncode != 0:
            raise ReplayError(
                f"L4 快照失败 (git stash create): {proc.stderr.strip()[:300]}"
            )
        baseline = proc.stdout.strip()
        if not baseline:  # 无任何变更 → stash create 无输出 → 用 HEAD
            baseline = self._git(project_dir, "rev-parse", "HEAD").stdout.strip()
        if not baseline:
            raise ReplayError(f"L4 快照失败: 无法确定基线提交 ({project_dir})")
        updated = dict(record)
        updated["pre_snapshot"] = {
            "project_dir": str(project_dir),
            "baseline": baseline,
            "method": "git-stash-create",
        }
        self._update_record(updated)
        return baseline

    def rollback(self, exec_id: str) -> None:
        """L4 回滚: pre_snapshot.baseline → git reset --hard + clean -fd 恢复执行前。

        - reset --hard <baseline>: 工作区/索引/HEAD 恢复到执行前状态
          (含执行期间的未提交修改);
        - git clean -fd: 清除执行期间新增的未跟踪文件 (基线含快照时的全部
          未跟踪文件 → 只清执行期新增);
        - 无 pre_snapshot → ReplayError ("请先 snapshot_before"); 回滚后清除
          pre_snapshot (一次性); git 失败 → ReplayError (响亮, 不静默)。
        """
        record = self._require_record(exec_id)
        snap = record.get("pre_snapshot")
        if not isinstance(snap, dict):
            raise ReplayError(f"执行记录 {exec_id} 无 L4 快照 — 请先 snapshot_before")
        project_dir = Path(str(snap.get("project_dir") or ""))
        baseline = str(snap.get("baseline") or "")
        if not project_dir.is_dir() or not baseline:
            raise ReplayError(
                f"L4 回滚信息不完整 (project_dir={project_dir}, baseline={baseline!r})"
            )
        reset = self._git(project_dir, "reset", "--hard", baseline)
        if reset.returncode != 0:
            raise ReplayError(
                f"L4 回滚失败 (git reset --hard): {reset.stderr.strip()[:300]}"
            )
        clean = self._git(project_dir, "clean", "-fd")
        if clean.returncode != 0:
            raise ReplayError(
                f"L4 回滚失败 (git clean -fd): {clean.stderr.strip()[:300]}"
            )
        updated = dict(record)
        updated.pop("pre_snapshot", None)
        self._update_record(updated)

    # ------------------------------------------------------------ 内部: 记录

    def _require_record(self, exec_id: str) -> dict[str, Any]:
        """按 result_id 取执行记录; 无效 → ReplayError (明确错误)。"""
        exec_id = str(exec_id or "").strip()
        if not exec_id:
            raise ReplayError("执行记录 id 不能为空")
        for record in load_records(self.records_file):
            if str(record.get("result_id") or "") == exec_id:
                return record
        raise ReplayError(f"执行记录不存在: {exec_id}")

    def _append_record(self, record: dict[str, Any]) -> None:
        """追加新记录 (幂等: result_id 已存在不重复写); 原子写 (tmp + replace)。"""
        records = load_records(self.records_file)
        rid = str(record.get("result_id") or "")
        if rid and any(str(r.get("result_id") or "") == rid for r in records):
            return
        records.append(record)
        self._write_records(records)

    def _update_record(self, updated: dict[str, Any]) -> None:
        """按 result_id 原位更新记录 (snapshot_before/rollback 写回); 无则追加。"""
        records = load_records(self.records_file)
        rid = str(updated.get("result_id") or "")
        for i, record in enumerate(records):
            if str(record.get("result_id") or "") == rid:
                records[i] = updated
                break
        else:
            records.append(updated)
        self._write_records(records)

    def _write_records(self, records: list[dict[str, Any]]) -> None:
        """原子写 records 文件 (目录自动创建; 失败 → ReplayError, 不静默丢数据)。"""
        try:
            self.records_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.records_file.with_suffix(self.records_file.suffix + ".tmp")
            tmp.write_text(
                json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            os.replace(tmp, self.records_file)
        except OSError as exc:
            raise ReplayError(f"执行记录写入失败: {exc}") from exc

    def latest_exec_id(self, exclude: str = "") -> Optional[str]:
        """最近一次执行记录 result_id (compare 缺省对比对象); 无 → None。"""
        records = load_records(self.records_file)
        for record in reversed(records):
            rid = str(record.get("result_id") or "")
            if rid and rid != exclude:
                return rid
        return None

    # ------------------------------------------------------------ 内部: 时间线

    def _record_step(self, record: dict[str, Any]) -> ReplayStep:
        """执行记录本身 → 时间线步骤 (kind="record")。"""
        return ReplayStep(
            timestamp=str(record.get("timestamp") or ""),
            kind="record",
            event_type="record",
            label="执行记录",
            agent=str(record.get("agent") or ""),
            result=str(record.get("result") or ""),
            detail=str(record.get("error") or record.get("task") or ""),
        )

    def _audit_step(self, event: dict[str, Any]) -> ReplayStep:
        """审计事件 → 时间线步骤 (kind="audit")。"""
        event_type = str(event.get("event_type") or "?")
        label = EVENT_LABELS.get(event_type, event_type)
        detail = str(
            event.get("decision_reason")
            or event.get("artifact_reference")
            or event.get("result")
            or ""
        )
        return ReplayStep(
            timestamp=str(event.get("timestamp") or ""),
            kind="audit",
            event_type=event_type,
            label=label,
            agent=str(event.get("agent_id") or ""),
            result=str(event.get("result") or "OK"),
            detail=detail,
        )

    def _matching_audit_events(self, record: dict[str, Any]) -> list[dict[str, Any]]:
        """关联审计事件 (真实匹配, 非全量倾倒):

        ① 显式 result_id/exec_id 关联 (metadata/字段, 未来快照友好);
        ② snapshot.context.task_id == event.task_id;
        ③ event.task_id == 记录 task (task 即任务 id 时);
        ④ 记录 task 文本出现在 event.decision_reason (任务文本关联);
        ⑤ agent 相同 + 时间窗内 (±event_window_seconds)。
        """
        events = self._load_audit_events()
        if not events:
            return []
        rec_ts = _parse_ts(record.get("timestamp") or "")
        rid = str(record.get("result_id") or "")
        task = str(record.get("task") or "")
        agent = str(record.get("agent") or "")
        snapshot = record.get("input_snapshot")
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        snap_ctx = snapshot.get("context")
        snap_ctx = snap_ctx if isinstance(snap_ctx, dict) else {}
        snap_task_id = str(snap_ctx.get("task_id") or "")
        matched: list[dict[str, Any]] = []
        for event in events:
            event_type = str(event.get("event_type") or "")
            if event_type not in REPLAY_EVENT_TYPES:
                continue
            ev_task = str(event.get("task_id") or "")
            ev_agent = str(event.get("agent_id") or "")
            ev_ts = _parse_ts(event.get("timestamp") or "")
            reason = str(event.get("decision_reason") or "")
            meta = event.get("metadata")
            meta = meta if isinstance(meta, dict) else {}
            # ① 显式 id 关联 (权威 — 不受时间窗限制)
            if rid and rid in (
                str(event.get("result_id") or ""),
                str(meta.get("result_id") or ""),
                str(meta.get("exec_id") or ""),
            ):
                matched.append(event)
                continue
            # ②-⑤ 均需时间窗内 (防止跨次执行文本/任务 id 误关联)
            if not (
                rec_ts is None
                or ev_ts is None
                or abs((ev_ts - rec_ts).total_seconds())
                <= self.event_window_seconds
            ):
                continue
            # ② snapshot task_id 关联
            if snap_task_id and ev_task and ev_task == snap_task_id:
                matched.append(event)
                continue
            # ③ event.task_id == 记录 task (task 为任务 id)
            if ev_task and task and ev_task == task:
                matched.append(event)
                continue
            # ④ 任务文本出现在 decision_reason
            if task and len(task) >= 4 and task in reason:
                matched.append(event)
                continue
            # ⑤ agent 相同
            if ev_agent and agent and ev_agent == agent:
                matched.append(event)
        return matched

    def _load_audit_events(self) -> list[dict[str, Any]]:
        """读 workspace/audit/audit_events.json (list 或 {"events": [...]}); 失败 → []。"""
        audit_file = self.workspace / "audit" / "audit_events.json"
        try:
            if not audit_file.is_file():
                return []
            data = json.loads(audit_file.read_text(encoding="utf-8"))
            events = data.get("events") if isinstance(data, dict) else data
            return events if isinstance(events, list) else []
        except (OSError, json.JSONDecodeError):  # noqa: BLE001 — 失败安全
            return []

    @staticmethod
    def _fill_durations(steps: list[ReplayStep]) -> None:
        """耗时 = 相邻时间戳差 (真实计算; 解析失败 → 0.0; 末步 → 0.0)。"""
        for i, step in enumerate(steps):
            if i == len(steps) - 1:
                step.duration = 0.0
                continue
            cur = _parse_ts(step.timestamp)
            nxt = _parse_ts(steps[i + 1].timestamp)
            if cur is None or nxt is None:
                step.duration = 0.0
            else:
                step.duration = max(0.0, (nxt - cur).total_seconds())

    # ------------------------------------------------------------ 内部: 对比

    def _format_compare(
        self,
        id1: str,
        rec1: dict[str, Any],
        tl1: ReplayTimeline,
        id2: str,
        rec2: dict[str, Any],
        tl2: ReplayTimeline,
    ) -> str:
        """两次执行 → markdown 对比报告 (真实 diff, 非"看起来一样")。"""
        result1 = str(rec1.get("result") or "")
        result2 = str(rec2.get("result") or "")
        result_same = result1 == result2
        dur1 = tl1.total_duration
        dur2 = tl2.total_duration
        dur_delta = dur2 - dur1
        arts1 = self._timeline_artifacts(tl1)
        arts2 = self._timeline_artifacts(tl2)
        artifacts_same = arts1 == arts2
        steps_same = [s.line() for s in tl1.steps] == [s.line() for s in tl2.steps]
        diff_lines = list(
            difflib.unified_diff(
                [s.line() for s in tl1.steps],
                [s.line() for s in tl2.steps],
                fromfile=id1,
                tofile=id2,
                lineterm="\n",
            )
        )
        differences = []
        if not result_same:
            differences.append("结果")
        if abs(dur_delta) > 0.0001 or (dur1 == 0.0) != (dur2 == 0.0):
            differences.append("耗时")
        if not artifacts_same:
            differences.append("产物")
        if not steps_same:
            differences.append("步骤")
        conclusion = (
            "两次执行一致 (步骤/结果/耗时/产物无差异)"
            if not differences
            else f"存在 {len(differences)} 项差异: {' / '.join(differences)}"
        )
        lines = [
            f"# 执行对比报告: {id1} ↔ {id2}",
            "",
            f"> 生成时间: {datetime.now(timezone.utc).isoformat()} · 真实 diff (difflib + 显式字段对比)",
            "",
            "## 1. 概览",
            "",
            "| 维度 | {0} | {1} | 差异 |".format(id1, id2),
            "| --- | --- | --- | --- |",
            f"| 任务 | {self._cell(rec1.get('task'))} | {self._cell(rec2.get('task'))} | "
            f"{'相同' if rec1.get('task') == rec2.get('task') else '⚠ 不同'} |",
            f"| Agent | {self._cell(rec1.get('agent'))} | {self._cell(rec2.get('agent'))} | "
            f"{'相同' if rec1.get('agent') == rec2.get('agent') else '⚠ 不同'} |",
            f"| 结果 | {self._cell(result1)} | {self._cell(result2)} | "
            f"{'相同' if result_same else '⚠ 不同'} |",
            f"| 耗时 | {_fmt_duration(dur1)} | {_fmt_duration(dur2)} | "
            f"{'相同' if dur_delta == 0.0 else f'{_fmt_duration(abs(dur_delta))} ({'增加' if dur_delta > 0 else '减少'})'} |",
            f"| 步骤数 | {len(tl1.steps)} | {len(tl2.steps)} | "
            f"{'相同' if len(tl1.steps) == len(tl2.steps) else '⚠ 不同'} |",
            f"| 产物数 | {len(arts1)} | {len(arts2)} | "
            f"{'相同' if artifacts_same else '⚠ 不同'} |",
            "",
            "## 2. 步骤差异 (真实 diff)",
            "",
        ]
        if diff_lines:
            lines.append("```diff")
            lines.extend(diff_lines)
            lines.append("```")
        else:
            lines.append("（步骤逐行一致）")
        lines += [
            "",
            "## 3. 结果差异",
            "",
            f"- {id1}: **{result1}**" + (f" (error: {rec1.get('error')})" if rec1.get("error") else ""),
            f"- {id2}: **{result2}**" + (f" (error: {rec2.get('error')})" if rec2.get("error") else ""),
            f"- 结论: {'一致' if result_same else '**不同**'}",
            "",
            "## 4. 耗时差异",
            "",
            f"- {id1}: {_fmt_duration(dur1)}",
            f"- {id2}: {_fmt_duration(dur2)}",
            f"- 结论: {'一致' if dur_delta == 0.0 else f'**不同** ({_fmt_duration(abs(dur_delta))} {"增加" if dur_delta > 0 else "减少"})'}",
            "",
            "## 5. 产物差异",
            "",
        ]
        if arts1 or arts2:
            for art in sorted(set(arts1) | set(arts2)):
                mark = "  " if art in arts1 and art in arts2 else ("-" if art in arts1 else "+")
                lines.append(f"- {mark} `{art}`")
            lines.append(f"- 结论: {'一致' if artifacts_same else '**不同**'}")
        else:
            lines.append("（两次执行均无产物信息 — 可从审计 ARTIFACT_CREATED 事件提取）")
        lines += [
            "",
            "## 结论",
            "",
            conclusion,
            "",
        ]
        return "\n".join(lines)

    @staticmethod
    def _cell(value: Any) -> str:
        """表格单元格 (None → '—'; 长文本截断)。"""
        text = str(value or "—")
        return text if len(text) <= 60 else text[:57] + "…"

    @staticmethod
    def _timeline_artifacts(timeline: ReplayTimeline) -> list[str]:
        """时间线产物 (ARTIFACT_CREATED 审计步骤的引用/详情; 记录 artifact 字段)。"""
        artifacts: list[str] = []
        for step in timeline.steps:
            if step.kind == "audit" and step.event_type == "ARTIFACT_CREATED":
                detail = step.detail.strip()
                if detail:
                    artifacts.append(detail)
        record_art = str(timeline.record.get("artifact") or "").strip()
        if record_art:
            artifacts.append(record_art)
        return sorted(set(artifacts))

    def _resolve_save_path(self, save_to: Path, id1: str, id2: str) -> Path:
        """save_to 解析: .md 文件 → 直接用; 目录/无后缀 → 默认文件名。"""
        path = Path(save_to)
        if path.suffix.lower() == ".md":
            return path
        return path / COMPARE_REPORT_NAME.format(id1=id1, id2=id2)

    # ------------------------------------------------------------ 内部: L4 git

    def _record_project_dir(self, record: dict[str, Any]) -> Optional[Path]:
        """记录 → 项目目录 (input_snapshot.context.project; 兜底 workspace/projects)。"""
        snapshot = record.get("input_snapshot")
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        ctx = snapshot.get("context")
        ctx = ctx if isinstance(ctx, dict) else {}
        raw = str(ctx.get("project") or ctx.get("project_dir") or "").strip()
        if not raw:
            return None
        path = Path(raw)
        if path.is_dir():
            return path
        candidate = self.workspace / "projects" / raw
        return candidate if candidate.is_dir() else path

    def _git(self, project_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
        """项目目录跑 git (stash create / rev-parse / reset); 失败 → 返回 rc。"""
        try:
            return subprocess.run(
                [
                    "git",
                    "-C", str(project_dir),
                    "-c", "user.name=factory-replay",
                    "-c", "user.email=replay@factory.local",
                    *args,
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise ReplayError(f"git 执行失败: {exc}") from exc


__all__ = [
    "ReplayEngine",
    "ReplayTimeline",
    "ReplayStep",
    "ReplayError",
    "REPLAY_EVENT_TYPES",
    "EVENT_LABELS",
]
