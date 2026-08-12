"""tests/exec/test_exec_runtime_session.py — S10-016 Runtime Session Domain 测试。

覆盖 (Task 001 — AI Employee Runtime Foundation, 最小 Agent Runtime Session):
- RuntimeSession 模型: 字段默认值 (PENDING/created_at)/事件内嵌/JSON 序列化
- 状态机合法转换: PENDING→RUNNING→SUCCESS|FAILED; RUNNING→CANCELLED
- 状态机非法转换 → RuntimeSessionError (响亮, 不静默)
- append_event: 仅 RUNNING 允许 (PENDING/终态 → RuntimeSessionError);
  非法 event type → ValueError
- Store 持久化: 重启 (重建 store) 后 session/events 仍可查
- Store 损坏 → CorruptRuntimeSessionStoreError (响亮, 不静默返回空)
- 时间戳语义: start 记录 started_at / complete 记录 finished_at

basename 全仓库唯一 (test_exec_* 前缀); 依赖 tests/exec/conftest.py 的 sys.path
(factory-exec 挂载, `exec` 包导入)。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from exec.runtime_session import (
    AgentStep,
    AgentStepStatus,
    AgentStepType,
    CorruptRuntimeSessionStoreError,
    RuntimeEventType,
    RuntimeSession,
    RuntimeSessionError,
    RuntimeSessionStatus,
    RuntimeSessionStore,
    new_session_id,
    new_event_id,
    new_step_id,
)


# ------------------------------------------------------------------ 模型


class TestRuntimeSessionModel:
    def test_defaults_pending_with_timestamps(self):
        """创建时缺省: status=PENDING, created_at 非空, started_at/finished_at None,
        events 空列表 (无 None 陷阱)。"""
        session = RuntimeSession(
            session_id="rs-abc", agent_id="dev-1", task_id="T-1", workflow_id="W-1"
        )
        assert session.status == RuntimeSessionStatus.PENDING
        assert session.created_at is not None
        assert session.started_at is None
        assert session.finished_at is None
        assert session.events == []

    def test_workflow_id_optional(self):
        """workflow_id 可选 (独立执行无工作流); 缺省空串。"""
        session = RuntimeSession(
            session_id="rs-abc", agent_id="dev-1", task_id="T-1"
        )
        assert session.workflow_id == ""

    def test_status_values(self):
        """五状态枚举值 (API 契约): pending/running/success/failed/cancelled。"""
        assert {s.value for s in RuntimeSessionStatus} == {
            "pending",
            "running",
            "success",
            "failed",
            "cancelled",
        }

    def test_event_type_twenty(self):
        """RuntimeEvent 类型 (任务约束 + Task 002 + S10-017 Task 001 + S10-018
        + S10-019 + S10-020): agent_started/task_received/execution_started/tool_called/
        llm_request_sent/llm_response_received/output_generated/
        execution_finished/execution_failed + thinking_started/
        decision_created/action_requested/observation_received/
        execution_completed + tool_requested/tool_started/tool_completed/
        tool_failed + skill_loaded/skill_selected + mcp_connected/
        mcp_tool_discovered/mcp_tool_registered (9→14→18→20→23, 向后兼容;
        Skill/MCP 事件为条件触发 — 仅装配对应上下文时发出)。"""
        assert {t.value for t in RuntimeEventType} == {
            "agent_started",
            "task_received",
            "execution_started",
            "tool_called",
            "llm_request_sent",
            "llm_response_received",
            "output_generated",
            "execution_finished",
            "execution_failed",
            "thinking_started",
            "decision_created",
            "action_requested",
            "observation_received",
            "execution_completed",
            "tool_requested",
            "tool_started",
            "tool_completed",
            "tool_failed",
            "skill_loaded",
            "skill_selected",
            "mcp_connected",
            "mcp_tool_discovered",
            "mcp_tool_registered",
        }

    def test_to_dict_json_friendly(self):
        """to_dict: datetime → ISO 字符串 (JSON 落库/API 响应友好)。"""
        session = RuntimeSession(
            session_id="rs-abc", agent_id="dev-1", task_id="T-1"
        )
        payload = session.to_dict()
        assert isinstance(payload["created_at"], str)
        assert payload["events"] == []

    def test_session_id_property_aliases_id(self):
        """id property → session_id (Store 通用 save 语义兼容)。"""
        session = RuntimeSession(session_id="rs-abc", agent_id="dev-1", task_id="T-1")
        assert session.id == "rs-abc"

    def test_new_ids_unique(self):
        """id 生成: rs-/ev-/st- 前缀, 唯一 basename。"""
        assert new_session_id().startswith("rs-")
        assert new_event_id().startswith("ev-")
        assert new_step_id().startswith("st-")
        assert new_session_id() != new_session_id()
        assert new_step_id() != new_step_id()


# ------------------------------------------------------------------ 状态机


class TestRuntimeSessionStateMachine:
    def _session(self, **overrides):
        return RuntimeSession(
            session_id=overrides.pop("session_id", "rs-abc"),
            agent_id=overrides.pop("agent_id", "dev-1"),
            task_id=overrides.pop("task_id", "T-1"),
            workflow_id=overrides.pop("workflow_id", "W-1"),
            **overrides,
        )

    def test_start_pending_to_running(self):
        """PENDING → RUNNING (start): started_at 记录, 状态更新。"""
        session = self._session()
        updated = session.start()
        assert updated.status == RuntimeSessionStatus.RUNNING
        assert updated.started_at is not None
        assert updated.session_id == session.session_id

    def test_complete_running_to_success(self):
        """RUNNING → SUCCESS (complete success=True): finished_at 记录。"""
        session = self._session().start()
        updated = session.complete(success=True)
        assert updated.status == RuntimeSessionStatus.SUCCESS
        assert updated.finished_at is not None

    def test_complete_running_to_failed(self):
        """RUNNING → FAILED (complete success=False)。"""
        session = self._session().start()
        updated = session.complete(success=False)
        assert updated.status == RuntimeSessionStatus.FAILED

    def test_cancel_running_to_cancelled(self):
        """RUNNING → CANCELLED (cancel): finished_at 记录 (终态时间戳)。"""
        session = self._session().start()
        updated = session.cancel()
        assert updated.status == RuntimeSessionStatus.CANCELLED
        assert updated.finished_at is not None

    @pytest.mark.parametrize(
        "setup,action",
        [
            ("running", "start"),
            ("success", "start"),
            ("failed", "start"),
            ("cancelled", "start"),
            ("pending", "complete"),
            ("success", "complete"),
            ("failed", "complete"),
            ("cancelled", "complete"),
            ("pending", "cancel"),
            ("success", "cancel"),
            ("failed", "cancel"),
            ("cancelled", "cancel"),
        ],
    )
    def test_illegal_transitions_raise(self, setup, action):
        """非法转换全表: 只有 PENDING→start / RUNNING→complete|cancel 合法;
        其余一律 RuntimeSessionError (响亮, 不静默)。"""
        base = self._session()
        if setup == "running":
            base = base.start()
        elif setup == "success":
            base = base.start().complete(success=True)
        elif setup == "failed":
            base = base.start().complete(success=False)
        elif setup == "cancelled":
            base = base.start().cancel()
        with pytest.raises(RuntimeSessionError):
            if action == "start":
                base.start()
            elif action == "complete":
                base.complete(success=True)
            else:
                base.cancel()

    def test_complete_requires_running_after_pending(self):
        """PENDING 直接 complete → 错误 (必须先 start)。"""
        with pytest.raises(RuntimeSessionError):
            self._session().complete(success=True)

    def test_state_transition_is_immutable_copy(self):
        """状态机返回新实例, 原实例不变 (审计: 落库前可对比 previous)。"""
        session = self._session()
        started = session.start()
        assert session.status == RuntimeSessionStatus.PENDING
        assert started.status == RuntimeSessionStatus.RUNNING


# ------------------------------------------------------------------ 事件


class TestRuntimeSessionEvents:
    def _running(self):
        return RuntimeSession(
            session_id="rs-abc", agent_id="dev-1", task_id="T-1"
        ).start()

    def test_append_event_running(self):
        """RUNNING 下 append_event: 事件追加 (event_id/type/message/data/created_at)。"""
        session = self._running()
        updated, event = session.append_event(
            RuntimeEventType.TOOL_CALLED, "调用 sandbox.apply_patch", data={"patch": "x"}
        )
        assert event.event_id.startswith("ev-")
        assert event.session_id == "rs-abc"
        assert event.type == RuntimeEventType.TOOL_CALLED
        assert event.message == "调用 sandbox.apply_patch"
        assert event.data == {"patch": "x"}
        assert event.created_at is not None
        assert len(updated.events) == 1

    def test_append_event_pending_rejected(self):
        """PENDING 下 append_event → RuntimeSessionError (未开始无事件)。"""
        session = RuntimeSession(
            session_id="rs-abc", agent_id="dev-1", task_id="T-1"
        )
        with pytest.raises(RuntimeSessionError):
            session.append_event(RuntimeEventType.AGENT_STARTED, "start")

    @pytest.mark.parametrize(
        "terminal",
        ["success", "failed", "cancelled"],
    )
    def test_append_event_terminal_rejected(self, terminal):
        """终态 (SUCCESS/FAILED/CANCELLED) 下 append_event → RuntimeSessionError
        (事件链在会话结束后冻结)。"""
        session = self._running()
        if terminal == "success":
            session = session.complete(success=True)
        elif terminal == "failed":
            session = session.complete(success=False)
        else:
            session = session.cancel()
        with pytest.raises(RuntimeSessionError):
            session.append_event(RuntimeEventType.OUTPUT_GENERATED, "late")

    def test_append_event_invalid_type_raises_value_error(self):
        """未知事件类型 → ValueError (pydantic Literal 校验, 响亮)。"""
        session = self._running()
        with pytest.raises(ValueError):
            session.append_event("not_a_real_event", "boom")  # type: ignore[arg-type]

    def test_seven_event_types_lifecycle_sequence(self):
        """七类型全链序列 (Agent Started → Task Received → Execution Started →
        Tool Called → Output Generated → Execution Finished) 逐条可追加。"""
        session = self._running()
        sequence = [
            RuntimeEventType.AGENT_STARTED,
            RuntimeEventType.TASK_RECEIVED,
            RuntimeEventType.EXECUTION_STARTED,
            RuntimeEventType.TOOL_CALLED,
            RuntimeEventType.OUTPUT_GENERATED,
            RuntimeEventType.EXECUTION_FINISHED,
        ]
        for i, event_type in enumerate(sequence):
            session, _ = session.append_event(event_type, f"step {i}")
        assert [e.type for e in session.events] == sequence

    def test_events_kept_in_append_order(self):
        """事件按追加顺序保留 (时间线)。"""
        session = self._running()
        for i in range(3):
            session, _ = session.append_event(RuntimeEventType.TOOL_CALLED, f"t{i}")
        assert [e.message for e in session.events] == ["t0", "t1", "t2"]


# ------------------------------------------------------------------ AgentStep (S10-017 Task 001)


class TestAgentStep:
    """AgentStep 模型 + RuntimeSession.add_step (执行步骤记录 — S10-017)。"""

    def _running(self):
        return RuntimeSession(
            session_id="rs-abc", agent_id="dev-1", task_id="T-1"
        ).start()

    def test_step_type_values(self):
        """step_type 六类型 (RECEIVE_TASK/ANALYZE/DECISION/ACTION/OBSERVATION/FINAL)。"""
        assert {t.value for t in AgentStepType} == {
            "RECEIVE_TASK",
            "ANALYZE",
            "DECISION",
            "ACTION",
            "OBSERVATION",
            "FINAL",
        }

    def test_step_status_values(self):
        """step status 四态 (pending/running/succeeded/failed)。"""
        assert {s.value for s in AgentStepStatus} == {
            "pending",
            "running",
            "succeeded",
            "failed",
        }

    def test_add_step_running_assigns_number_and_id(self):
        """RUNNING 下 add_step: id (st-)/step_number 递增 (1,2,3)/step_type/
        input/output/status/created_at; steps 内嵌于 session (保序)。"""
        session = self._running()
        session, step1 = session.add_step(
            AgentStepType.RECEIVE_TASK, input={"task_id": "T-1"}
        )
        assert step1.id.startswith("st-")
        assert step1.session_id == "rs-abc"
        assert step1.step_number == 1
        assert step1.step_type == AgentStepType.RECEIVE_TASK
        assert step1.input == {"task_id": "T-1"}
        assert step1.output == {}
        assert step1.status == AgentStepStatus.SUCCEEDED
        assert step1.created_at is not None
        session, step2 = session.add_step(
            AgentStepType.ANALYZE, input={}, output={"note": "x"}
        )
        assert step2.step_number == 2
        assert [s.step_type for s in session.steps] == [
            AgentStepType.RECEIVE_TASK,
            AgentStepType.ANALYZE,
        ]

    def test_add_step_pending_rejected(self):
        """PENDING 下 add_step → RuntimeSessionError (未开始无步骤)。"""
        session = RuntimeSession(
            session_id="rs-abc", agent_id="dev-1", task_id="T-1"
        )
        with pytest.raises(RuntimeSessionError):
            session.add_step(AgentStepType.RECEIVE_TASK)

    @pytest.mark.parametrize(
        "terminal",
        ["success", "failed", "cancelled"],
    )
    def test_add_step_terminal_rejected(self, terminal):
        """终态下 add_step → RuntimeSessionError (步骤链冻结, 同事件链)。"""
        session = self._running()
        if terminal == "success":
            session = session.complete(success=True)
        elif terminal == "failed":
            session = session.complete(success=False)
        else:
            session = session.cancel()
        with pytest.raises(RuntimeSessionError):
            session.add_step(AgentStepType.FINAL)

    def test_add_step_invalid_type_raises_value_error(self):
        """未知 step_type → ValueError (响亮)。"""
        session = self._running()
        with pytest.raises(ValueError):
            session.add_step("NOT_A_STEP")  # type: ignore[arg-type]

    def test_step_to_dict_json_friendly(self):
        """AgentStep to_dict: datetime → ISO 字符串 (session.to_dict 含 steps)。"""
        session = self._running()
        session, _ = session.add_step(AgentStepType.RECEIVE_TASK, input={"task_id": "T-1"})
        payload = session.to_dict()
        assert len(payload["steps"]) == 1
        assert isinstance(payload["steps"][0]["created_at"], str)
        assert payload["steps"][0]["step_number"] == 1

    def test_steps_persist_across_store_recreation(self, tmp_path: Path):
        """持久化铁律: 重建 store 后 steps 仍可查 (旧数据无 steps 字段 → 空列表)。"""
        data_dir = tmp_path / "sessions"
        store = RuntimeSessionStore(data_dir)
        session = self._running()
        session, _ = session.add_step(AgentStepType.RECEIVE_TASK, input={"task_id": "T-1"})
        store.save(session)
        reopened = RuntimeSessionStore(data_dir)
        loaded = reopened.get("rs-abc")
        assert loaded is not None
        assert len(loaded.steps) == 1
        assert loaded.steps[0].step_type == AgentStepType.RECEIVE_TASK

    def test_old_session_without_steps_loads_with_empty_list(self, tmp_path: Path):
        """旧数据兼容: 无 steps 字段的已存 session 反序列化 → steps 空列表。"""
        data_dir = tmp_path / "sessions"
        store = RuntimeSessionStore(data_dir)
        store.save(RuntimeSession(session_id="rs-old", agent_id="d", task_id="T"))
        loaded = store.get("rs-old")
        assert loaded is not None
        assert loaded.steps == []


# ------------------------------------------------------------------ Store


class TestRuntimeSessionStore:
    def test_save_get_roundtrip(self, tmp_path: Path):
        """save → get: 字段/事件完整还原 (JSON 落库)。"""
        store = RuntimeSessionStore(tmp_path / "sessions")
        session = RuntimeSession(
            session_id="rs-abc", agent_id="dev-1", task_id="T-1", workflow_id="W-1"
        )
        running = session.start()
        running, _ = running.append_event(
            RuntimeEventType.AGENT_STARTED, "agent woke up"
        )
        store.save(running)
        loaded = store.get("rs-abc")
        assert loaded is not None
        assert loaded.status == RuntimeSessionStatus.RUNNING
        assert loaded.started_at is not None
        assert len(loaded.events) == 1
        assert loaded.events[0].type == RuntimeEventType.AGENT_STARTED

    def test_get_missing_returns_none(self, tmp_path: Path):
        """不存在 id → None (404 语义)。"""
        store = RuntimeSessionStore(tmp_path / "sessions")
        assert store.get("rs-nope") is None

    def test_persistence_across_store_recreation(self, tmp_path: Path):
        """重启语义: 重建 store (同目录) 后 session/事件仍可查 (持久化铁律)。"""
        data_dir = tmp_path / "sessions"
        store = RuntimeSessionStore(data_dir)
        session = (
            RuntimeSession(
                session_id="rs-abc", agent_id="dev-1", task_id="T-1"
            )
            .start()
            .complete(success=True)
        )
        store.save(session)
        # 模拟进程重启: 全新 store 实例 (同数据目录)
        reopened = RuntimeSessionStore(data_dir)
        loaded = reopened.get("rs-abc")
        assert loaded is not None
        assert loaded.status == RuntimeSessionStatus.SUCCESS
        assert loaded.finished_at is not None

    def test_list_all_sorted_by_id(self, tmp_path: Path):
        """list_all: 按 session_id 排序 (审计友好确定性)。"""
        store = RuntimeSessionStore(tmp_path / "sessions")
        for sid in ("rs-b", "rs-a", "rs-c"):
            store.save(
                RuntimeSession(session_id=sid, agent_id="dev-1", task_id="T-1")
            )
        assert [s.session_id for s in store.list_all()] == ["rs-a", "rs-b", "rs-c"]

    def test_count(self, tmp_path: Path):
        store = RuntimeSessionStore(tmp_path / "sessions")
        store.save(RuntimeSession(session_id="rs-a", agent_id="d", task_id="T"))
        assert store.count() == 1

    def test_corrupt_store_raises_loudly(self, tmp_path: Path):
        """损坏 JSON → CorruptRuntimeSessionStoreError (绝不静默返回空)。"""
        data_dir = tmp_path / "sessions"
        data_dir.mkdir(parents=True)
        (data_dir / "sessions.json").write_text("{ not json", encoding="utf-8")
        store = RuntimeSessionStore(data_dir)
        with pytest.raises(CorruptRuntimeSessionStoreError):
            store.list_all()

    def test_upsert_overwrites_by_id(self, tmp_path: Path):
        """同 id 覆盖 = 状态流转落库 (model_copy 新实例后 save)。"""
        store = RuntimeSessionStore(tmp_path / "sessions")
        store.save(RuntimeSession(session_id="rs-a", agent_id="d", task_id="T"))
        store.save(
            RuntimeSession(session_id="rs-a", agent_id="d", task_id="T").start()
        )
        assert store.count() == 1
        assert store.get("rs-a").status == RuntimeSessionStatus.RUNNING
