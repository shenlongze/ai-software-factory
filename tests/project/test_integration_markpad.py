"""test_integration_markpad.py — Phase 5A 集成: markpad 配置加载 → 注册 → 完整 echo 链路。

链路 (phase5a-status.md §验证): 加载 markpad agents/workflows → task create →
workflow run --auto (echo runtime, 不调真实 hermes) → Workflow COMPLETED +
全事件序 (orchestration.* / workflow.* / assignment.* / execution.*)。

说明: CLI `workflow add` 只支持内置定义或纯步骤名 (无法表达 required_role/
required_skill), 故带元数据的工作流经 project.loader → WorkflowEngine API 注册 —
这是示例层与既有引擎的集成点 (ADR-0013 决策 4)。
"""

from __future__ import annotations

from pathlib import Path

from agents.registry import AgentRegistry
from agents.store import AgentStore
from assignment.store import AssignmentStore
from project.loader import load_project
from runtime.store import RuntimeStore
from tasks.store import TaskStore
from workflows.engine import WorkflowEngine
from workflows.models import Workflow, WorkflowStep, WorkflowStatus
from workflows.store import WorkflowStore

from cli_helpers import event_types, open_events, run_cli


def _register_markpad(capsys, cli_root: Path, examples_dir: Path) -> None:
    """markpad 配置 → 工厂注册 (agent 走 CLI, workflow 走引擎 API — 见模块 docstring)。"""
    cfg = load_project(examples_dir, "markpad")
    assert cfg is not None
    for a in cfg.agents:
        rc, out, err = run_cli(
            capsys, cli_root, "agent", "add", "--id", a.id, "--role", a.role,
            "--skills", ",".join(a.skills), "--name", a.name,
        )
        assert rc == 0, err
    engine = WorkflowEngine(
        WorkflowStore(cli_root / "workflows"), task_store=TaskStore(cli_root / "tasks")
    )
    for w in cfg.workflows:
        steps = [
            WorkflowStep(
                id=s.id, name=s.name or s.id, order=i + 1,
                required_skill=s.required_skill, required_role=s.required_role,
            )
            for i, s in enumerate(w.steps)
        ]
        engine.create_workflow(
            Workflow(id=w.id, name=w.name or w.id, description=w.description, steps=steps)
        )
    rc, out, err = run_cli(capsys, cli_root, "runtime", "add", "--id", "echo", "--type", "mock")
    assert rc == 0, err


