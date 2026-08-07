"""tests/exec/test_exec_candidate_strategy.py — Candidate Execution 集成测试 (Sprint 5 T5.2)。

覆盖 (真实 AgentRuntime 全链, mock Provider, 零 LLM 零网络):
- Feature Flag 关: 旧流程逐位不变 (单次执行 / 单 completed 事件 / 零候选)
- Feature Flag 开: N 次独立顺序执行 → 候选收集 (成功+失败混合必存) /
  临时选择 (第一个成功 / 全失败如实返回) / Run 状态记录 / 事件链每 Run 完整 /
  store 每 Run 落库 / 顺序执行禁并发 (单线程)
- 失败安全: 策略路径异常 → 回退旧流程 (执行链不破坏)

basename 唯一 (test_exec_* 前缀); helper 复用 tests/exec/exec_helpers.py。
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest

from exec.agent_runtime import AgentRuntime
from exec.candidate import CANDIDATE_REASON_EMPTY_OUTPUT, CANDIDATE_REASON_OTHER
from exec.provider import ProviderResponse
from exec_helpers import FakeProvider, git_diff_text, make_request, write_files

CALC_BEFORE = "def add(a, b):\n    return a + b\n\n"
CALC_AFTER = "def add(a, b):\n    return abs(a + b)\n\n"


def _bug_project(tmp_path: Path) -> Path:
    proj = tmp_path / "bug-project"
    write_files(proj, {"calc.py": CALC_BEFORE, "README.md": "# demo\n"})
    return proj


def _patch_content(tmp_path: Path) -> str:
    return git_diff_text(tmp_path, {"calc.py": CALC_BEFORE}, {"calc.py": CALC_AFTER})


def _ok_content(tmp_path: Path) -> str:
    return "fixed the sub bug\n<patch>\n" + _patch_content(tmp_path) + "\n</patch>"


class _SeqProvider:
    """按调用序出结果的 Provider (成功/错误可编排; 记录调用序 + 线程名)。

    steps: [(kind, payload), ...] — kind "ok" → content, "error" → error 消息。
    """

    provider_id = "mock"

    def __init__(self, steps: list[tuple[str, str]]) -> None:
        self._steps = list(steps)
        self.calls: list[Any] = []
        self.threads: list[str] = []

    def generate(self, request: Any) -> ProviderResponse:
        self.calls.append(request)
        self.threads.append(threading.current_thread().name)
        kind, payload = self._steps.pop(0)
        if kind == "error":
            return ProviderResponse(content="", error=payload)
        return ProviderResponse(
            content=payload,
            usage={"input_tokens": 10, "estimated_cost_usd": 0.01},
        )


def _runtime(
    provider: Any,
    store: Any,
    logger: Any,
    *,
    execution_strategy_enabled: bool = False,
    execution_strategy_runs: int = 3,
) -> AgentRuntime:
    return AgentRuntime(
        provider,
        store=store,
        logger=logger,
        artifacts_dir=store.dir,
        execution_strategy_enabled=execution_strategy_enabled,
        execution_strategy_runs=execution_strategy_runs,
    )


def _event_types(logger: Any) -> list[str]:
    return [e.type.value for e in logger.store.query()]


# ================================================================ Flag 关: 旧流程逐位不变


class TestFlagOff:
    def test_off_single_run_single_completed_event(
        self, exec_store, logger, tmp_path: Path
    ) -> None:
        """Flag 关: 单次执行, 单 completed 事件 — 旧流程逐位不变。"""
        provider = FakeProvider(content=_ok_content(tmp_path))
        runtime = _runtime(provider, exec_store, logger)
        request = make_request(request_id="EXR-off-1", project_dir=_bug_project(tmp_path))

        result = runtime.execute(request)

        assert result.is_success
        assert len(provider.calls) == 1  # 单次 Provider 调用
        types = _event_types(logger)
        assert types.count("org.execution.completed") == 1
        assert types.count("org.execution.started") == 1
        assert types.count("org.execution.requested") == 1
        assert runtime.last_candidates == []  # 旧流程不产候选

    def test_off_failure_single_failed_event(
        self, exec_store, logger, tmp_path: Path
    ) -> None:
        """Flag 关 + 失败: 单 failed 事件, 单次调用 — 旧失败语义不变。"""
        provider = FakeProvider(error="anthropic http 429: rate limited")
        runtime = _runtime(provider, exec_store, logger)
        request = make_request(request_id="EXR-off-2", project_dir=_bug_project(tmp_path))

        result = runtime.execute(request)

        assert not result.is_success
        assert len(provider.calls) == 1
        types = _event_types(logger)
        assert types.count("org.execution.failed") == 1
        assert types.count("org.execution.completed") == 0

    def test_off_store_single_result(
        self, exec_store, logger, tmp_path: Path
    ) -> None:
        provider = FakeProvider(content=_ok_content(tmp_path))
        runtime = _runtime(provider, exec_store, logger)
        request = make_request(request_id="EXR-off-3", project_dir=_bug_project(tmp_path))
        runtime.execute(request)
        assert exec_store.count_results() == 1


# ================================================================ Flag 开: 多 Run 策略


class TestFlagOn:
    def test_on_three_runs_three_candidates(
        self, exec_store, logger, tmp_path: Path
    ) -> None:
        provider = FakeProvider(content=_ok_content(tmp_path))
        runtime = _runtime(provider, exec_store, logger, execution_strategy_enabled=True)
        request = make_request(request_id="EXR-on-1", project_dir=_bug_project(tmp_path))

        result = runtime.execute(request)

        assert result.is_success
        assert len(provider.calls) == 3  # N=3 独立 Provider 调用
        candidates = runtime.last_candidates
        assert len(candidates) == 3
        assert all(c.is_success for c in candidates)
        assert [c.run_id for c in candidates] == [
            "EXR-on-1-run-1", "EXR-on-1-run-2", "EXR-on-1-run-3",
        ]
        assert all(c.provider == "mock" for c in candidates)
        types = _event_types(logger)
        assert types.count("org.execution.completed") == 3  # 每 Run 独立事件链

    def test_on_custom_runs(self, exec_store, logger, tmp_path: Path) -> None:
        provider = FakeProvider(content=_ok_content(tmp_path))
        runtime = _runtime(
            provider, exec_store, logger,
            execution_strategy_enabled=True, execution_strategy_runs=2,
        )
        request = make_request(request_id="EXR-on-2", project_dir=_bug_project(tmp_path))
        runtime.execute(request)
        assert len(provider.calls) == 2
        assert len(runtime.last_candidates) == 2

    def test_on_mixed_success_failure_collected(
        self, exec_store, logger, tmp_path: Path
    ) -> None:
        """失败+成功混合: 失败候选必存 (禁静默丢弃), failure_reason 必填。"""
        provider = _SeqProvider([
            ("error", "provider error: empty content (after 1 retry)"),
            ("ok", _ok_content(tmp_path)),
            ("error", "anthropic http 429: rate limited"),
        ])
        runtime = _runtime(provider, exec_store, logger, execution_strategy_enabled=True)
        request = make_request(request_id="EXR-on-3", project_dir=_bug_project(tmp_path))

        result = runtime.execute(request)

        candidates = runtime.last_candidates
        assert len(candidates) == 3  # 失败必存 — 无静默丢弃
        assert not candidates[0].is_success
        assert candidates[0].failure_reason == CANDIDATE_REASON_EMPTY_OUTPUT
        assert candidates[1].is_success
        assert not candidates[2].is_success
        # Provider HTTP 429 = 环境性失败 (非候选产出质量失败) → other 诚实兜底
        assert candidates[2].failure_reason == CANDIDATE_REASON_OTHER
        assert result.is_success  # 临时选择 = 第一个成功候选
        assert result.request_id == "EXR-on-3"

    def test_on_all_failed_returns_failed_result(
        self, exec_store, logger, tmp_path: Path
    ) -> None:
        """全失败: 结果如实失败返回 — 不静默伪装成功。"""
        provider = FakeProvider(error="anthropic http 429: rate limited")
        runtime = _runtime(provider, exec_store, logger, execution_strategy_enabled=True)
        request = make_request(request_id="EXR-on-4", project_dir=_bug_project(tmp_path))

        result = runtime.execute(request)

        assert not result.is_success
        assert len(runtime.last_candidates) == 3
        assert all(not c.is_success for c in runtime.last_candidates)
        types = _event_types(logger)
        assert types.count("org.execution.failed") == 3

    def test_on_first_success_selected_with_patch(
        self, exec_store, logger, tmp_path: Path
    ) -> None:
        """fail/success/fail → 选中第一个成功候选的结果 (patch 产物齐全)。"""
        provider = _SeqProvider([
            ("error", "provider error: empty content (after 1 retry)"),
            ("ok", _ok_content(tmp_path)),
            ("error", "provider error: empty content (after 1 retry)"),
        ])
        runtime = _runtime(provider, exec_store, logger, execution_strategy_enabled=True)
        request = make_request(request_id="EXR-on-5", project_dir=_bug_project(tmp_path))

        result = runtime.execute(request)

        assert result.is_success
        assert result.artifacts  # 成功候选的产物链 (patch/test/report)
        from exec.models import ArtifactType

        assert any(a.type is ArtifactType.PATCH for a in result.artifacts)

    def test_on_store_saves_all_runs(
        self, exec_store, logger, tmp_path: Path
    ) -> None:
        provider = FakeProvider(content=_ok_content(tmp_path))
        runtime = _runtime(provider, exec_store, logger, execution_strategy_enabled=True)
        request = make_request(request_id="EXR-on-6", project_dir=_bug_project(tmp_path))
        runtime.execute(request)
        assert exec_store.count_results() == 3  # 每 Run 结果独立落库

    def test_on_sequential_single_thread(
        self, exec_store, logger, tmp_path: Path
    ) -> None:
        """禁并发: 全部 Provider 调用同一线程 + 严格顺序。"""
        provider = FakeProvider(content=_ok_content(tmp_path))
        real_generate = provider.generate  # 原始 bound method
        provider.threads = []  # type: ignore[attr-defined]
        provider.generate = lambda request: (  # type: ignore[method-assign]
            provider.threads.append(threading.current_thread().name)
            or real_generate(request)
        )
        runtime = _runtime(provider, exec_store, logger, execution_strategy_enabled=True)
        request = make_request(request_id="EXR-on-7", project_dir=_bug_project(tmp_path))
        runtime.execute(request)
        assert len(provider.threads) == 3
        assert len(set(provider.threads)) == 1  # 单线程顺序执行

    def test_on_run_states_recorded(
        self, exec_store, logger, tmp_path: Path
    ) -> None:
        provider = _SeqProvider([
            ("error", "provider error: empty content"),
            ("ok", _ok_content(tmp_path)),
        ])
        runtime = _runtime(
            provider, exec_store, logger,
            execution_strategy_enabled=True, execution_strategy_runs=2,
        )
        request = make_request(request_id="EXR-on-8", project_dir=_bug_project(tmp_path))
        runtime.execute(request)
        # Run 状态经 runner 记录 (runner 内部不可达 — 通过候选/结果交叉验证:
        # 失败 Run 的候选失败、成功 Run 的候选成功, 无静默丢弃)
        candidates = runtime.last_candidates
        assert [c.is_success for c in candidates] == [False, True]
        assert candidates[0].failure_reason  # 失败必带原因


# ================================================================ 失败安全回退


class TestFallback:
    def test_strategy_exception_falls_back_to_legacy(
        self, exec_store, logger, tmp_path: Path
    ) -> None:
        """策略路径异常 → 失败安全回退旧流程 (执行链不破坏)。"""
        provider = FakeProvider(content=_ok_content(tmp_path))
        runtime = _runtime(provider, exec_store, logger, execution_strategy_enabled=True)

        def _boom(_request: Any, **_: Any) -> Any:
            raise RuntimeError("strategy machinery exploded")

        import exec.agent_runtime as ar

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(ar.AgentRuntime, "_execute_strategy", _boom)
        try:
            request = make_request(request_id="EXR-fb-1", project_dir=_bug_project(tmp_path))
            result = runtime.execute(request)
        finally:
            monkeypatch.undo()

        assert result.is_success  # 回退到旧流程单次执行
        assert len(provider.calls) == 1
        assert runtime.last_candidates == []  # 回退路径不产候选
        types = _event_types(logger)
        assert types.count("org.execution.completed") == 1

    def test_flag_off_never_enters_strategy(
        self, exec_store, logger, tmp_path: Path
    ) -> None:
        """Flag 关: 策略路径零调用 (旧流程逐位兼容的强断言)。"""
        provider = FakeProvider(content=_ok_content(tmp_path))
        runtime = _runtime(provider, exec_store, logger)

        called = {"strategy": False}
        original = AgentRuntime._execute_strategy

        def _spy(self: Any, *args: Any, **kwargs: Any) -> Any:
            called["strategy"] = True
            return original(self, *args, **kwargs)

        import exec.agent_runtime as ar

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(ar.AgentRuntime, "_execute_strategy", _spy)
        try:
            request = make_request(request_id="EXR-fb-2", project_dir=_bug_project(tmp_path))
            runtime.execute(request)
        finally:
            monkeypatch.undo()

        assert not called["strategy"]
        assert len(provider.calls) == 1
