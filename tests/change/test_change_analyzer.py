"""tests/change/test_change_analyzer.py — ChangeAnalyzer 路径分析 + L4 判定纯函数。

覆盖: _module_chain / affected_modules / ChangeAnalyzer.analyze (Files/
Insertions/Deletions/Modules) / l4_checks (SKIP/PASS/FAIL 全分支) /
l4_verdict (ERROR 兜底 > 任一 PASS → PASS > 任一 FAIL → FAIL > SKIP —
FAIL 须"无关联提交且标题无重叠"双条件缺失, ADR-0019 决策 6) — 全部确定性
规则, 禁 LLM。
"""

from __future__ import annotations

import pytest

from change.analyzer import (
    ChangeAnalyzer,
    _module_chain,
    affected_modules,
    l4_checks,
    l4_verdict,
)

from change_helpers import make_change, make_change_context, make_commit


class TestModuleChain:
    def test_py_module_chain(self):
        # 后缀链: 最宽泛 (全路径) 在前, 最具体 (文件模块名) 在后
        assert _module_chain("change/analyzer.py") == ["change.analyzer", "analyzer"]

    def test_src_layout(self):
        assert _module_chain("src/app.py") == ["src.app", "app"]

    def test_noise_dirs_filtered(self):
        assert "node_modules" not in _module_chain("node_modules/lodash/index.js")
        assert "__pycache__" not in _module_chain("app/__pycache__/x.pyc")

    def test_non_py_keeps_filename(self):
        assert _module_chain("README.md") == ["README.md"]
        assert _module_chain("package.json") == ["package.json"]

    def test_deep_path_chain(self):
        chain = _module_chain("a/b/c/d.py")
        assert chain == ["a.b.c.d", "b.c.d", "c.d", "d"]

    def test_empty_path(self):
        assert _module_chain("") == []


class TestAffectedModules:
    def test_union_dedup_sorted(self):
        mods = affected_modules(["b.py", "a.py", "b.py"])
        assert mods == ["a", "b"]

    def test_limit_cap(self):
        files = [f"f{i}.py" for i in range(100)]
        mods = affected_modules(files, limit=10)
        assert len(mods) == 10

    def test_empty(self):
        assert affected_modules([]) == []


class TestChangeAnalyzerAnalyze:
    def test_empty_input_failsafe(self):
        a = ChangeAnalyzer().analyze("MP-BUG-001")
        assert a.task_id == "MP-BUG-001"
        assert a.files == []
        assert a.insertions == 0
        assert a.deletions == 0

    def test_files_union_from_changes(self):
        changes = [make_change("a.py"), make_change("b.py")]
        a = ChangeAnalyzer().analyze("MP-BUG-001", changes=changes)
        assert a.files == ["a.py", "b.py"]

    def test_explicit_files_merged_sorted_dedup(self):
        a = ChangeAnalyzer().analyze("T-001", files=["b.py", "a.py", "b.py"])
        assert a.files == ["a.py", "b.py"]

    def test_insertions_deletions_sum(self):
        changes = [make_change("a.py", insertions=3, deletions=1),
                   make_change("b.py", insertions=7, deletions=2)]
        a = ChangeAnalyzer().analyze("T-001", changes=changes)
        assert a.insertions == 10
        assert a.deletions == 3

    def test_commits_deduped(self):
        a = ChangeAnalyzer().analyze("T-001", commits=["h1", "h1", "h2"])
        assert a.commits == ["h1", "h2"]

    def test_modules_inferred(self):
        a = ChangeAnalyzer().analyze("T-001", files=["app/auth.py"])
        assert "app.auth" in a.affected_modules

    def test_task_id_passthrough(self):
        a = ChangeAnalyzer().analyze("MP-FEATURE-002")
        assert a.task_id == "MP-FEATURE-002"


