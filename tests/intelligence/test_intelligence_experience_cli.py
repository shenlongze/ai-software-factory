"""tests/intelligence/test_intelligence_experience_cli.py — Intelligence Experience
Evaluate CLI (Phase 10A-4, ADR-0033): factory intelligence experience evaluate。

覆盖 (10A-4 单字符 bug 回归 + 冒烟):
- --capability 逗号分割: 单值 "code" → ["code"] (不拆成 ['c','o','d','e']);
  多值 "code,reasoning" → ["code","reasoning"]; 空段 "code,, reasoning ,"
  → 过滤空段 ["code","reasoning"]
- 非冷启动冒烟: seed 经验 (字符串 capability) → evaluate --capability code →
  推荐输出 (agent/provider) + 无冷启动风险
- 文本输出 (能力行/推荐行/事件锚点) + --json 结构 (evaluation/event_seq)

basename 全仓库唯一 (test_intelligence_* 前缀)。
"""

from __future__ import annotations

import json

from intelligence.experience import ExperienceAnalyzer
from intelligence.store import ExperienceStore


def _run(root, *argv) -> int:
    from cli.main import main

    return main(["--root", str(root), *argv])


def _seed(root, *records) -> None:
    """向 CLI 数据空间 (<root>/intelligence) 落经验记录 (冒烟 seed)。

    records: (subject_type, subject_id, task_type, capability, score) 元组;
    capability 传字符串 — 正是 10A-4 单字符 bug 的输入形态。
    """
    an = ExperienceAnalyzer(ExperienceStore(root / "intelligence"))
    for subject_type, subject_id, task_type, capability, score in records:
        an.record_experience(
            subject_type=subject_type,
            subject_id=subject_id,
            task_type=task_type,
            capability=capability,
            result="success",
            score=score,
            confidence=0.9,
        )


# ------------------------------------------------------------------- --capability 解析


class TestCapabilityParsing:
    def test_single_value_not_chars(self, tmp_path, capsys):
        """10A-4 单字符 bug 回归: --capability code → ["code"] (非 ['c','o','d','e'])。"""
        _seed(
            tmp_path,
            ("agent", "coder-1", "development", "code", 0.9),
        )
        rc = _run(tmp_path, "intelligence", "experience", "evaluate",
                  "--task", "development", "--capability", "code", "--json")
        out = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert out["evaluation"]["required_capabilities"] == ["code"]

    def test_comma_split(self, tmp_path, capsys):
        _seed(
            tmp_path,
            ("agent", "coder-1", "development", "code,reasoning", 0.9),
        )
        rc = _run(tmp_path, "intelligence", "experience", "evaluate",
                  "--task", "development", "--capability", "code,reasoning", "--json")
        out = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert out["evaluation"]["required_capabilities"] == ["code", "reasoning"]

    def test_empty_segments_filtered(self, tmp_path, capsys):
        _seed(
            tmp_path,
            ("agent", "coder-1", "development", "code", 0.9),
        )
        rc = _run(tmp_path, "intelligence", "experience", "evaluate",
                  "--task", "development", "--capability", "code,, reasoning ,", "--json")
        out = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert out["evaluation"]["required_capabilities"] == ["code", "reasoning"]

    def test_absent_capability_empty(self, tmp_path, capsys):
        _seed(
            tmp_path,
            ("agent", "coder-1", "development", "code", 0.9),
        )
        rc = _run(tmp_path, "intelligence", "experience", "evaluate",
                  "--task", "development", "--json")
        out = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert out["evaluation"]["required_capabilities"] == []


# ------------------------------------------------------------------- 非冷启动冒烟


class TestEvaluateSmoke:
    def test_string_seeded_capability_recommends(self, tmp_path, capsys):
        """seed 经验 (capability 字符串) → evaluate --capability code → 推荐非冷启动。"""
        _seed(
            tmp_path,
            ("agent", "coder-1", "development", "code", 0.9),
            ("provider", "hermes", "development", "code", 0.85),
        )
        rc = _run(tmp_path, "intelligence", "experience", "evaluate",
                  "--task", "development", "--capability", "code", "--json")
        out = json.loads(capsys.readouterr().out)
        assert rc == 0
        ev = out["evaluation"]
        assert ev["task_type"] == "development"
        assert ev["required_capabilities"] == ["code"]
        assert [e["id"] for e in ev["recommended_agents"]] == ["coder-1"]
        assert [e["id"] for e in ev["recommended_providers"]] == ["hermes"]
        assert not any("冷启动" in risk for risk in ev["risks"])
        assert ev["confidence"] > 0.0
        assert out["event_seq"]  # intelligence.task.evaluated 事件锚点

    def test_text_output_recommends_not_cold_start(self, tmp_path, capsys):
        _seed(
            tmp_path,
            ("agent", "coder-1", "development", "code", 0.9),
        )
        rc = _run(tmp_path, "intelligence", "experience", "evaluate",
                  "--task", "development", "--capability", "code")
        out = capsys.readouterr().out
        assert rc == 0
        assert "✔ 任务评估 (task: development)" in out
        assert "能力        code" in out
        assert "推荐 Agent" in out
        assert "coder-1" in out
        assert "冷启动" not in out
        assert "intelligence.task.evaluated seq=" in out
