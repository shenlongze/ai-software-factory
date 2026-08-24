"""tests/console/test_m3e_full_chain.py — M3e 调度器接管真实执行 + 动态分配契约测试 (S10-097)。

覆盖 (Hermes 规格 §6 验收):
1. 全链真实执行: 复合任务 → decompose → critical → scheduler → 真实执行 → 产物
   (decomposition.json / plan.json / schedule.json / 代码文件 / evidence 证据包)
2. 动态分配: AgentMatcher 返回的 agent_id 落盘 state.m3.assignments (每任务有 agent_id)
3. 旧路径零变化: mode=solo → 原 TaskTree 流程 (execution_plan.json 顺序, 无 m3 落盘)
4. 单任务失败不中断: 轮内一个任务失败 → 下一轮继续 (诚实标注失败)
5. 冲突串行: 同文件任务不同轮 (ConflictResolver 生效)
6. 失败回退: M3 链异常 → 降级 solo + degraded 标注 (EXECUTION_M3_DEGRADED 审计)

额外 (规格 §5): 5 审计事件 ∈ EVENT_TYPES 且全链真实发射。

basename 全仓库唯一 (test_console_* 前缀); 本目录自洽 (conftest 已挂仓库根)。
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

AUDIT = importlib.import_module("factory-console.audit.audit_event")
AUDIT_STORE = importlib.import_module("factory-console.audit.audit_store")
DEC = importlib.import_module("factory-console.session.decomposer")
ORCH = importlib.import_module("factory-console.session.orchestrator")

#: M3 动态分配用 Agent 注册表 (skill 对齐技术层 agent_type → 匹配必命中)
AGENTS = {
    "backend-1": {"id": "backend-1", "name": "backend-1", "skills": ["python", "api", "database"]},
    "frontend-1": {"id": "frontend-1", "name": "frontend-1", "skills": ["flutter", "dart", "ui", "frontend"]},
    "qa-1": {"id": "qa-1", "name": "qa-1", "skills": ["test", "qa"]},
}

#: M3 5 审计事件 (注册表契约)
M3_EVENTS = (
    "EXECUTION_ROUND_STARTED",
    "EXECUTION_TASK_ASSIGNED",
    "EXECUTION_TASK_COMPLETED",
    "EXECUTION_ROUND_COMPLETED",
    "EXECUTION_M3_DEGRADED",
)


def _project(root: Path, *, features: list[str], agents: dict | None = AGENTS) -> Path:
    """projects/<slug>/ 固定资产 (project.json + product.json + execution_plan.json
    + agents.json) — 零 ~/.factory 污染。"""
    ws = root / "ws"
    ws.mkdir(exist_ok=True)
    pdir = ws / "projects" / "demo"
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "project.json").write_text(
        json.dumps({"name": "demo", "status": "execution_ready"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (pdir / "product.json").write_text(
        json.dumps({
            "name": "demo",
            "problem": "实现一个简单记账应用",
            "user": "个人用户",
            "core_features": features,
            "status": "project_created",
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    (pdir / "execution_plan.json").write_text(
        json.dumps({
            "tasks": [{"id": "legacy-t1", "name": "旧路径任务"}, {"id": "legacy-t2", "name": "旧路径任务2"}],
            "count": 2,
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    agents_file = root / "agents.json"
    agents_file.write_text(json.dumps(agents or {}, ensure_ascii=False), encoding="utf-8")
    return pdir


def _patch_fn(task: dict, project_dir: Path) -> str:
    """任务 → 真实 unified diff patch (写回项目目录后经 deliver_patch 应用)。"""
    tid = str(task.get("id") or "task")
    fname = f"gen_{tid.replace('-', '_')}.py"
    return f"""diff --git a/{fname} b/{fname}