class TestL4Checks:
    def test_not_repo_both_skip(self):
        ctx = make_change_context(is_repo=False)
        checks = l4_checks(ctx)
        assert [c["status"] for c in checks] == ["SKIP", "SKIP"]

    def test_repo_no_evidence_skip(self):
        ctx = make_change_context(is_repo=True, commits=[], files=[])
        assert [c["status"] for c in l4_checks(ctx)] == ["SKIP", "SKIP"]

    def test_commit_link_pass(self):
        ctx = make_change_context(
            commits=[make_commit(task_id="MP-BUG-001")], files=["app/auth.py"])
        checks = l4_checks(ctx)
        assert checks[0]["id"] == "L4.commit_link"
        assert checks[0]["status"] == "PASS"

    def test_commit_link_fail_with_evidence(self):
        ctx = make_change_context(commits=[make_commit(task_id="MP-FEATURE-002")],
                                  files=["app/auth.py"])
        assert l4_checks(ctx)[0]["status"] == "FAIL"

    def test_path_match_pass_on_overlap(self):
        ctx = make_change_context(task_title="login page",
                                  files=["app/login.py"])
        checks = l4_checks(ctx)
        assert checks[1]["id"] == "L4.path_match"
        assert checks[1]["status"] == "PASS"

    def test_path_match_skip_no_title(self):
        ctx = make_change_context(task_title="", files=["app/auth.py"])
        assert l4_checks(ctx)[1]["status"] == "SKIP"

    def test_path_match_fail_no_overlap(self):
        ctx = make_change_context(task_title="billing report",
                                  files=["app/auth.py"])
        assert l4_checks(ctx)[1]["status"] == "FAIL"

    def test_path_match_case_insensitive(self):
        ctx = make_change_context(task_title="LOGIN crash", files=["app/Login.py"])
        assert l4_checks(ctx)[1]["status"] == "PASS"

    def test_path_match_module_overlap(self):
        # 标题 token 与模块名重叠 (模块链 'app.auth') 同样命中
        ctx = make_change_context(task_title="auth service",
                                  files=["app/auth.py"])
        assert l4_checks(ctx)[1]["status"] == "PASS"

    def test_chinese_title_no_false_positive(self):
        ctx = make_change_context(task_title="修复登录崩溃", files=["app/auth.py"])
        assert l4_checks(ctx)[1]["status"] == "FAIL"  # 中文整段 token 不重叠

    def test_checks_include_message_text(self):
        ctx = make_change_context(commits=[make_commit(task_id="MP-BUG-001")])
        assert "MP-BUG-001" in l4_checks(ctx)[0]["message"]


class TestL4Verdict:
    def test_all_skip(self):
        checks = [{"id": "a", "status": "SKIP"}, {"id": "b", "status": "SKIP"}]
        assert l4_verdict(checks) == "SKIP"

    def test_any_pass(self):
        checks = [{"id": "a", "status": "SKIP"}, {"id": "b", "status": "PASS"}]
        assert l4_verdict(checks) == "PASS"

    def test_pass_any_rule_wins_over_fail(self):
        # 关联提交命中 (commit_link PASS) + 无关工作区文件标题不重叠 (path_match
        # FAIL) → 仍 PASS — FAIL 须双条件缺失, 不因无关文件误报 (ADR-0019 决策 6)
        checks = [{"id": "a", "status": "PASS"}, {"id": "b", "status": "FAIL"}]
        assert l4_verdict(checks) == "PASS"

    def test_fail_when_no_rule_passes(self):
        checks = [{"id": "a", "status": "FAIL"}, {"id": "b", "status": "SKIP"}]
        assert l4_verdict(checks) == "FAIL"

    def test_error_fallback(self):
        checks = [{"id": "a", "status": "SKIP"}, {"id": "b", "status": "ERROR"}]
        assert l4_verdict(checks) == "ERROR"

    def test_empty_checks_skip(self):
        assert l4_verdict([]) == "SKIP"

    def test_missing_status_defaults_skip(self):
        assert l4_verdict([{"id": "a"}]) == "SKIP"
