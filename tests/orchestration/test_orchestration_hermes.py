"""test_orchestration_hermes.py — Hermes Adapter Integration (Mock subprocess)。

覆盖: hermes-runtime 注册 + 内置 HermesRuntimeAdapter 经完整编排链路 (Workflow→
Matcher→Allocator→Execution→Hermes CLI→Result→推进) / subprocess.run 成功与失败
(exit≠0 / stdout 空 / FileNotFoundError / TimeoutExpired → Workflow FAILED 无半完成) /
prompt 构造 (execution input 为 {} 时兜底 "execute execution <id>") /
FACTORY_HERMES_CMD env 覆盖 / Agent 释放与 Assignment FAILED。
"""

from __future__ import annotations

import subprocess

from agents.models import AgentStatus
from agents.registry import AgentRegistry
from assignment.models import AssignmentStatus
from events.models import EventType
from orchestration.pipeline import execute_workflow
from workflows.models import WorkflowStatus

from conftest import (
    make_agent,
    make_step,
    make_task,
    make_workflow,
    seed_agent,
    seed_runtime,
    seed_task,
    seed_workflow,
)


class _FakeCompleted:
    """模拟 subprocess.CompletedProcess (同 test_hermes_adapter 模式)。"""

    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _patch_run(monkeypatch, result: _FakeCompleted | None = None,
               exc: Exception | None = None, seen: list | None = None):
    """替换 runtime.adapters.hermes.subprocess.run; seen 收集 (argv, kwargs)。"""
    def fake_run(argv, **kwargs):
        if seen is not None:
            seen.append((argv, kwargs))
        if exc is not None:
            raise exc
        return result
    monkeypatch.setattr("runtime.adapters.hermes.subprocess.run", fake_run)


def _seed_hermes_env(workflow_store, task_store, agent_store, runtime_store, *,
                     steps=None, agents=None):
    """种子数据: hermes-runtime 注册 + 可选自定义工作流/Agent 集。"""
    wf = make_workflow(steps=steps) if steps is not None else make_workflow()
    seed_workflow(workflow_store, wf)
    if agents is None:
        agents = [make_agent("A-001", role="backend-developer", skills=["development"])]
    for agent in agents:
        seed_agent(agent_store, agent)
    seed_task(task_store, make_task())
    seed_runtime(runtime_store, "hermes-runtime", type_="agent")


class TestHermesSuccess:
    def test_full_chain_hermes_success(self, monkeypatch, workflow_store, task_store,
                                       agent_store, assignment_store, runtime_store,
                                       logger):
        """Hermes CLI 成功 (rc 0 + stdout) → Workflow COMPLETED, 结果含 stdout。"""
        seen: list = []
        _patch_run(monkeypatch, _FakeCompleted(0, "OK from hermes\n"), seen=seen)
        _seed_hermes_env(workflow_store, task_store, agent_store, runtime_store)

        outcome = execute_workflow(
            "T-001", workflow_store=workflow_store, task_store=task_store,
            agent_store=agent_store, assignment_store=assignment_store,
            runtime_store=runtime_store, logger=logger,
        )

        assert outcome.ok
        assert outcome.status is WorkflowStatus.COMPLETED
        assert outcome.steps[0].runtime_id == "hermes-runtime"
        assert outcome.steps[0].result == "SUCCESS"
        assert outcome.run.status is WorkflowStatus.COMPLETED
        # subprocess 调用: hermes -z <prompt>
        assert len(seen) == 1
        argv, kwargs = seen[0]
        assert argv[0] == "hermes"
        assert argv[1] == "-z"
        assert "execute execution" in argv[2]
        assert kwargs["timeout"] > 0
        # 结果落库
        requests = runtime_store.list_executions(task_id="T-001")
        result = runtime_store.get_result(requests[0].id)
        assert result is not None
        assert result.output["stdout"] == "OK from hermes\n"
        assert result.output["runtime_id"] == "hermes-runtime"

    def test_prompt_fallback_when_input_empty(self, monkeypatch, workflow_store, task_store,
                                              agent_store, assignment_store, runtime_store,
                                              logger):
        """编排创建的 execution input={} → prompt 兜底 \"execute execution <id>\"。"""
        seen: list = []
        _patch_run(monkeypatch, _FakeCompleted(0, "ok\n"), seen=seen)
        _seed_hermes_env(workflow_store, task_store, agent_store, runtime_store)

        execute_workflow("T-001", workflow_store=workflow_store, task_store=task_store,
                         agent_store=agent_store, assignment_store=assignment_store,
                         runtime_store=runtime_store, logger=logger)

        argv, _ = seen[0]
        requests = runtime_store.list_executions(task_id="T-001")
        assert argv[2] == f"execute execution {requests[0].id}"

    def test_agent_available_after_hermes_success(self, monkeypatch, workflow_store,
                                                  task_store, agent_store,
                                                  assignment_store, runtime_store, logger):
        _patch_run(monkeypatch, _FakeCompleted(0, "ok\n"))
        _seed_hermes_env(workflow_store, task_store, agent_store, runtime_store)

        execute_workflow("T-001", workflow_store=workflow_store, task_store=task_store,
                         agent_store=agent_store, assignment_store=assignment_store,
                         runtime_store=runtime_store, logger=logger)

        agent = AgentRegistry(agent_store).get("A-001")
        assert agent is not None and agent.status is AgentStatus.AVAILABLE
        assert assignment_store.list()[0].status is AssignmentStatus.COMPLETED

    def test_env_command_override(self, monkeypatch, workflow_store, task_store, agent_store,
                                  assignment_store, runtime_store, logger):
        """构造函数参数覆盖命令 (ADR-0009 决策 3: 参数优先于环境变量)。"""
        from runtime.adapters import HermesRuntimeAdapter
        seen: list = []
        _patch_run(monkeypatch, _FakeCompleted(0, "ok\n"), seen=seen)
        _seed_hermes_env(workflow_store, task_store, agent_store, runtime_store)

        outcome = execute_workflow(
            "T-001", workflow_store=workflow_store, task_store=task_store,
            agent_store=agent_store, assignment_store=assignment_store,
            runtime_store=runtime_store, logger=logger,
            adapters={"hermes-runtime": HermesRuntimeAdapter(command="/fake/hermes-bin")},
        )

        assert outcome.ok
        assert seen[0][0][0] == "/fake/hermes-bin"