new file mode 100644
--- /dev/null
+++ b/{fname}
@@ -0,0 +1,2 @@
+def fn_{tid.replace('-', '_')}():
+    return 1
+
"""


def _execute_ok(task: dict, project_dir: Path, workspace: Path) -> dict:
    """真实执行: 任务 → patch 落盘 → deliver_patch 应用 → 项目目录出现代码文件。"""
    tid = str(task.get("id") or "task")
    art = project_dir / "artifacts" / f"{tid}.patch"
    art.parent.mkdir(parents=True, exist_ok=True)
    art.write_text(_patch_fn(task, project_dir), encoding="utf-8")
    return {"success": True, "artifact": str(art)}


def _audit_types(ws: Path) -> set[str]:
    store = AUDIT_STORE.AuditStore(workspace=ws)
    return {e.event_type for e in store.events()}


class TestFullChainRealExecution:
    def test_full_chain_product_to_artifacts(self, tmp_path):
        """复合任务 → M3 全链 → 真实执行 → 项目目录有产物 (非只算轮次)。"""
        pdir = _project(tmp_path, features=["登录", "注册"])
        orch = ORCH.ExecutionOrchestrator(tmp_path / "ws")
        calls: list[str] = []
        def execute_fn(task, project_dir, workspace):
            calls.append(str(task.get("id")))
            return _execute_ok(task, project_dir, workspace)
        result = orch.execute_project(
            "demo", mode="m3", execute_fn=execute_fn,
            agents_file=tmp_path / "agents.json", max_concurrency=2,
        )
        # 真实执行: 8 原子叶子 (2 feature × 4 技术层) 全完成
        assert result.failed_tasks == 0
        assert result.completed_tasks == 8
        assert result.status == "user_acceptance"
        # 产物: 项目目录出现真实代码文件 (deliver_patch 应用)
        code_files = sorted(p.name for p in pdir.glob("gen_*.py"))
        assert len(code_files) == 8, code_files
        # M3a/b/c 产物落盘
        assert (pdir / "decomposition.json").is_file()
        assert (pdir / "plan.json").is_file()
        assert (pdir / "schedule.json").is_file()
        # 证据: 每任务 EvidenceBundle 落盘 evidence/
        state = orch._load_state(pdir)
        assert len(state.m3["evidence"]) == 8
        evidence_dir = pdir / "evidence"
        assert len(list(evidence_dir.glob("ev-*.json"))) >= 8
        bundle = json.loads(sorted(evidence_dir.glob("ev-*.json"))[0].read_text(encoding="utf-8"))
        assert bundle["task_id"] and bundle["bundle_id"] and bundle["diff"]
        # 依赖就绪: 执行序 = rounds 扁平序 (轮内依序), 技术层链不逆序
        expected_order = [tid for r in state.m3["rounds"] for tid in r]
        assert calls == expected_order
        assert calls[0].endswith("-db") and calls[-1].endswith("-test")

    def test_five_audit_events_registered_and_emitted(self, tmp_path):
        """5 EXECUTION_* 事件 ∈ EVENT_TYPES 且全链真实发射 (注册表 + 存储)。"""
        for ev in M3_EVENTS:
            assert ev in AUDIT.EVENT_TYPES, ev
        _project(tmp_path, features=["登录"])
        orch = ORCH.ExecutionOrchestrator(tmp_path / "ws")
        orch.execute_project(
            "demo", mode="m3", execute_fn=_execute_ok,
            agents_file=tmp_path / "agents.json",
        )
        types = _audit_types(tmp_path / "ws")
        for ev in ("EXECUTION_ROUND_STARTED", "EXECUTION_TASK_ASSIGNED",
                   "EXECUTION_TASK_COMPLETED", "EXECUTION_ROUND_COMPLETED"):
            assert ev in types, ev
        assert "EXECUTION_M3_DEGRADED" not in types  # 全链成功 → 无降级


class TestDynamicAssignment:
    def test_assignments_agent_id_per_task(self, tmp_path):
        """AgentMatcher 实时匹配 → state.m3.assignments 每任务有 agent_id。"""
        pdir = _project(tmp_path, features=["登录"])
        orch = ORCH.ExecutionOrchestrator(tmp_path / "ws")
        orch.execute_project(
            "demo", mode="m3", execute_fn=_execute_ok,
            agents_file=tmp_path / "agents.json", max_concurrency=1,
        )
        state = orch._load_state(pdir)
        assigns = state.m3["assignments"]
        assert len(assigns) == 4  # 1 feature × 4 技术层
        by_type = {str(t["id"]).rsplit("-", 1)[-1]: a for t, a in zip(state.tasks, assigns)}
        # skill 匹配: db/api → backend-1; frontend → frontend-1; test → qa-1
        assert by_type["db"]["agent_id"] == "backend-1"
        assert by_type["api"]["agent_id"] == "backend-1"
        assert by_type["frontend"]["agent_id"] == "frontend-1"
        assert by_type["test"]["agent_id"] == "qa-1"
        assert all(a["matched"] is True and a["agent_id"] for a in assigns)
        assert all(a["round"] >= 1 and a["task"] for a in assigns)
        # 任务级 agent 回填 (执行消费)
        task_agents = {str(t["id"]): t.get("agent") for t in state.tasks}
        assert task_agents == {a["task"]: a["agent_id"] for a in assigns}

    def test_no_match_honest_reported(self, tmp_path):
        """空注册表 → 无匹配诚实报告 (不伪造分配), 任务仍执行。"""
        pdir = _project(tmp_path, features=["登录"], agents={})
        orch = ORCH.ExecutionOrchestrator(tmp_path / "ws")
        # AgentRegistry.load 空文件会回退默认注册表 → 注入空注册表 (诚实无匹配路径)
        orig_load = ORCH.AgentRegistry.load
        ORCH.AgentRegistry.load = classmethod(lambda cls, f=None: {})
        try:
            result = orch.execute_project(
                "demo", mode="m3", execute_fn=_execute_ok,
                agents_file=tmp_path / "agents.json",
            )
        finally:
            ORCH.AgentRegistry.load = orig_load
        state = orch._load_state(pdir)
        assigns = state.m3["assignments"]
        assert assigns and all(a["matched"] is False and a["agent_id"] == "" for a in assigns)
        assert all("无匹配" in a["reason"] or "无可用" in a["reason"] for a in assigns)
        assert result.failed_tasks == 0  # 无匹配不阻塞执行


class TestSoloPathUnchanged:
    def test_solo_mode_zero_change(self, tmp_path):
        """mode=solo (默认): 原 TaskTree 流程 — execution_plan.json 顺序执行, 无 m3。"""
        pdir = _project(tmp_path, features=["登录"])
        orch = ORCH.ExecutionOrchestrator(tmp_path / "ws")
        calls: list[str] = []
        def execute_fn(task, project_dir, workspace):
            calls.append(str(task.get("id")))
            return {"success": True, "artifact": ""}
        result = orch.execute_project("demo", execute_fn=execute_fn)
        # 旧路径: 按 execution_plan.json 任务顺序执行 (无 decompose 产物驱动)
        assert calls == ["legacy-t1", "legacy-t2"]
        assert result.failed_tasks == 0
        assert result.completed_tasks == 2
        state = orch._load_state(pdir)
        assert state.m3 == {}
        assert state.schedule == {}
        # 无 M3 产物副作用
        assert not (pdir / "schedule.json").is_file()


class TestSingleTaskFailureIsolation:
    def test_one_task_failure_continues_next_rounds(self, tmp_path):
        """轮内一个任务失败 → 后续轮次继续 (诚实标注失败, 不中断整链)。"""
        pdir = _project(tmp_path, features=["登录", "注册"])
        orch = ORCH.ExecutionOrchestrator(tmp_path / "ws")
        def execute_fn(task, project_dir, workspace):
            tid = str(task.get("id") or "")
            if tid.endswith("-db") and "f1" in tid:
                return {"success": False, "error": "模拟单任务失败"}
            return _execute_ok(task, project_dir, workspace)
        result = orch.execute_project(
            "demo", mode="m3", execute_fn=execute_fn,
            agents_file=tmp_path / "agents.json", max_concurrency=2,
        )
        assert result.failed_tasks == 1
        assert result.completed_tasks == 7
        state = orch._load_state(pdir)
        statuses = {str(t["id"]): t["status"] for t in state.tasks}
        assert statuses["root-f1-db"] == "failed"
        # 后续轮次继续: f1-api / f1-frontend / f1-test 仍完成
        assert statuses["root-f1-api"] == "completed"
        assert statuses["root-f1-frontend"] == "completed"
        assert statuses["root-f1-test"] == "completed"
        assert result.status == "failed"  # 有失败 → 保持 DEVELOPMENT 语义
        assert state.m3["rounds"]  # 轮次完整
        # 失败任务有错误回填
        failed_task = next(t for t in state.tasks if t["status"] == "failed")
        assert "模拟单任务失败" in str(failed_task.get("error") or "")


class TestConflictSerialization:
    def test_same_file_tasks_in_different_rounds(self, tmp_path):
        """同 target_file 任务 → ConflictResolver 串行化 → 不同轮 (M3 链调度生效)。"""
        pdir = _project(tmp_path, features=["登录"])
        # M3b 输入: plan.json 含同文件冲突任务 (A/B 同 target_file → 串行)
        (pdir / "plan.json").write_text(
            json.dumps({
                "project_id": "demo",
                "tasks": [
                    {"id": "A", "name": "任务A", "agent_type": "backend", "target_file": "src/shared.py"},
                    {"id": "B", "name": "任务B", "agent_type": "backend", "target_file": "src/shared.py"},
                    {"id": "C", "name": "任务C", "agent_type": "backend", "target_file": "src/c.py"},
                ],
                "edges": [],
                "order": ["A", "B", "C"],
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        orch = ORCH.ExecutionOrchestrator(tmp_path / "ws")
        calls: list[str] = []
        def execute_fn(task, project_dir, workspace):
            calls.append(str(task.get("id")))
            return {"success": True, "artifact": ""}
        result = orch.execute_project(
            "demo", mode="m3", execute_fn=execute_fn,
            agents_file=tmp_path / "agents.json", max_concurrency=3,
        )
        assert result.failed_tasks == 0
        assert result.completed_tasks == 3
        state = orch._load_state(pdir)
        rounds = state.m3["rounds"]
        round_of = {tid: i for i, r in enumerate(rounds, start=1) for tid in r}
        assert round_of["A"] != round_of["B"], f"同文件任务必须串行: {rounds}"
        # 执行序: A 先于 B (冲突串行生效)
        assert calls.index("A") < calls.index("B")
        # 调度冲突记录落盘 (ConflictResolver 生效)
        sched = json.loads((pdir / "schedule.json").read_text(encoding="utf-8"))
        assert any("src/shared.py" in c.get("reason", "") for c in sched.get("conflicts", [])), sched
        # 动态分配仍生效 (计划输入路径)
        assert all(a["agent_id"] for a in state.m3["assignments"])


class TestFailureFallback:
    def test_m3_chain_exception_degrades_to_solo(self, tmp_path, monkeypatch):
        """M3 链异常 → 降级 solo 顺序执行 + degraded 标注 (诚实, 不伪造 M3)。"""
        pdir = _project(tmp_path, features=["登录"])
        monkeypatch.setattr(
            DEC.DecomposeEngine, "decompose",
            lambda self, task, **kw: (_ for _ in ()).throw(RuntimeError("模拟 M3 计划链异常")),
        )
        orch = ORCH.ExecutionOrchestrator(tmp_path / "ws")
        calls: list[str] = []
        def execute_fn(task, project_dir, workspace):
            calls.append(str(task.get("id")))
            return {"success": True, "artifact": ""}
        result = orch.execute_project(
            "demo", mode="m3", execute_fn=execute_fn,
            agents_file=tmp_path / "agents.json",
        )
        # 降级 solo: 按 execution_plan.json 顺序执行旧队列
        assert calls == ["legacy-t1", "legacy-t2"]
        assert result.failed_tasks == 0
        assert result.completed_tasks == 2
        state = orch._load_state(pdir)
        assert state.m3.get("degraded") is True
        assert "solo" in str(state.m3.get("reason"))
        assert state.m3["rounds"] == [] and state.m3["assignments"] == []
        # EXECUTION_M3_DEGRADED 审计 (诚实标注)
        assert "EXECUTION_M3_DEGRADED" in _audit_types(tmp_path / "ws")
