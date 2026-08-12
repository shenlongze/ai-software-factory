"""tests/exec/test_exec_execution_loop.py — S10-017 Task 001 Agent Execution Loop 测试。

覆盖 (Agent Execution Loop Foundation — 执行循环基础):
- Loop 生命周期: CREATED→RUNNING→WAITING_DECISION|WAITING_ACTION→…→
  COMPLETED|FAILED (run 全链: FINAL 单轮 = 旧流程 Task→LLM→Result)
- 状态转换: 合法链全记录进 Session (事件+步骤, 不静默); 非法转换 →
  ExecutionLoopError (响亮)
- AgentStep 序列: RECEIVE_TASK→ANALYZE→DECISION→(ACTION→OBSERVATION)→FINAL
  保序 + step_number 递增 + 内嵌 session.steps
- Planner: LLMPlanner 复用 ProviderInterface (DECISION 标记/JSON 解析;
  无 Provider / Provider 错误 / 解析失败 → 诚实 FINAL 单轮回退, 不伪造)
- Action Boundary: MockActionExecutor ({type: "noop"} → SUCCEEDED;
  未知 action → FAILED — 为 Tool/MCP/Skill 预留)
- Event Chain: 6 新事件 (thinking_started/decision_created/action_requested/
  observation_received/execution_completed + execution_failed 失败路径)
- 执行: FINAL → 复用 runtime.execute (旧流程); runtime None → 诚实 FAILED

basename 全仓库唯一 (test_exec_* 前缀); 依赖 tests/exec/conftest.py 的 sys.path
(factory-exec 挂载, `exec` 包导入); FakeProvider/write_files 来自 exec_helpers。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from exec.agent_runtime import AgentRuntime
from exec.execution_loop import (
    ACTION_REQUIRED,
    FINAL,
    ActionResult,
    ActionResultStatus,
    AgentExecutionLoop,
    Decision,
    DecisionType,
    ExecutionLoopError,
    ExecutionState,
    LLMPlanner,
    MockActionExecutor,
)
from exec.models import ExecutionRequest
from exec.runtime_session import (
    AgentStepType,
    RuntimeEventType,
    RuntimeSession,
    RuntimeSessionStatus,
    RuntimeSessionStore,
    new_session_id,
)
from exec_helpers import FakeProvider, write_files  # noqa: E402  (tests/exec/)

#: FakeProvider 成功 content: <patch>NO_CHANGE</patch> — 合法「无修改」交付
#: (DeveloperAgent 空补丁 → 验证通过 → SUCCESS; 不伪造真实 LLM 结果)。
NO_CHANGE_PATCH = "<patch>NO_CHANGE</patch>"

MINI_PROJECT = {
    "calc.py": "def add(a, b):\n    return a + b\n",
    # S10-018: 连续两轮工具测试 (test_tool_then_tool_multiple_rounds) 第二轮
    # 读取 README.md — 沙箱工作区须包含该文件 (工具轮成对收敛 → COMPLETED)。
    "README.md": "# demo project\n",
}


def _task_store(root: Path):
    from tasks.store import TaskStore

    return TaskStore(root / "tasks")


def _agent_registry(root: Path):
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


def _make_runtime(provider, *, root: Path, project_dir: Path) -> AgentRuntime:
    """真实 AgentRuntime (复用执行引擎 — 沙箱副本 + Developer + 验证循环)。"""
    work_root = root / "work"
    work_root.mkdir(parents=True, exist_ok=True)
    return AgentRuntime(provider, work_root=work_root, validation_command=None)


@pytest.fixture
def loop_env(tmp_path: Path):
    """最小装配: 真实 TaskStore/AgentRegistry/RuntimeSessionStore + FakeProvider。"""
    root = tmp_path / "factory"
    task_store = _task_store(root)
    agent_registry = _agent_registry(root)
    session_store = RuntimeSessionStore(root / "runtime-sessions")
    project_dir = tmp_path / "project"
    write_files(project_dir, MINI_PROJECT)
    provider = FakeProvider(content=NO_CHANGE_PATCH, usage={"input_tokens": 10, "output_tokens": 5})
    runtime = _make_runtime(provider, root=root, project_dir=project_dir)
    return {
        "root": root,
        "task_store": task_store,
        "agent_registry": agent_registry,
        "session_store": session_store,
        "project_dir": project_dir,
        "provider": provider,
        "runtime": runtime,
    }


def _running_session(env, *, agent_id="developer-1", task_id="T-101") -> RuntimeSession:
    """PENDING → RUNNING 的 session (执行器 start 语义; 交给 Loop 编排)。"""
    session = RuntimeSession(
        session_id=new_session_id(),
        agent_id=agent_id,
        task_id=task_id,
        workflow_id="dev",
    )
    env["session_store"].save(session)
    started = session.start()
    env["session_store"].save(started)
    return started


def _loop(env, session, *, planner=None, action_executor=None, runtime=None, tool_executor=None):
    return AgentExecutionLoop(
        session=session,
        session_store=env["session_store"],
        planner=planner,
        action_executor=action_executor,
        runtime=env["runtime"] if runtime is None else runtime,
        tool_executor=tool_executor,
    )


class _StubPlanner:
    """固定决策序列的假 Planner (循环测试注入 — 非 Provider 行为)。"""

    def __init__(self, *decisions: Decision) -> None:
        self._decisions = list(decisions)
        self.calls = 0

    def plan(self, task, context) -> Decision:
        self.calls += 1
        if not self._decisions:
            return Decision(type=FINAL)
        return self._decisions.pop(0)


class _ExplodingPlanner:
    """抛意外异常的假 Planner (编排层兜底测试)。"""

    def plan(self, task, context) -> Decision:
        raise RuntimeError("boom: planner failure")


class _FakeTask:
    """Planner 单元测试用的最小 Task duck (id/title/project/type/workflow)。"""

    id = "T-101"
    title = "fix the sub bug"
    project = "demo"
    type = "feature"
    workflow = "dev"


# ------------------------------------------------------------------ 生命周期


class TestExecutionLoopLifecycle:
    def test_created_to_completed_single_round(self, loop_env):
        """FINAL 单轮: CREATED→RUNNING→WAITING_DECISION→RUNNING→COMPLETED;
        session SUCCESS (等价旧流程 Task→LLM→Result)。"""
        env = loop_env
        task = _make_task(env["task_store"])
        agent = _make_agent(env["agent_registry"])
        session = _running_session(env)
        loop = _loop(env, session)

        result = loop.run(task, agent, context={"project_dir": str(env["project_dir"])})

        assert loop.state == ExecutionState.COMPLETED
        assert result["status"] == "success"
        loaded = env["session_store"].get(result["runtime_session_id"])
        assert loaded.status == RuntimeSessionStatus.SUCCESS
        assert loaded.execution_output
        assert loaded.execution_summary
        # execution_steps 保序: RECEIVE_TASK → ANALYZE → DECISION → FINAL
        assert [s["type"] for s in result["execution_steps"]] == [
            "RECEIVE_TASK",
            "ANALYZE",
            "DECISION",
            "FINAL",
        ]

    def test_created_to_failed_no_runtime_honest(self, loop_env):
        """无 runtime (无 Provider) → 诚实 FAILED: 状态 FAILED + session failed
        + 错误进事件 (不伪造 LLM 结果)。"""
        env = loop_env
        task = _make_task(env["task_store"])
        agent = _make_agent(env["agent_registry"])
        session = _running_session(env)
        loop = _loop(env, session, runtime=None)

        result = loop.run(task, agent)

        assert loop.state == ExecutionState.FAILED
        assert result["status"] == "failed"
        loaded = env["session_store"].get(result["runtime_session_id"])
        assert loaded.status == RuntimeSessionStatus.FAILED
        assert loaded.events[-1].type == RuntimeEventType.EXECUTION_FAILED
        assert "provider" in (loaded.events[-1].data or {}).get("error", "").lower()

    def test_action_required_round_continues_to_completed(self, loop_env):
        """ACTION_REQUIRED → WAITING_ACTION → noop action → OBSERVATION →
        下一轮 ANALYZE → FINAL → COMPLETED (Continue/Complete 循环)。"""
        env = loop_env
        task = _make_task(env["task_store"])
        agent = _make_agent(env["agent_registry"])
        session = _running_session(env)
        planner = _StubPlanner(
            Decision(
                type=ACTION_REQUIRED,
                reason="需要执行动作",
                payload={"action": {"type": "noop"}},
            ),
            Decision(type=FINAL, reason="任务完成"),
        )
        loop = _loop(env, session, planner=planner)

        result = loop.run(task, agent, context={"project_dir": str(env["project_dir"])})

        assert planner.calls == 2
        assert loop.state == ExecutionState.COMPLETED
        assert result["status"] == "success"
        loaded = env["session_store"].get(result["runtime_session_id"])
        types = [e.type.value for e in loaded.events]
        assert "action_requested" in types
        assert "observation_received" in types
        # 步骤序列: RECEIVE_TASK → ANALYZE → DECISION → ACTION → OBSERVATION
        # → ANALYZE → DECISION → FINAL
        assert [s["type"] for s in result["execution_steps"]] == [
            "RECEIVE_TASK",
            "ANALYZE",
            "DECISION",
            "ACTION",
            "OBSERVATION",
            "ANALYZE",
            "DECISION",
            "FINAL",
        ]

    def test_action_required_loop_not_converging_fails_honestly(self, loop_env):
        """循环不收敛 (每轮都 ACTION_REQUIRED) → 超轮次上限 → 诚实 FAILED
        (禁无限循环)。"""
        env = loop_env
        task = _make_task(env["task_store"])
        agent = _make_agent(env["agent_registry"])
        session = _running_session(env)
        planner = _StubPlanner(
            Decision(type=ACTION_REQUIRED, reason="又要动作"),
            Decision(type=ACTION_REQUIRED, reason="还要动作"),
            Decision(type=ACTION_REQUIRED, reason="永远动作"),
            Decision(type=ACTION_REQUIRED, reason="继续动作"),
        )
        loop = _loop(env, session, planner=planner)

        result = loop.run(task, agent)

        assert loop.state == ExecutionState.FAILED
        assert result["status"] == "failed"
        loaded = env["session_store"].get(result["runtime_session_id"])
        assert "round" in (loaded.events[-1].data or {}).get("error", "").lower()

    def test_planner_exception_fails_safely(self, loop_env):
        """planner 抛意外异常 → 诚实 FAILED (编排层兜底, 不抛裸异常)。"""
        env = loop_env
        task = _make_task(env["task_store"])
        agent = _make_agent(env["agent_registry"])
        session = _running_session(env)
        loop = _loop(env, session, planner=_ExplodingPlanner())

        result = loop.run(task, agent)

        assert loop.state == ExecutionState.FAILED
        assert result["status"] == "failed"
        loaded = env["session_store"].get(result["runtime_session_id"])
        assert loaded.events[-1].type == RuntimeEventType.EXECUTION_FAILED
        assert "planner" in (loaded.events[-1].data or {}).get("error", "").lower()

    def test_runtime_execution_failure_fails_loop(self, loop_env, tmp_path: Path):
        """runtime.execute 返回 failed → 事件 execution_failed + loop FAILED
        (错误进事件不静默)。"""
        env = loop_env
        task = _make_task(env["task_store"])
        agent = _make_agent(env["agent_registry"])
        session = _running_session(env)
        failing_provider = FakeProvider(error="anthropic api key missing: demo")
        failing_runtime = _make_runtime(
            failing_provider, root=tmp_path / "f2", project_dir=env["project_dir"]
        )
        loop = _loop(env, session, runtime=failing_runtime)

        result = loop.run(
            task, agent, context={"project_dir": str(env["project_dir"])}
        )

        assert loop.state == ExecutionState.FAILED
        assert result["status"] == "failed"
        loaded = env["session_store"].get(result["runtime_session_id"])
        assert loaded.events[-1].type == RuntimeEventType.EXECUTION_FAILED
        assert "api key missing" in (loaded.events[-1].data or {}).get("error", "")


# ------------------------------------------------------------------ 状态转换


class TestExecutionLoopStateTransitions:
    def test_illegal_transition_raises(self, loop_env):
        """非法转换 (CREATED→COMPLETED / RUNNING→CREATED) → ExecutionLoopError
        (响亮, 不静默)。"""
        env = loop_env
        session = _running_session(env)
        loop = _loop(env, session)
        with pytest.raises(ExecutionLoopError):
            loop.transition(ExecutionState.COMPLETED)
        with pytest.raises(ExecutionLoopError):
            loop.transition(ExecutionState.CREATED)

    def test_terminal_state_frozen(self, loop_env):
        """终态冻结: COMPLETED 后任何转换 → ExecutionLoopError。"""
        env = loop_env
        task = _make_task(env["task_store"])
        agent = _make_agent(env["agent_registry"])
        session = _running_session(env)
        loop = _loop(env, session)
        loop.run(task, agent, context={"project_dir": str(env["project_dir"])})
        assert loop.state == ExecutionState.COMPLETED
        with pytest.raises(ExecutionLoopError):
            loop.transition(ExecutionState.RUNNING)

    def test_state_changes_recorded_in_session_not_silent(self, loop_env):
        """状态变化不静默: run 后 session 事件链完整记录每一阶段
        (agent_started/task_received/thinking_started/decision_created/…)。"""
        env = loop_env
        task = _make_task(env["task_store"])
        agent = _make_agent(env["agent_registry"])
        session = _running_session(env)
        loop = _loop(env, session)
        result = loop.run(task, agent, context={"project_dir": str(env["project_dir"])})
        loaded = env["session_store"].get(result["runtime_session_id"])
        assert [e.type.value for e in loaded.events] == [
            "agent_started",
            "task_received",
            "thinking_started",
            "decision_created",
            "llm_request_sent",
            "llm_response_received",
            "output_generated",
            "execution_completed",
        ]


# ------------------------------------------------------------------ Event Chain (6 新事件)


class TestExecutionLoopEventChain:
    def test_six_new_events_emitted_in_order(self, loop_env):
        """6 新事件: thinking_started/decision_created/action_requested/
        observation_received 在过程中, execution_completed 为成功终态事件。"""
        env = loop_env
        task = _make_task(env["task_store"])
        agent = _make_agent(env["agent_registry"])
        session = _running_session(env)
        planner = _StubPlanner(
            Decision(type=ACTION_REQUIRED, reason="动作", payload={"action": {"type": "noop"}}),
            Decision(type=FINAL, reason="完成"),
        )
        loop = _loop(env, session, planner=planner)
        result = loop.run(task, agent, context={"project_dir": str(env["project_dir"])})
        loaded = env["session_store"].get(result["runtime_session_id"])
        types = [e.type.value for e in loaded.events]
        assert types == [
            "agent_started",
            "task_received",
            "thinking_started",
            "decision_created",
            "action_requested",
            "observation_received",
            "thinking_started",
            "decision_created",
            "llm_request_sent",
            "llm_response_received",
            "output_generated",
            "execution_completed",
        ]

    def test_decision_created_event_carries_decision(self, loop_env):
        """decision_created 事件带 data (type/reason — 决策可审计)。"""
        env = loop_env
        task = _make_task(env["task_store"])
        agent = _make_agent(env["agent_registry"])
        session = _running_session(env)
        loop = _loop(env, session)
        result = loop.run(task, agent)
        loaded = env["session_store"].get(result["runtime_session_id"])
        decision_ev = next(
            e for e in loaded.events if e.type == RuntimeEventType.DECISION_CREATED
        )
        assert decision_ev.data is not None
        assert decision_ev.data["type"] == "FINAL"
        assert "reason" in decision_ev.data

    def test_no_provider_chain_still_records_thinking_and_decision(self, loop_env):
        """无 LLM key → 诚实 FAILED — 事件链仍完整记录 thinking_started/
        decision_created (不静默, 不伪造)。"""
        env = loop_env
        task = _make_task(env["task_store"])
        agent = _make_agent(env["agent_registry"])
        session = _running_session(env)
        loop = _loop(env, session, runtime=None)
        result = loop.run(task, agent)
        loaded = env["session_store"].get(result["runtime_session_id"])
        assert [e.type.value for e in loaded.events] == [
            "agent_started",
            "task_received",
            "thinking_started",
            "decision_created",
            "execution_failed",
        ]


# ------------------------------------------------------------------ Planner


class TestLLMPlanner:
    def test_no_provider_honest_final(self):
        """无 Provider → 诚实 FINAL 单轮回退 (不伪造决策)。"""
        planner = LLMPlanner(provider=None)
        decision = planner.plan(_FakeTask(), None)
        assert decision.type == DecisionType.FINAL
        assert "provider" in decision.reason.lower()

    def test_parses_decision_marker(self):
        """LLM 响应含 DECISION: FINAL 标记 → FINAL 决策。"""
        provider = FakeProvider(content="DECISION: FINAL\n理由: 任务已明确")
        decision = LLMPlanner(provider=provider).plan(_FakeTask(), None)
        assert decision.type == DecisionType.FINAL

    def test_parses_action_required_marker(self):
        """LLM 响应含 DECISION: ACTION_REQUIRED → ACTION_REQUIRED 决策。"""
        provider = FakeProvider(content="DECISION: ACTION_REQUIRED\n需要工具")
        decision = LLMPlanner(provider=provider).plan(_FakeTask(), None)
        assert decision.type == DecisionType.ACTION_REQUIRED

    def test_parses_json_decision_with_payload(self):
        """JSON 决策 {decision, reason, payload} → 结构化 Decision (payload 保留)。"""
        provider = FakeProvider(
            content='{"decision": "ACTION_REQUIRED", "reason": "需要执行动作", '
            '"payload": {"action": {"type": "noop"}}}'
        )
        decision = LLMPlanner(provider=provider).plan(_FakeTask(), None)
        assert decision.type == DecisionType.ACTION_REQUIRED
        assert decision.reason == "需要执行动作"
        assert decision.payload == {"action": {"type": "noop"}}

    def test_unparseable_content_honest_final_fallback(self):
        """无法识别决策格式 → 诚实 FINAL 单轮回退 (reason 说明)。"""
        provider = FakeProvider(content="<patch>NO_CHANGE</patch>")
        decision = LLMPlanner(provider=provider).plan(_FakeTask(), None)
        assert decision.type == DecisionType.FINAL
        assert decision.reason

    def test_provider_error_honest_final_fallback(self):
        """Provider 返回 error → 诚实 FINAL 单轮回退 (错误原因进 reason)。"""
        provider = FakeProvider(error="anthropic api key missing: demo")
        decision = LLMPlanner(provider=provider).plan(_FakeTask(), None)
        assert decision.type == DecisionType.FINAL
        assert "api key missing" in decision.reason

    def test_planner_builds_task_context_for_provider(self, loop_env):
        """LLMPlanner 组装 Task Context (任务/项目/工作流阶段) 发给 Provider
        (复用 ProviderInterface — 不绑 OpenAI)。"""
        env = loop_env
        task = _make_task(env["task_store"])
        planner = LLMPlanner(provider=env["provider"])
        planner.plan(task, {"requirement": "必须通过测试"})
        sent = env["provider"].calls[-1]
        assert "fix the sub bug" in sent.task_context
        assert "必须通过测试" in sent.task_context


# ------------------------------------------------------------------ Action Boundary


class TestMockActionExecutor:
    def test_noop_action_succeeds(self):
        """{type: "noop"} → ActionResult SUCCEEDED (为 Tool/MCP/Skill 预留边界)。"""
        result = MockActionExecutor().execute({"type": "noop"})
        assert result.status == ActionResultStatus.SUCCEEDED
        assert result.output

    def test_unknown_action_fails(self):
        """未知 action → ActionResult FAILED (响亮, 不假装成功)。"""
        result = MockActionExecutor().execute({"type": "shell"})
        assert result.status == ActionResultStatus.FAILED
        assert result.error

    def test_missing_type_fails(self):
        """缺 type 字段 → ActionResult FAILED。"""
        result = MockActionExecutor().execute({})
        assert result.status == ActionResultStatus.FAILED


# ------------------------------------------------------------------ AgentStep 序列


class TestExecutionLoopSteps:
    def test_steps_recorded_into_session(self, loop_env):
        """run 后 session.steps 保序 + step_number 递增 + 类型正确 (状态变化
        进 Session 不静默)。"""
        env = loop_env
        task = _make_task(env["task_store"])
        agent = _make_agent(env["agent_registry"])
        session = _running_session(env)
        loop = _loop(env, session)
        result = loop.run(task, agent, context={"project_dir": str(env["project_dir"])})
        loaded = env["session_store"].get(result["runtime_session_id"])
        assert [s.step_type for s in loaded.steps] == [
            AgentStepType.RECEIVE_TASK,
            AgentStepType.ANALYZE,
            AgentStepType.DECISION,
            AgentStepType.FINAL,
        ]
        assert [s.step_number for s in loaded.steps] == [1, 2, 3, 4]
        assert all(s.session_id == loaded.session_id for s in loaded.steps)
        # DECISION 步骤 output 携带决策 (type/reason)
        assert loaded.steps[2].output["type"] == "FINAL"


# ------------------------------------------------------------------ 执行 (旧流程复用)


class TestExecutionLoopExecution:
    def test_final_reuses_runtime_execute(self, loop_env):
        """FINAL → 复用 runtime.execute (Task→LLM→Result 旧流程仍在);
        Provider 被 planner 与 runtime 各调用一次 (Reason→Act)。"""
        env = loop_env
        task = _make_task(env["task_store"])
        agent = _make_agent(env["agent_registry"])
        session = _running_session(env)
        loop = _loop(env, session)
        loop.run(task, agent, context={"project_dir": str(env["project_dir"])})
        assert len(env["provider"].calls) == 2
        # 最后一次调用是 runtime 执行 (Developer 提示含任务目标)
        runtime_call = env["provider"].calls[-1]
        assert "fix the sub bug" in runtime_call.task_context

    def test_output_preserved_on_completed(self, loop_env):
        """COMPLETED: execution_output/execution_summary/raw_response 落
        Session (可跨重启查询)。"""
        env = loop_env
        task = _make_task(env["task_store"])
        agent = _make_agent(env["agent_registry"])
        session = _running_session(env)
        loop = _loop(env, session)
        result = loop.run(task, agent, context={"project_dir": str(env["project_dir"])})
        loaded = env["session_store"].get(result["runtime_session_id"])
        assert loaded.execution_output
        assert loaded.execution_summary
        assert loaded.raw_response
        assert loaded.finished_at is not None

    def test_final_step_output_carries_summary(self, loop_env):
        """FINAL 步骤 output 带执行摘要 (execution_steps 可展示结果)。"""
        env = loop_env
        task = _make_task(env["task_store"])
        agent = _make_agent(env["agent_registry"])
        session = _running_session(env)
        loop = _loop(env, session)
        result = loop.run(task, agent, context={"project_dir": str(env["project_dir"])})
        final_step = result["execution_steps"][-1]
        assert final_step["type"] == "FINAL"
        assert final_step["status"] == "succeeded"
        assert "output" in final_step


# ------------------------------------------------------------------ S10-018 Task 001: Tool 集成

#: 工具轮完整事件链 (约束 7 九事件链 — 决策→工具→观察→继续):
#: agent_started → task_received → thinking_started → decision_created →
#: tool_requested → tool_started → tool_completed → observation_received
TOOL_ROUND_CHAIN = [
    "agent_started",
    "task_received",
    "thinking_started",
    "decision_created",
    "tool_requested",
    "tool_started",
    "tool_completed",
    "observation_received",
]


def _tool_action(tool_id: str, tool_input: dict) -> dict:
    """Tool Action payload (决策 payload.action — 约束 6: {type, tool_id, input})。"""
    return {"type": "tool", "tool_id": tool_id, "input": tool_input}


def _real_tool_executor(workspace_root: Path):
    """真实 ToolExecutor: 系统 Tool (filesystem.read) + workspace 沙箱根。"""
    from exec.tool import ToolExecutor, ToolRegistry

    return ToolExecutor(ToolRegistry.with_system_tools(), workspace_root=workspace_root)


class TestExecutionLoopToolIntegration:
    def test_tool_action_full_chain_completed(self, loop_env):
        """ACTION_REQUIRED(tool) → tool_requested→tool_started→tool_completed→
        observation_received → 下一轮 FINAL → COMPLETED; 工具轮九事件链保序
        (agent_started→…→tool_requested→tool_started→tool_completed→
        observation_received) + observation 含工具输出 (Observation 边界)。"""
        env = loop_env
        task = _make_task(env["task_store"])
        agent = _make_agent(env["agent_registry"], agent_id="backend-1", name="Backend")
        session = _running_session(env, agent_id="backend-1")
        planner = _StubPlanner(
            Decision(
                type=ACTION_REQUIRED,
                reason="需要读取文件",
                payload={"action": _tool_action("filesystem.read", {"path": "calc.py"})},
            ),
            Decision(type=FINAL, reason="任务完成"),
        )
        loop = _loop(
            env, session, planner=planner, tool_executor=_real_tool_executor(env["project_dir"])
        )

        result = loop.run(task, agent, context={"project_dir": str(env["project_dir"])})

        assert loop.state == ExecutionState.COMPLETED
        assert result["status"] == "success"
        loaded = env["session_store"].get(result["runtime_session_id"])
        types = [e.type.value for e in loaded.events]
        # 九事件链前缀保序 (工具轮: 决策→工具请求→工具开始→工具完成→观察)
        assert types[:8] == TOOL_ROUND_CHAIN
        # 工具事件顺序: requested → started → completed (无 failed)
        assert [t for t in types if t.startswith("tool_")] == [
            "tool_requested",
            "tool_started",
            "tool_completed",
        ]
        # Observation 边界: 工具输出进观察载荷 (Decision→Tool→Result→Observation)
        obs = [e for e in loaded.events if e.type.value == "observation_received"][0]
        assert obs.data["status"] == "succeeded"
        assert "def add" in (obs.data.get("output") or {}).get("content", "")
        # 步骤序列含 ACTION + OBSERVATION (工具执行步骤记录)
        assert [s["type"] for s in result["execution_steps"]] == [
            "RECEIVE_TASK",
            "ANALYZE",
            "DECISION",
            "ACTION",
            "OBSERVATION",
            "ANALYZE",
            "DECISION",
            "FINAL",
        ]

    def test_tool_then_tool_multiple_rounds(self, loop_env):
        """连续两轮工具 (工具→观察→再工具→观察→FINAL): 每轮工具事件成对,
        循环收敛 → COMPLETED (Continue 语义)。"""
        env = loop_env
        task = _make_task(env["task_store"])
        agent = _make_agent(env["agent_registry"], agent_id="backend-1", name="Backend")
        session = _running_session(env, agent_id="backend-1")
        planner = _StubPlanner(
            Decision(type=ACTION_REQUIRED, payload={"action": _tool_action("filesystem.read", {"path": "calc.py"})}),
            Decision(type=ACTION_REQUIRED, payload={"action": _tool_action("filesystem.read", {"path": "README.md"})}),
            Decision(type=FINAL, reason="任务完成"),
        )
        loop = _loop(
            env, session, planner=planner, tool_executor=_real_tool_executor(env["project_dir"])
        )

        result = loop.run(task, agent, context={"project_dir": str(env["project_dir"])})

        assert result["status"] == "success"
        loaded = env["session_store"].get(result["runtime_session_id"])
        types = [e.type.value for e in loaded.events]
        assert types.count("tool_completed") == 2
        assert types.count("observation_received") == 2
        assert types[-1] == "execution_completed"

    def test_tool_failed_ends_execution_failed(self, loop_env):
        """工具执行失败 (文件不存在) → tool_failed 事件 → execution_failed →
        loop FAILED (诚实 — 失败→tool_failed→execution_failed, 不假装成功)。"""
        env = loop_env
        task = _make_task(env["task_store"])
        agent = _make_agent(env["agent_registry"], agent_id="backend-1", name="Backend")
        session = _running_session(env, agent_id="backend-1")
        planner = _StubPlanner(
            Decision(type=ACTION_REQUIRED, payload={"action": _tool_action("filesystem.read", {"path": "missing.txt"})}),
        )
        loop = _loop(
            env, session, planner=planner, tool_executor=_real_tool_executor(env["project_dir"])
        )

        result = loop.run(task, agent, context={"project_dir": str(env["project_dir"])})

        assert loop.state == ExecutionState.FAILED
        assert result["status"] == "failed"
        loaded = env["session_store"].get(result["runtime_session_id"])
        types = [e.type.value for e in loaded.events]
        assert "tool_failed" in types
        assert "tool_completed" not in types
        assert types[-1] == "execution_failed"
        failed = [e for e in loaded.events if e.type.value == "tool_failed"][0]
        assert "missing.txt" in (failed.data or {}).get("error", "")

    def test_tool_permission_denied_fails_honestly(self, loop_env):
        """工具权限失败 (非白名单 agent) → ToolResult.failed + tool_failed 事件
        → execution_failed (约束 8/9: backend-1 允许 filesystem.read, 其他禁止)。"""
        env = loop_env
        task = _make_task(env["task_store"])
        agent = _make_agent(env["agent_registry"], agent_id="flutter-dev", name="Flutter")
        session = _running_session(env, agent_id="flutter-dev")
        planner = _StubPlanner(
            Decision(type=ACTION_REQUIRED, payload={"action": _tool_action("filesystem.read", {"path": "calc.py"})}),
        )
        loop = _loop(
            env, session, planner=planner, tool_executor=_real_tool_executor(env["project_dir"])
        )

        result = loop.run(task, agent, context={"project_dir": str(env["project_dir"])})

        assert result["status"] == "failed"
        loaded = env["session_store"].get(result["runtime_session_id"])
        types = [e.type.value for e in loaded.events]
        assert types[-1] == "execution_failed"
        failed = [e for e in loaded.events if e.type.value == "tool_failed"][0]
        assert "permission denied" in (failed.data or {}).get("error", "")
        assert "flutter-dev" in (failed.data or {}).get("error", "")

    def test_tool_schema_invalid_fails_honestly(self, loop_env):
        """工具输入 Schema 校验失败 (缺 path) → tool_failed (invalid input) →
        execution_failed (失败明确不吞)。"""
        env = loop_env
        task = _make_task(env["task_store"])
        agent = _make_agent(env["agent_registry"], agent_id="backend-1", name="Backend")
        session = _running_session(env, agent_id="backend-1")
        planner = _StubPlanner(
            Decision(type=ACTION_REQUIRED, payload={"action": _tool_action("filesystem.read", {})}),
        )
        loop = _loop(
            env, session, planner=planner, tool_executor=_real_tool_executor(env["project_dir"])
        )

        result = loop.run(task, agent, context={"project_dir": str(env["project_dir"])})

        assert result["status"] == "failed"
        loaded = env["session_store"].get(result["runtime_session_id"])
        types = [e.type.value for e in loaded.events]
        assert types[-1] == "execution_failed"
        failed = [e for e in loaded.events if e.type.value == "tool_failed"][0]
        assert "invalid input" in (failed.data or {}).get("error", "")

    def test_tool_action_without_tool_executor_honest_failed(self, loop_env):
        """Tool Action 但 loop 未装配 tool_executor → tool_failed
        ('tool executor not configured') → execution_failed (诚实, 不假装执行)。"""
        env = loop_env
        task = _make_task(env["task_store"])
        agent = _make_agent(env["agent_registry"], agent_id="backend-1", name="Backend")
        session = _running_session(env, agent_id="backend-1")
        planner = _StubPlanner(
            Decision(type=ACTION_REQUIRED, payload={"action": _tool_action("filesystem.read", {"path": "calc.py"})}),
        )
        loop = _loop(env, session, planner=planner, tool_executor=None)

        result = loop.run(task, agent, context={"project_dir": str(env["project_dir"])})

        assert result["status"] == "failed"
        loaded = env["session_store"].get(result["runtime_session_id"])
        types = [e.type.value for e in loaded.events]
        assert types[-1] == "execution_failed"
        failed = [e for e in loaded.events if e.type.value == "tool_failed"][0]
        assert "not configured" in (failed.data or {}).get("error", "")

    def test_noop_compat_with_tool_executor_present(self, loop_env):
        """S10-017 兼容: tool_executor 已装配时 noop action 仍走旧流程
        (MockActionExecutor → observation_received; 无 tool_* 事件)。"""
        env = loop_env
        task = _make_task(env["task_store"])
        agent = _make_agent(env["agent_registry"])
        session = _running_session(env)
        planner = _StubPlanner(
            Decision(type=ACTION_REQUIRED, reason="noop", payload={"action": {"type": "noop"}}),
            Decision(type=FINAL, reason="任务完成"),
        )
        loop = _loop(
            env, session, planner=planner, tool_executor=_real_tool_executor(env["project_dir"])
        )

        result = loop.run(task, agent, context={"project_dir": str(env["project_dir"])})

        assert result["status"] == "success"
        loaded = env["session_store"].get(result["runtime_session_id"])
        types = [e.type.value for e in loaded.events]
        assert "observation_received" in types
        assert not [t for t in types if t.startswith("tool_")]
