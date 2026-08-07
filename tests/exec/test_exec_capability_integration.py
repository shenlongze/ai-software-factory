"""tests/exec/test_exec_capability_integration.py — Model Capability Registry 集成测试 (Sprint 5 T5.4)。

覆盖 (真实 SequentialRunner / registry / stats 全链, mock executor, 零 LLM 零网络):
- Candidate 保存快照: Runner 级 (registry 接线 → 每候选 model_capability_snapshot
  冻结 registry 当前评分) / 未知模型 {} 中性 / 无 registry {} 中性 /
  注册表后续变更不影响已保存候选 (历史可解释) / 异常 Run 失败候选仍带快照
- candidate_from_result 直连快照 / 候选序列化 round-trip 保留快照
- Experience 集成: Runner 接线 stats → 成功/失败计数正确; 批量喂候选 →
  按任务类型成功率; 全闭环: 统计更新 + 注册表评分逐位不变 (禁自动改分强断言)
- registry 加载: seed_defaults → 落盘 → 重载一致; find_by_capability 端到端
  (内置声明式配置驱动查询)
- 回归: 带快照候选 to_experience_signals 词汇不变 (experience_ctx 复用)

basename 唯一 (test_exec_* 前缀); helper 复用 tests/exec/exec_helpers.py。
"""

from __future__ import annotations

from typing import Any

from exec.capability import (
    ModelExperienceStats,
    CapabilityRegistry,
)
from exec.candidate import (
    ExecutionCandidate,
    SequentialRunner,
    candidate_from_result,
)
from exec_helpers import make_request


class _R:
    """duck-typed ExecutionResult (runner executor 产出; 零 LLM 零网络)。"""

    def __init__(
        self,
        *,
        success: bool = True,
        error: str = "",
        usage: dict[str, Any] | None = None,
    ) -> None:
        self.is_success = success
        self.error = error
        self.usage = usage or {}
        self.artifacts = []
        self.generated_output = "ok" if success else ""


def make_registry() -> CapabilityRegistry:
    """内存注册表 (flash + pro 两个模型, 已知评分)。"""
    reg = CapabilityRegistry()
    reg.register({
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "coding_score": 0.6,
        "reasoning_score": 0.8,
        "stability_score": 0.3,
        "context_score": 0.7,
        "tool_use_score": 0.5,
        "cost_score": 0.9,
        "latency_score": 0.8,
    })
    reg.register({
        "provider": "deepseek",
        "model": "deepseek-v4-pro",
        "coding_score": 0.7,
        "reasoning_score": 0.9,
        "stability_score": 0.5,
        "context_score": 0.8,
        "tool_use_score": 0.6,
        "cost_score": 0.7,
        "latency_score": 0.6,
    })
    return reg


# ================================================================ Candidate 快照