class TestMarkpadEchoChain:
    def test_bugfix_full_chain_completed(self, capsys, cli_root: Path, examples_dir: Path):
        """bug-fix 任务: 4 步全完成 (reproduce→diagnose→fix→verify), echo runtime。"""
        _register_markpad(capsys, cli_root, examples_dir)
        rc, out, err = run_cli(
            capsys, cli_root, "task", "create", "--id", "T-101",
            "--title", "修复编辑器光标位置错乱", "--project", "markpad",
            "--type", "bug", "--workflow", "bug-fix",
        )
        assert rc == 0, err

        rc, out, err = run_cli(capsys, cli_root, "workflow", "run", "--auto", "T-101")
        assert rc == 0, err
        assert "COMPLETED" in out

        engine = WorkflowEngine(
            WorkflowStore(cli_root / "workflows"), task_store=TaskStore(cli_root / "tasks")
        )
        run = engine.status("T-101")
        assert run is not None
        assert run.status is WorkflowStatus.COMPLETED
        assert run.all_steps_completed()

        # 每步一个执行 + 一个 assignment (echo 全 SUCCESS)
        assert len(RuntimeStore(cli_root / "runtimes").list_executions()) == 4
        assert len(AssignmentStore(cli_root / "assignments").list()) == 4
        results = RuntimeStore(cli_root / "runtimes").list_results()
        assert len(results) == 4 and all(r.status.value == "SUCCESS" for r in results)

        # agents 全部回 AVAILABLE (每步完成即释放)
        reg = AgentRegistry(AgentStore(cli_root / "agents"))
        assert all(reg.get(a.id).status.value == "AVAILABLE" for a in
                   load_project(examples_dir, "markpad").agents)

    def test_full_event_sequence(self, capsys, cli_root: Path, examples_dir: Path):
        """注册事件在前, orchestration.started 开头、orchestration.completed 收尾, 底层事件全序在中间。"""
        _register_markpad(capsys, cli_root, examples_dir)
        run_cli(capsys, cli_root, "task", "create", "--id", "T-201",
                "--title", "渲染引擎性能优化", "--project", "markpad", "--workflow", "feature")
        run_cli(capsys, cli_root, "workflow", "run", "--auto", "T-201")

        with open_events(cli_root) as store:
            types = event_types(store)
        # 注册事件 (agent.registered ×3 + runtime.registered) 在前, 编排链从 orchestration.started 开始
        assert "orchestration.started" in types
        start = types.index("orchestration.started")
        assert types[-1] == "orchestration.completed"
        chain = types[start:]
        for t in ("workflow.started", "workflow.step.started", "workflow.step.completed",
                  "workflow.completed", "agent.assignment.created", "agent.assignment.completed",
                  "agent.released", "execution.created", "execution.started", "execution.completed",
                  "orchestration.step.started", "orchestration.step.completed"):
            assert t in chain, f"missing event {t}"
        # 4 步 × 每步 step.started/step.completed
        assert chain.count("orchestration.step.completed") == 4
        assert chain.count("execution.completed") == 4

    def test_feature_workflow_agent_rotation(self, capsys, cli_root: Path, examples_dir: Path):
        """feature 工作流: architect → flutter-developer → tester → tester (复用 tester)。"""
        _register_markpad(capsys, cli_root, examples_dir)
        run_cli(capsys, cli_root, "task", "create", "--id", "T-301",
                "--title", "新增表格语法支持", "--project", "markpad", "--workflow", "feature")
        rc, out, err = run_cli(capsys, cli_root, "workflow", "run", "--auto", "T-301")
        assert rc == 0, err
        assert "COMPLETED" in out

        assignments = AssignmentStore(cli_root / "assignments").list()
        by_step = {a.workflow_step_id: a.agent_id for a in assignments}
        assert by_step["architecture"] == "architect"
        assert by_step["development"] == "flutter-developer"
        assert by_step["testing"] == "tester"
        assert by_step["validation"] == "tester"

    def test_no_matching_agent_workflow_failed(self, capsys, cli_root: Path, examples_dir: Path):
        """缺匹配 agent → Workflow FAILED (无半完成状态), CLI 退出码 1。"""
        _register_markpad(capsys, cli_root, examples_dir)
        # 移除 flutter-developer / tester: 只剩 architect → development 步起无匹配 agent
        reg = AgentRegistry(AgentStore(cli_root / "agents"))
        reg.remove("flutter-developer")
        reg.remove("tester")
        run_cli(capsys, cli_root, "task", "create", "--id", "T-401",
                "--title", "主题切换", "--project", "markpad", "--workflow", "feature")
        rc, out, err = run_cli(capsys, cli_root, "workflow", "run", "--auto", "T-401")
        assert rc == 1
        assert "FAILED" in out

        engine = WorkflowEngine(
            WorkflowStore(cli_root / "workflows"), task_store=TaskStore(cli_root / "tasks")
        )
        run = engine.status("T-401")
        assert run is not None and run.status is WorkflowStatus.FAILED
        # 无半完成: 失败步骤 (development) 之后不得出现 COMPLETED; 失败步自身 FAILED
        states = {st.step_id: st.status.value for st in run.step_states}
        assert states["development"] == "FAILED"
        assert states["testing"] == "PENDING" and states["validation"] == "PENDING"
        assert "COMPLETED" not in [v for k, v in states.items() if k != "architecture"]

    def test_config_to_registry_mapping_1to1(self, capsys, cli_root: Path, examples_dir: Path):
        """加载器 → 注册表 1:1: 配置里的 agent/workflow 全部可查。"""
        _register_markpad(capsys, cli_root, examples_dir)
        cfg = load_project(examples_dir, "markpad")
        assert cfg is not None
        reg = AgentRegistry(AgentStore(cli_root / "agents"))
        for a in cfg.agents:
            got = reg.get(a.id)
            assert got is not None and got.role == a.role
            assert set(got.skills) == set(a.skills)
        engine = WorkflowEngine(
            WorkflowStore(cli_root / "workflows"), task_store=TaskStore(cli_root / "tasks")
        )
        for w in cfg.workflows:
            wf = engine.get_workflow(w.id)
            assert wf is not None and wf.name == w.name
            assert [s.id for s in wf.ordered_steps()] == [s.id for s in w.steps]