class TestHermesFailure:
    def test_exit_nonzero_fails_workflow(self, monkeypatch, workflow_store, task_store,
                                         agent_store, assignment_store, runtime_store,
                                         logger):
        """Hermes exit≠0 → FAILED → Workflow FAILED (无半完成), Agent 回 AVAILABLE。"""
        _patch_run(monkeypatch, _FakeCompleted(1, "", "hermes exploded"))
        _seed_hermes_env(workflow_store, task_store, agent_store, runtime_store)

        outcome = execute_workflow(
            "T-001", workflow_store=workflow_store, task_store=task_store,
            agent_store=agent_store, assignment_store=assignment_store,
            runtime_store=runtime_store, logger=logger,
        )

        assert not outcome.ok
        assert outcome.status is WorkflowStatus.FAILED
        assert "hermes command exited with code 1" in (outcome.error or "")
        assert outcome.run.status is WorkflowStatus.FAILED
        assert outcome.run.error is not None
        agent = AgentRegistry(agent_store).get("A-001")
        assert agent is not None and agent.status is AgentStatus.AVAILABLE
        assert assignment_store.list()[0].status is AssignmentStatus.FAILED
        # 执行结果 FAILED 落库
        requests = runtime_store.list_executions(task_id="T-001")
        result = runtime_store.get_result(requests[0].id)
        assert result is not None and result.status.value == "FAILED"

    def test_empty_stdout_fails_workflow(self, monkeypatch, workflow_store, task_store,
                                         agent_store, assignment_store, runtime_store,
                                         logger):
        """Hermes rc=0 但 stdout 空 → FAILED (ADR-0009 决策 2)。"""
        _patch_run(monkeypatch, _FakeCompleted(0, "", ""))
        _seed_hermes_env(workflow_store, task_store, agent_store, runtime_store)

        outcome = execute_workflow(
            "T-001", workflow_store=workflow_store, task_store=task_store,
            agent_store=agent_store, assignment_store=assignment_store,
            runtime_store=runtime_store, logger=logger,
        )

        assert not outcome.ok
        assert "no output" in (outcome.error or "")

    def test_command_not_found_fails_workflow(self, monkeypatch, workflow_store, task_store,
                                              agent_store, assignment_store, runtime_store,
                                              logger):
        """hermes 命令不存在 (FileNotFoundError) → FAILED → Workflow FAILED。"""
        _patch_run(monkeypatch, exc=FileNotFoundError("no such file"))
        _seed_hermes_env(workflow_store, task_store, agent_store, runtime_store)

        outcome = execute_workflow(
            "T-001", workflow_store=workflow_store, task_store=task_store,
            agent_store=agent_store, assignment_store=assignment_store,
            runtime_store=runtime_store, logger=logger,
        )

        assert not outcome.ok
        assert "hermes command not found" in (outcome.error or "")
        assert outcome.run.status is WorkflowStatus.FAILED

    def test_timeout_fails_workflow(self, monkeypatch, workflow_store, task_store,
                                    agent_store, assignment_store, runtime_store, logger):
        """Hermes 超时 (TimeoutExpired) → FAILED → Workflow FAILED。"""
        _patch_run(monkeypatch, exc=subprocess.TimeoutExpired(cmd="hermes", timeout=300))
        _seed_hermes_env(workflow_store, task_store, agent_store, runtime_store)

        outcome = execute_workflow(
            "T-001", workflow_store=workflow_store, task_store=task_store,
            agent_store=agent_store, assignment_store=assignment_store,
            runtime_store=runtime_store, logger=logger,
        )

        assert not outcome.ok
        assert "timed out" in (outcome.error or "")

    def test_os_error_fails_workflow(self, monkeypatch, workflow_store, task_store,
                                     agent_store, assignment_store, runtime_store, logger):
        """OS 级错误 (PermissionError) → FAILED → Workflow FAILED。"""
        _patch_run(monkeypatch, exc=PermissionError("denied"))
        _seed_hermes_env(workflow_store, task_store, agent_store, runtime_store)

        outcome = execute_workflow(
            "T-001", workflow_store=workflow_store, task_store=task_store,
            agent_store=agent_store, assignment_store=assignment_store,
            runtime_store=runtime_store, logger=logger,
        )

        assert not outcome.ok
        assert outcome.run.status is WorkflowStatus.FAILED

    def test_failed_event_sequence(self, monkeypatch, workflow_store, task_store,
                                   agent_store, assignment_store, runtime_store, logger):
        """Hermes 失败事件序: started → step.started → workflow.failed → orchestration.failed。"""
        _patch_run(monkeypatch, _FakeCompleted(1, "", "boom"))
        _seed_hermes_env(workflow_store, task_store, agent_store, runtime_store)

        outcome = execute_workflow(
            "T-001", workflow_store=workflow_store, task_store=task_store,
            agent_store=agent_store, assignment_store=assignment_store,
            runtime_store=runtime_store, logger=logger,
        )

        types = [e.type.value for e in logger.store.query()]
        assert types[0] == "orchestration.started"
        assert "orchestration.step.started" in types
        assert "execution.failed" in types
        assert "workflow.failed" in types
        assert types[-1] == "orchestration.failed"
        assert "orchestration.completed" not in types

    def test_no_half_completed_state(self, monkeypatch, workflow_store, task_store,
                                     agent_store, assignment_store, runtime_store, logger):
        """Hermes 失败: 运行实例 FAILED, 无 COMPLETED 步骤 (无半完成)。"""
        _patch_run(monkeypatch, _FakeCompleted(1, "", "boom"))
        _seed_hermes_env(workflow_store, task_store, agent_store, runtime_store)

        outcome = execute_workflow(
            "T-001", workflow_store=workflow_store, task_store=task_store,
            agent_store=agent_store, assignment_store=assignment_store,
            runtime_store=runtime_store, logger=logger,
        )

        assert outcome.run is not None
        assert outcome.run.status is WorkflowStatus.FAILED
        assert "COMPLETED" not in [st.status.value for st in outcome.run.step_states]
        assert outcome.events[-1].type is EventType.ORCHESTRATION_FAILED

    def test_second_step_hermes_failure(self, monkeypatch, workflow_store, task_store,
                                        agent_store, assignment_store, runtime_store,
                                        logger):
        """第 2 步 Hermes 失败: 第 1 步 COMPLETED (真实完成), 整体 FAILED。"""
        calls = {"n": 0}

        def fake_run(argv, **kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                return _FakeCompleted(1, "", "second boom")
            return _FakeCompleted(0, "ok\n")

        monkeypatch.setattr("runtime.adapters.hermes.subprocess.run", fake_run)
        wf = make_workflow(steps=[
            make_step("s1", 1, skill="development", role="backend-developer"),
            make_step("s2", 2, skill="development", role="backend-developer"),
        ])
        _seed_hermes_env(workflow_store, task_store, agent_store, runtime_store,
                         steps=wf.steps)

        outcome = execute_workflow(
            "T-001", workflow_store=workflow_store, task_store=task_store,
            agent_store=agent_store, assignment_store=assignment_store,
            runtime_store=runtime_store, logger=logger,
        )

        assert not outcome.ok
        assert [s.step_id for s in outcome.steps] == ["s1", "s2"]
        assert outcome.steps[0].status.value == "COMPLETED"
        assert outcome.steps[1].status.value == "FAILED"
        assert calls["n"] == 2  # 失败后立即停止
        assert outcome.run.status is WorkflowStatus.FAILED