class TestCandidateSnapshot:
    def test_runner_captures_snapshot(self) -> None:
        reg = make_registry()
        runner = SequentialRunner(
            executor=lambda _i: _R(),
            runs=3,
            provider="deepseek",
            model="deepseek-v4-flash",
            capability_registry=reg,
        )
        candidates = runner.run()
        assert len(candidates) == 3
        for candidate in candidates:
            snap = candidate.model_capability_snapshot
            assert snap["provider"] == "deepseek"
            assert snap["model"] == "deepseek-v4-flash"
            assert snap["scores"]["cost_score"] == 0.9
            assert snap["scores"]["stability_score"] == 0.3
            assert snap["captured_at"]

    def test_runner_unknown_model_neutral(self) -> None:
        reg = make_registry()
        runner = SequentialRunner(
            executor=lambda _i: _R(),
            runs=2,
            provider="deepseek",
            model="unknown-model",
            capability_registry=reg,
        )
        candidates = runner.run()
        assert all(c.model_capability_snapshot == {} for c in candidates)

    def test_runner_no_registry_neutral(self) -> None:
        runner = SequentialRunner(
            executor=lambda _i: _R(),
            runs=2,
            provider="deepseek",
            model="deepseek-v4-flash",
        )
        candidates = runner.run()
        assert all(c.model_capability_snapshot == {} for c in candidates)

    def test_snapshot_frozen_after_registry_change(self) -> None:
        """历史可解释: 注册表评分后续变化不影响已保存候选。"""
        reg = make_registry()
        runner = SequentialRunner(
            executor=lambda _i: _R(),
            runs=2,
            provider="deepseek",
            model="deepseek-v4-flash",
            capability_registry=reg,
        )
        candidates = runner.run()
        frozen = [c.model_capability_snapshot["scores"]["coding_score"]
                  for c in candidates]
        reg.register({
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "coding_score": 0.99,
            "reasoning_score": 0.99,
            "stability_score": 0.99,
            "context_score": 0.99,
            "tool_use_score": 0.99,
            "cost_score": 0.99,
            "latency_score": 0.99,
        })
        for candidate, before in zip(candidates, frozen):
            assert candidate.model_capability_snapshot["scores"]["coding_score"] \
                == before
        # 新候选才携带新评分
        new_runner = SequentialRunner(
            executor=lambda _i: _R(),
            runs=1,
            provider="deepseek",
            model="deepseek-v4-flash",
            capability_registry=reg,
        )
        fresh = new_runner.run()[0]
        assert fresh.model_capability_snapshot["scores"]["coding_score"] == 0.99

    def test_runner_exception_path_snapshot(self) -> None:
        """异常 Run 失败候选仍带快照 (失败必存 + 历史可解释)。"""
        reg = make_registry()

        def boom(_index: int) -> Any:
            raise RuntimeError("provider timeout")

        runner = SequentialRunner(
            executor=boom,
            runs=2,
            provider="deepseek",
            model="deepseek-v4-flash",
            capability_registry=reg,
        )
        candidates = runner.run()
        assert len(candidates) == 2
        for candidate in candidates:
            assert not candidate.is_success
            assert candidate.failure_reason
            assert candidate.model_capability_snapshot["scores"]["cost_score"] == 0.9

    def test_candidate_from_result_direct_snapshot(self) -> None:
        reg = make_registry()
        candidate = candidate_from_result(
            _R(),
            run_id="EXR-1-run-1",
            request=make_request(),
            provider="deepseek",
            model="deepseek-v4-pro",
            capability_registry=reg,
        )
        snap = candidate.model_capability_snapshot
        assert snap["model"] == "deepseek-v4-pro"
        assert snap["scores"]["reasoning_score"] == 0.9

    def test_snapshot_roundtrip_serialization(self) -> None:
        reg = make_registry()
        candidate = candidate_from_result(
            _R(),
            run_id="EXR-1-run-1",
            provider="deepseek",
            model="deepseek-v4-flash",
            capability_registry=reg,
        )
        restored = ExecutionCandidate.from_dict(candidate.to_dict())
        assert restored.model_capability_snapshot \
            == candidate.model_capability_snapshot


# ================================================================ Experience 统计集成

class TestExperienceStatsIntegration:
    def test_runner_updates_stats(self) -> None:
        reg = make_registry()
        stats = ModelExperienceStats()
        outcomes = [True, True, False]

        def executor(_index: int) -> _R:
            return _R(success=outcomes[_index - 1])

        runner = SequentialRunner(
            executor=executor,
            runs=3,
            provider="deepseek",
            model="deepseek-v4-flash",
            capability_registry=reg,
            experience_stats=stats,
        )
        runner.run()
        assert stats.attempts("deepseek", "deepseek-v4-flash") == 3
        assert stats.successes("deepseek", "deepseek-v4-flash") == 2
        assert stats.failures("deepseek", "deepseek-v4-flash") == 1
        assert stats.success_rate("deepseek", "deepseek-v4-flash") == \
            round(2 / 3, 3)

    def test_stats_by_task_type_from_runner(self) -> None:
        stats = ModelExperienceStats()
        runner = SequentialRunner(
            executor=lambda _i: _R(success=True),
            runs=2,
            provider="deepseek",
            model="deepseek-v4-flash",
            experience_stats=stats,
        )
        runner.run(request=make_request(task_id="bugfix"))
        # runner 喂入不带 task_type (task 维度由调用方显式给 — 统计只记事实)
        assert stats.attempts("deepseek", "deepseek-v4-flash") == 2
        assert stats.attempts("deepseek", "deepseek-v4-flash",
                              task_type="bugfix") == 0
        # 显式 task_type 喂入
        stats.record_candidates(runner.candidates, task_type="bugfix")
        assert stats.attempts("deepseek", "deepseek-v4-flash",
                              task_type="bugfix") == 2
        assert stats.success_rate("deepseek", "deepseek-v4-flash",
                                  task_type="bugfix") == 1.0

    def test_full_loop_no_auto_score_change(self) -> None:
        """全闭环强断言: 统计更新 + 注册表评分逐位不变 (禁自动改分铁律)。"""
        reg = make_registry()
        stats = ModelExperienceStats()
        before = {c.model: c.to_dict() for c in reg.list()}
        runner = SequentialRunner(
            executor=lambda _i: _R(success=False, error="validation failed"),
            runs=5,
            provider="deepseek",
            model="deepseek-v4-flash",
            capability_registry=reg,
            experience_stats=stats,
        )
        runner.run()
        assert stats.failures("deepseek", "deepseek-v4-flash") == 5
        after = {c.model: c.to_dict() for c in reg.list()}
        assert after == before  # 评分未被经验统计触碰

    def test_stats_serialization_across_store(self, tmp_path: Any) -> None:
        """统计可随审计输出落盘/重载 (不重复建库 — JSON dict 序列化)。"""
        stats = ModelExperienceStats()
        stats.record_candidates([
            ExecutionCandidate(id="CAND-1", run_id="R-1",
                               provider="deepseek", model="deepseek-v4-flash"),
            ExecutionCandidate(id="CAND-2", run_id="R-2",
                               provider="deepseek", model="deepseek-v4-flash",
                               failure_reason="token_limit"),
        ], task_type="bugfix")
        payload = stats.to_dict()
        reloaded = ModelExperienceStats(payload)
        assert reloaded.success_rate("deepseek", "deepseek-v4-flash",
                                     task_type="bugfix") == 0.5


