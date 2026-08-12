"""tests/exec/test_exec_agent_executor.py — S10-016 Agent Executor 测试 (Task 002)。

覆盖 (Agent Executor — 第一个真实 AI Employee 执行闭环):
- 全链路 Success: Task/Agent 校验 → Session PENDING→RUNNING → LLM 调用
  (复用 AgentRuntime.execute + Provider) → 事件链 → SUCCESS → Output 保留
  (execution_output/execution_summary/raw_response)
- 事件序列断言: agent_started → task_received → llm_request_sent →
  llm_response_received → output_generated → execution_finished (保序)
- Failure Case: LLM Provider 错误 → execution_failed 事件 + FAILED 状态 +
  错误信息进事件 (不静默)
- 错误处理: Task 不存在 → TaskNotFoundError; Agent 不存在 →
  AgentNotFoundError; runtime 意外异常 → FAILED session (不抛裸异常)
- 持久化: 重启 (重建 store) 后 session/output/事件仍可查
- 诚实降级: 无 Provider (runtime=None) → FAILED session + 事件
  (Provider Adapter Interface, 不伪造结果)

basename 全仓库唯一 (test_exec_* 前缀); 依赖 tests/exec/conftest.py 的 sys.path。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from exec.agent_executor import (
    AgentExecutor,
    AgentNotFoundError,
    TaskNotFoundError,
)
from exec.agent_runtime import AgentRuntime
from exec.models import ExecutionRequest
from exec.provider import ProviderRegistry
from exec.runtime_session import RuntimeEventType, RuntimeSessionStore
from exec_helpers import FakeProvider, write_files  # noqa: E402  (tests/exec/)

#: FakeProvider 成功 content: <patch>NO_CHANGE</patch> — 合法「无修改」交付
#: (DeveloperAgent 空补丁 → 验证通过 → SUCCESS; 不伪造真实 LLM 结果)。
NO_CHANGE_PATCH = "<patch>NO_CHANGE</patch>"

MINI_PROJECT = {
    "calc.py": "def add(a, b):\n    return a + b\n",
}


def _task_store(root: Path):
    """真实 Core TaskStore (<root>/tasks — 单任务单文件)。"""
    from tasks.store import TaskStore

    return TaskStore(root / "tasks")


def _agent_registry(root: Path):
    """真实 Core AgentRegistry (AgentStore + 事件可选)。"""
    from agents.registry import AgentRegistry
    from agents.store import AgentStore

    return AgentRegistry(AgentStore(root / "agents"))


def _make_task(task_store, task_id: str = "T-101", title: str = "fix the sub bug"):
    from tasks.models import Task

    task = Task(id=task_id, title=title, project="demo", type="feature", workflow="dev")
    task_store.create(task)
    return task


def _make_agent(agent_registry, agent_id: str = "developer-1", name: str = "Developer"):
    from agents.models import Agent

    agent, _ev = agent_registry.register(
        Agent(id=agent_id, name=name, role="developer")
    )
    return agent


def _make_runtime(
    provider,
    *,
    root: Path,
    project_dir: Path,
    store=None,
    logger=None,
) -> AgentRuntime:
    """真实 AgentRuntime (复用执行引擎 — 沙箱副本 + Developer + 验证循环)。"""
    work_root = root / "work"
    work_root.mkdir(parents=True, exist_ok=True)  # mkdtemp(dir=...) 须已存在
    return AgentRuntime(
        provider,
        store=store,
        logger=logger,
        work_root=work_root,
        validation_command=None,
    )


@pytest.fixture
def executor_env(tmp_path: Path):
    """最小装配: 真实 TaskStore/AgentRegistry/RuntimeSessionStore + FakeProvider。"""
    root = tmp_path / "factory"
    task_store = _task_store(root)
    agent_registry = _agent_registry(root)
    session_store = RuntimeSessionStore(root / "runtime-sessions")
    project_dir = tmp_path / "project"
    write_files(project_dir, MINI_PROJECT)
    provider = FakeProvider(content=NO_CHANGE_PATCH, usage={"input_tokens": 10, "output_tokens": 5})
    runtime = _make_runtime(provider, root=root, project_dir=project_dir)
    executor = AgentExecutor(
        task_store=task_store,
        agent_registry=agent_registry,
        session_store=session_store,
        runtime=runtime,
    )
    return {
        "root": root,
        "task_store": task_store,
        "agent_registry": agent_registry,
        "session_store": session_store,
        "project_dir": project_dir,
        "provider": provider,
        "runtime": runtime,
        "executor": executor,
    }


# ------------------------------------------------------------------ 全链路 Success


class TestAgentExecutorSuccess:
    def test_full_chain_success(self, executor_env):
        """全链路: Task/Agent 校验 → Session 创建 (PENDING→RUNNING) → Loop
        编排 (Analyze→Decision→Execute) → SUCCESS; 返回 {runtime_session_id,
        status, output, execution_steps}。"""
        env = executor_env
        _make_task(env["task_store"])
        _make_agent(env["agent_registry"])

        result = env["executor"].execute_task(
            "T-101", "developer-1", context={"project_dir": str(env["project_dir"])}
        )

        assert result["runtime_session_id"].startswith("rs-")
        assert result["status"] == "success"
        output = result["output"]
        assert output["execution_output"]
        assert output["execution_summary"]
        assert output["raw_response"]
        # S10-017 Task 001: API 返回增加 execution_steps (Loop 步骤链)
        assert [s["type"] for s in result["execution_steps"]] == [
            "RECEIVE_TASK",
            "ANALYZE",
            "DECISION",
            "FINAL",
        ]

    def test_session_persisted_with_status_and_events(self, executor_env):
        """Session 落库: status=success + 事件链保序 (agent_started →
        task_received → thinking_started → decision_created → llm_request_sent
        → llm_response_received → output_generated → execution_completed)。"""
        env = executor_env
        _make_task(env["task_store"])
        _make_agent(env["agent_registry"])

        result = env["executor"].execute_task(
            "T-101", "developer-1", context={"project_dir": str(env["project_dir"])}
        )
        session = env["session_store"].get(result["runtime_session_id"])
        assert session is not None
        assert session.status.value == "success"
        assert session.started_at is not None
        assert session.finished_at is not None
        assert [e.type.value for e in session.events] == [
            "agent_started",
            "task_received",
            "thinking_started",
            "decision_created",
            "llm_request_sent",
            "llm_response_received",
            "output_generated",
            "execution_completed",
        ]

    def test_llm_called_through_reused_runtime(self, executor_env):
        """LLM 调用复用 Provider: LLMPlanner (Reason) + AgentRuntime.execute
        (Act — 旧流程 Task→LLM→Result); FakeProvider.generate 被真实调用。"""
        env = executor_env
        _make_task(env["task_store"])
        _make_agent(env["agent_registry"])

        env["executor"].execute_task(
            "T-101", "developer-1", context={"project_dir": str(env["project_dir"])}
        )
        # 2 次调用: ① LLMPlanner 决策分析 ② runtime 执行 (Developer 工作)
        assert len(env["provider"].calls) == 2
        runtime_call = env["provider"].calls[-1]
        assert "fix the sub bug" in runtime_call.task_context

    def test_output_preserved_in_session(self, executor_env):
        """Output 保留: execution_output/execution_summary/raw_response 在
        Session 模型上持久化 (可跨重启查询)。"""
        env = executor_env
        _make_task(env["task_store"])
        _make_agent(env["agent_registry"])

        result = env["executor"].execute_task(
            "T-101", "developer-1", context={"project_dir": str(env["project_dir"])}
        )
        session = env["session_store"].get(result["runtime_session_id"])
        assert session.execution_output
        assert session.execution_summary
        assert session.raw_response

    def test_output_persisted_across_store_recreation(self, executor_env, tmp_path: Path):
        """持久化铁律: 重建 store (同数据目录) 后 session/output/事件仍可查。"""
        env = executor_env
        _make_task(env["task_store"])
        _make_agent(env["agent_registry"])

        result = env["executor"].execute_task(
            "T-101", "developer-1", context={"project_dir": str(env["project_dir"])}
        )
        reopened = RuntimeSessionStore(env["root"] / "runtime-sessions")
        loaded = reopened.get(result["runtime_session_id"])
        assert loaded is not None
        assert loaded.status.value == "success"
        assert loaded.execution_output
        assert len(loaded.events) == 8

    def test_event_data_carries_context(self, executor_env):
        """agent_started 事件带 data (agent/task 锚点); output_generated 事件
        带 data (输出摘要) — 时间线可追溯。"""
        env = executor_env
        _make_task(env["task_store"])
        _make_agent(env["agent_registry"])

        result = env["executor"].execute_task(
            "T-101", "developer-1", context={"project_dir": str(env["project_dir"])}
        )
        session = env["session_store"].get(result["runtime_session_id"])
        started = session.events[0]
        assert started.type == RuntimeEventType.AGENT_STARTED
        assert started.data is not None
        assert started.data["agent_id"] == "developer-1"
        assert started.data["task_id"] == "T-101"
        output_ev = session.events[6]
        assert output_ev.type == RuntimeEventType.OUTPUT_GENERATED
        assert output_ev.data is not None
        assert "summary" in output_ev.data


# ------------------------------------------------------------------ Failure Case


class TestAgentExecutorFailure:
    def test_llm_provider_error_marks_session_failed(self, executor_env, tmp_path: Path):
        """LLM Provider 错误 → FAILED 状态 + execution_failed 事件 + 错误信息
        进事件 data (不静默)。"""
        env = executor_env
        _make_task(env["task_store"])
        _make_agent(env["agent_registry"])
        # 替换 runtime 为「Provider 返回错误」的真实 AgentRuntime
        failing_provider = FakeProvider(error="anthropic api key missing: demo")
        failing_runtime = _make_runtime(
            failing_provider, root=tmp_path / "f2", project_dir=env["project_dir"]
        )
        executor = AgentExecutor(
            task_store=env["task_store"],
            agent_registry=env["agent_registry"],
            session_store=env["session_store"],
            runtime=failing_runtime,
        )

        result = executor.execute_task(
            "T-101", "developer-1", context={"project_dir": str(env["project_dir"])}
        )

        assert result["status"] == "failed"
        session = env["session_store"].get(result["runtime_session_id"])
        assert session.status.value == "failed"
        # 事件链: agent_started → task_received → thinking_started →
        # decision_created → llm_request_sent → llm_response_received →
        # execution_failed (Provider 失败无输出生成)
        types = [e.type.value for e in session.events]
        assert types == [
            "agent_started",
            "task_received",
            "thinking_started",
            "decision_created",
            "llm_request_sent",
            "llm_response_received",
            "execution_failed",
        ]
        failed_ev = session.events[-1]
        assert failed_ev.data is not None
        assert "error" in failed_ev.data
        # Output 保留失败原因 (不静默)
        assert session.execution_output
        assert session.raw_response

    def test_runtime_unexpected_exception_marks_failed(self, executor_env):
        """runtime.execute 抛意外异常 → FAILED session + execution_failed 事件
        (编排层兜底, 不抛裸异常)。"""
        env = executor_env
        _make_task(env["task_store"])
        _make_agent(env["agent_registry"])
        broken_runtime = _ExplodingRuntime()
        executor = AgentExecutor(
            task_store=env["task_store"],
            agent_registry=env["agent_registry"],
            session_store=env["session_store"],
            runtime=broken_runtime,
        )

        result = executor.execute_task(
            "T-101", "developer-1", context={"project_dir": str(env["project_dir"])}
        )

        assert result["status"] == "failed"
        session = env["session_store"].get(result["runtime_session_id"])
        assert session.status.value == "failed"
        assert session.events[-1].type == RuntimeEventType.EXECUTION_FAILED
        assert "boom" in (session.events[-1].data or {}).get("error", "")

    def test_no_provider_honest_failed(self, executor_env):
        """无 Provider (runtime=None) → 诚实 FAILED session + 事件
        (Provider Adapter Interface — 不伪造 LLM 结果)。"""
        env = executor_env
        _make_task(env["task_store"])
        _make_agent(env["agent_registry"])
        executor = AgentExecutor(
            task_store=env["task_store"],
            agent_registry=env["agent_registry"],
            session_store=env["session_store"],
            runtime=None,
        )

        result = executor.execute_task(
            "T-101", "developer-1", context={"project_dir": str(env["project_dir"])}
        )

        assert result["status"] == "failed"
        session = env["session_store"].get(result["runtime_session_id"])
        assert session.status.value == "failed"
        assert session.events[-1].type == RuntimeEventType.EXECUTION_FAILED
        assert "provider" in (session.events[-1].data or {}).get("error", "").lower()


# ------------------------------------------------------------------ 错误处理


class TestAgentExecutorErrors:
    def test_task_not_found_raises(self, executor_env):
        """Invalid Task → TaskNotFoundError (HTTP 层 400 — 不创建 Session)。"""
        env = executor_env
        _make_agent(env["agent_registry"])
        with pytest.raises(TaskNotFoundError):
            env["executor"].execute_task("T-nope", "developer-1")

    def test_agent_not_found_raises(self, executor_env):
        """Agent Not Found → AgentNotFoundError (HTTP 层 400)。"""
        env = executor_env
        _make_task(env["task_store"])
        with pytest.raises(AgentNotFoundError):
            env["executor"].execute_task("T-101", "no-such-agent")

    def test_invalid_task_and_agent_no_session_leaked(self, executor_env):
        """校验失败不泄漏 Session (Task/Agent 不存在 → 无 rs-* 记录)。"""
        env = executor_env
        with pytest.raises(TaskNotFoundError):
            env["executor"].execute_task("T-nope", "ghost")
        assert env["session_store"].count() == 0


class _ExplodingRuntime:
    """抛意外异常的假 runtime (编排层兜底测试 — 非 Provider 行为)。"""

    def execute(self, request: ExecutionRequest, employee=None, agent_instance=None):
        raise RuntimeError("boom: unexpected executor failure")