# ================================================================ Registry 加载/查询端到端

class TestRegistryEndToEnd:
    def test_seed_defaults_persist_and_reload(self, tmp_path: Any) -> None:
        reg = CapabilityRegistry(tmp_path, seed_defaults=True)
        assert reg.count() >= 2
        reloaded = CapabilityRegistry(tmp_path)
        assert reloaded.count() == reg.count()
        flash = reloaded.get("deepseek", "deepseek-v4-flash")
        assert flash is not None
        assert flash.cost_score == 0.9  # 与声明式配置文件一致

    def test_find_by_capability_end_to_end(self) -> None:
        reg = CapabilityRegistry()
        reg.seed_defaults()
        # 便宜优先: cost_score ≥ 0.85 → 只有 flash
        cheap = reg.find_by_capability("cost_score", 0.85)
        assert [c.model for c in cheap] == ["deepseek-v4-flash"]
        # 推理优先: reasoning_score ≥ 0.85 → pro 在前
        smart = reg.find_by_capability("reasoning_score", 0.85)
        assert [c.model for c in smart] == ["deepseek-v4-pro"]
        # 稳定性: stability ≥ 0.4 → pro 唯一 (flash 0.3 低 — T5.1 诊断语义)
        stable = reg.find_by_capability("stability_score", 0.4)
        assert [c.model for c in stable] == ["deepseek-v4-pro"]

    def test_registry_snapshot_into_candidate_chain(self) -> None:
        """注册表 → 快照 → 候选 → 评估信号全链 (零 LLM)。"""
        reg = make_registry()
        stats = ModelExperienceStats()
        runner = SequentialRunner(
            executor=lambda _i: _R(),
            runs=3,
            provider="deepseek",
            model="deepseek-v4-flash",
            capability_registry=reg,
            experience_stats=stats,
        )
        candidates = runner.run()
        evaluation = runner.evaluate()
        assert evaluation.selected_candidate_id is not None
        selected = next(
            c for c in candidates if c.id == evaluation.selected_candidate_id
        )
        assert selected.model_capability_snapshot["model"] == "deepseek-v4-flash"

    def test_signals_vocabulary_regression(self) -> None:
        """带快照候选 to_experience_signals 词汇不变 (experience_ctx 复用)。"""
        reg = make_registry()
        runner = SequentialRunner(
            executor=lambda _i: _R(success=False, error="test failed"),
            runs=1,
            provider="deepseek",
            model="deepseek-v4-flash",
            capability_registry=reg,
        )
        candidate = runner.run()[0]
        assert candidate.model_capability_snapshot  # 快照存在
        assert candidate.to_experience_signals() == ["validation_failure"]

    def test_stats_without_registry_side_effects(self) -> None:
        """统计独立于注册表: 无 registry 也能统计 (不强制耦合)。"""
        stats = ModelExperienceStats()
        runner = SequentialRunner(
            executor=lambda _i: _R(),
            runs=2,
            provider="deepseek",
            model="deepseek-v4-flash",
            experience_stats=stats,
        )
        runner.run()
        assert stats.successes("deepseek", "deepseek-v4-flash") == 2
