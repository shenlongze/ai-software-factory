"""S10-062 批次 A — ContextBuilder + PlanningTrace 基础设施测试套件。

覆盖:
- ContextBuilder: 完整上下文 14 字段 + meta / 每字段 source 标识 / PRD 解析 /
  engineering/execution_state/execution_plan/workspace/validation/team/
  capabilities/previous_decisions/previous_replans / 缺失文件失败安全 /
  estimate_tokens (中文≈1 char/token, 其他≈4) / truncate budget 裁剪
  (关键字段保留, 低优先级先丢, 输入不变) / extract_evidence。
- PlanningTrace: record 白名单字段 / 落盘 append / input_hash (sha256,
  不存原文) / 敏感信息脱敏 (api_key/secret/token 键) / load 失败安全 /
  for_project 项目级文件。

装配: tmp_path + fixtures (PRD.md/engineering.json/execution_state.json/
execution_plan.json/workspace_context.json/validation_result.json/
project.json/gap_analysis.json/replanning_decisions.json/
team_execution_state.json); 禁真实 LLM/网络 (纯 deterministic)。
"""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path

CB = import_module("factory-console.session.context_builder")
PT = import_module("factory-console.session.planning_trace")

PRD_TEXT = """# ScorePocket

平台: mobile

记分应用 — 记录用户分数并持久化。

- 用户可记录分数
- 数据需要持久化
- 需要界面展示
"""


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def make_project(tmp_path: Path) -> Path:
    """标准项目资产 fixture (ScorePocket — mobile + 持久化要求)。"""
    root = tmp_path / "scorepocket"
    root.mkdir(parents=True, exist_ok=True)
    (root / "PRD.md").write_text(PRD_TEXT, encoding="utf-8")
    write_json(root / "project.json", {"name": "ScorePocket", "slug": "scorepocket"})
    write_json(root / "engineering.json", {
        "name": "ScorePocket",
        "platform": "mobile",
        "architecture": "layered",
        "modules": [{"name": "storage", "description": "持久化模块"}],
        "technical_tasks": [{"id": "E1", "name": "数据存储"}],
    })
    write_json(root / "execution_state.json", {
        "plan_version": 2,
        "replan_count": 1,
        "tasks": [
            {"id": "T001", "name": "backend api", "status": "completed",
             "agent": "backend"},
            {"id": "T002", "name": "ui", "status": "failed",
             "agent": "frontend"},
            {"id": "T003", "name": "pending task", "status": "pending"},
        ],
    })
    write_json(root / "execution_plan.json", {
        "tasks": [
            {"id": "T001", "name": "backend api", "status": "completed"},
            {"id": "T002", "name": "ui", "status": "failed"},
        ],
    })
    write_json(root / "workspace_context.json", {
        "project": "ScorePocket",
        "files": ["src/a.py"],
        "completed_tasks": ["T001"],
        "artifacts": ["art_a.json", "art_b.json"],
        "agent_history": [{"agent": "backend", "task_id": "T001"}],
    })
    write_json(root / "validation_result.json", {
        "success": True,
        "tests_total": 10,
        "tests_passed": 9,
        "tests_failed": 1,
        "errors": ["test_x failed"],
    })
    write_json(root / "gap_analysis.json", [
        {"detected": True, "gap_type": "missing_test",
         "source_task_id": "T001"},
    ])
    write_json(root / "replanning_decisions.json", [
        {"decision": "INSERT_TASK", "affected_tasks": ["T001"]},
    ])
    write_json(root / "team_execution_state.json", {
        "team": "team-a", "status": "running", "plan_version": 2,
        "tasks": {"T001": {"status": "completed", "agent": "backend"}},
    })
    return root


# ==================================================================
# ContextBuilder — 结构
# ==================================================================


class TestContextStructure:
    def test_all_fields_present(self, tmp_path):
        ctx = CB.ContextBuilder().build(make_project(tmp_path), "scorepocket")
        for f in CB.ContextBuilder.CONTEXT_FIELDS:
            assert f in ctx, f"context 缺字段: {f}"

    def test_meta_present(self, tmp_path):
        ctx = CB.ContextBuilder().build(make_project(tmp_path), "scorepocket")
        for k in ("slug", "built_at", "sources", "total_tokens", "truncated"):
            assert k in ctx["meta"], f"meta 缺键: {k}"

    def test_meta_slug(self, tmp_path):
        ctx = CB.ContextBuilder().build(make_project(tmp_path), "scorepocket")
        assert ctx["meta"]["slug"] == "scorepocket"

    def test_meta_slug_defaults_to_dirname(self, tmp_path):
        root = make_project(tmp_path)
        ctx = CB.ContextBuilder().build(root)
        assert ctx["meta"]["slug"] == "scorepocket"

    def test_each_field_has_source_and_value(self, tmp_path):
        ctx = CB.ContextBuilder().build(make_project(tmp_path), "scorepocket")
        for f in CB.ContextBuilder.CONTEXT_FIELDS:
            assert isinstance(ctx[f], dict), f"{f} 非 dict"
            assert "source" in ctx[f], f"{f} 缺 source"
            assert "value" in ctx[f], f"{f} 缺 value"

    def test_source_identifiers(self, tmp_path):
        ctx = CB.ContextBuilder().build(make_project(tmp_path), "scorepocket")
        assert ctx["product"]["source"] == "PRD.md"
        assert ctx["requirements"]["source"] == "PRD.md"
        assert ctx["engineering"]["source"] == "engineering.json"
        assert ctx["current_plan"]["source"] == "execution_plan.json"
        assert ctx["completed_work"]["source"] == "execution_state.json"
        assert ctx["failed_work"]["source"] == "execution_state.json"
        assert ctx["validation"]["source"] == "validation_result.json"
        assert ctx["workspace"]["source"] == "workspace_context.json"
        assert ctx["artifacts"]["source"] == "workspace_context.json"
        assert ctx["team"]["source"] == "team_execution_state.json"
        assert ctx["capabilities"]["source"] == "roles.py"
        assert ctx["previous_decisions"]["source"] == "replanning_decisions.json"
        assert ctx["previous_replans"]["source"] == "gap_analysis.json"

    def test_meta_sources_records_present_files(self, tmp_path):
        ctx = CB.ContextBuilder().build(make_project(tmp_path), "scorepocket")
        s = ctx["meta"]["sources"]
        assert s["PRD.md"] is True
        assert s["engineering.json"] is True
        assert s["execution_state.json"] is True
        assert s["validation_result.json"] is True

    def test_meta_total_tokens_int(self, tmp_path):
        ctx = CB.ContextBuilder().build(make_project(tmp_path), "scorepocket")
        assert isinstance(ctx["meta"]["total_tokens"], int)
        assert ctx["meta"]["total_tokens"] > 0

    def test_meta_truncated_false_by_default(self, tmp_path):
        ctx = CB.ContextBuilder().build(make_project(tmp_path), "scorepocket")
        assert ctx["meta"]["truncated"] is False

    def test_build_non_path_project_dir_fail_safe(self, tmp_path):
        ctx = CB.ContextBuilder().build(12345, "x")
        assert ctx["meta"]["slug"] == "x"
        assert ctx["project"]["value"]["name"] == "x"


# ==================================================================
# ContextBuilder — 字段内容
# ==================================================================


class TestContextContent:
    def test_project_from_project_json(self, tmp_path):
        ctx = CB.ContextBuilder().build(make_project(tmp_path), "scorepocket")
        assert ctx["project"]["value"] == {
            "name": "ScorePocket", "slug": "scorepocket",
        }

    def test_product_parsed_from_prd(self, tmp_path):
        ctx = CB.ContextBuilder().build(make_project(tmp_path), "scorepocket")
        p = ctx["product"]["value"]
        assert p["name"] == "ScorePocket"
        assert p["platform"] == "mobile"
        assert p["summary"]

    def test_requirements_from_prd_bullets(self, tmp_path):
        ctx = CB.ContextBuilder().build(make_project(tmp_path), "scorepocket")
        reqs = ctx["requirements"]["value"]
        assert "数据需要持久化" in reqs
        assert len(reqs) >= 3

    def test_engineering_normalized(self, tmp_path):
        ctx = CB.ContextBuilder().build(make_project(tmp_path), "scorepocket")
        e = ctx["engineering"]["value"]
        assert e["name"] == "ScorePocket"
        assert e["platform"] == "mobile"
        assert e["modules"]

    def test_current_plan_tasks(self, tmp_path):
        ctx = CB.ContextBuilder().build(make_project(tmp_path), "scorepocket")
        plan = ctx["current_plan"]["value"]
        assert isinstance(plan, list)
        assert len(plan) == 2

    def test_current_plan_accepts_plain_list(self, tmp_path):
        root = make_project(tmp_path)
        write_json(root / "execution_plan.json", [
            {"id": "T001", "name": "a"}, {"id": "T002", "name": "b"},
        ])
        ctx = CB.ContextBuilder().build(root, "scorepocket")
        assert len(ctx["current_plan"]["value"]) == 2

    def test_completed_work_only_completed(self, tmp_path):
        ctx = CB.ContextBuilder().build(make_project(tmp_path), "scorepocket")
        done = ctx["completed_work"]["value"]
        assert len(done) == 1
        assert done[0]["id"] == "T001"

    def test_failed_work_only_failed(self, tmp_path):
        ctx = CB.ContextBuilder().build(make_project(tmp_path), "scorepocket")
        failed = ctx["failed_work"]["value"]
        assert len(failed) == 1
        assert failed[0]["id"] == "T002"

    def test_validation_normalized(self, tmp_path):
        ctx = CB.ContextBuilder().build(make_project(tmp_path), "scorepocket")
        v = ctx["validation"]["value"]
        assert v["success"] is True
        assert v["tests_total"] == 10
        assert v["tests_failed"] == 1

    def test_workspace_context(self, tmp_path):
        ctx = CB.ContextBuilder().build(make_project(tmp_path), "scorepocket")
        w = ctx["workspace"]["value"]
        assert w["project"] == "ScorePocket"
        assert w["files"] == ["src/a.py"]

    def test_artifacts_from_workspace(self, tmp_path):
        ctx = CB.ContextBuilder().build(make_project(tmp_path), "scorepocket")
        assert ctx["artifacts"]["value"] == ["art_a.json", "art_b.json"]

    def test_team_normalized(self, tmp_path):
        ctx = CB.ContextBuilder().build(make_project(tmp_path), "scorepocket")
        t = ctx["team"]["value"]
        assert t["team"] == "team-a"
        assert t["plan_version"] == 2
        assert t["tasks_count"] == 1

    def test_capabilities_from_roles(self, tmp_path):
        ctx = CB.ContextBuilder().build(make_project(tmp_path), "scorepocket")
        c = ctx["capabilities"]["value"]
        assert "backend" in c["roles"]
        assert "frontend" in c["roles"]
        assert "qa" in c["roles"]
        assert "backend_api" in c["capabilities"]

    def test_previous_decisions(self, tmp_path):
        ctx = CB.ContextBuilder().build(make_project(tmp_path), "scorepocket")
        d = ctx["previous_decisions"]["value"]
        assert len(d) == 1
        assert d[0]["decision"] == "INSERT_TASK"

    def test_previous_replans(self, tmp_path):
        ctx = CB.ContextBuilder().build(make_project(tmp_path), "scorepocket")
        r = ctx["previous_replans"]["value"]
        assert len(r) == 1
        assert r[0]["gap_type"] == "missing_test"


# ==================================================================
# ContextBuilder — 失败安全
# ==================================================================


class TestContextFailSafe:
    def test_missing_project_dir_no_raise(self, tmp_path):
        ctx = CB.ContextBuilder().build(tmp_path / "nope", "ghost")
        assert ctx["product"]["value"]["name"] == "ghost"
        assert ctx["requirements"]["value"] == []

    def test_missing_prd_no_raise(self, tmp_path):
        root = make_project(tmp_path)
        (root / "PRD.md").unlink()
        ctx = CB.ContextBuilder().build(root, "scorepocket")
        assert ctx["product"]["value"]["name"] == "scorepocket"
        assert ctx["requirements"]["value"] == []
        assert ctx["meta"]["sources"]["PRD.md"] is False

    def test_corrupt_json_no_raise(self, tmp_path):
        root = make_project(tmp_path)
        (root / "engineering.json").write_text("{not json", encoding="utf-8")
        ctx = CB.ContextBuilder().build(root, "scorepocket")
        # 损坏 → 规范空 dict (非抛)
        assert ctx["engineering"]["value"] == {
            "name": "", "platform": "", "architecture": "",
            "modules": [], "technical_tasks": [],
        }
        assert ctx["meta"]["sources"]["engineering.json"] is False

    def test_non_dict_json_defaults(self, tmp_path):
        root = make_project(tmp_path)
        (root / "engineering.json").write_text('["a", 1]', encoding="utf-8")
        ctx = CB.ContextBuilder().build(root, "scorepocket")
        assert ctx["engineering"]["value"] == {
            "name": "", "platform": "", "architecture": "",
            "modules": [], "technical_tasks": [],
        }

    def test_missing_execution_state_no_raise(self, tmp_path):
        root = make_project(tmp_path)
        (root / "execution_state.json").unlink()
        ctx = CB.ContextBuilder().build(root, "scorepocket")
        assert ctx["completed_work"]["value"] == []
        assert ctx["failed_work"]["value"] == []

    def test_missing_all_assets_empty_context(self, tmp_path):
        ctx = CB.ContextBuilder().build(tmp_path / "empty", "e")
        empty_vals = (
            {}, [],
            {"name": "e", "slug": "e"},
            {"name": "e", "platform": "", "summary": "", "requirements": []},
            {"name": "", "platform": "", "architecture": "",
             "modules": [], "technical_tasks": []},
            {"success": False, "tests_total": 0, "tests_passed": 0,
             "tests_failed": 0, "errors": []},
            {"team": "", "status": "", "plan_version": 1, "tasks_count": 0},
        )
        for f in CB.ContextBuilder.CONTEXT_FIELDS:
            if f == "capabilities":
                assert ctx[f]["value"]["roles"]
            else:
                assert ctx[f]["value"] in empty_vals, f"{f}: {ctx[f]['value']}"


# ==================================================================
# ContextBuilder — estimate_tokens
# ==================================================================


class TestEstimateTokens:
    def test_empty_is_zero(self):
        assert CB.ContextBuilder.estimate_tokens("") == 0

    def test_none_is_zero(self):
        assert CB.ContextBuilder.estimate_tokens(None) == 0

    def test_ascii_roughly_len_over_4(self):
        # "hello world, this is a test!!" = 29 非中文 → (29+3)//4 = 8
        n = CB.ContextBuilder.estimate_tokens("hello world, this is a test!!")
        assert n == 8

    def test_cjk_one_char_per_token(self):
        assert CB.ContextBuilder.estimate_tokens("持久化存储") == 5

    def test_mixed_cjk_and_ascii(self):
        # 5 CJK + " storage"(8) → 5 + (8+3)//4 = 5 + 2 = 7
        n = CB.ContextBuilder.estimate_tokens("持久化存储 storage")
        assert n == 7

    def test_returns_int_and_deterministic(self):
        b = CB.ContextBuilder()
        assert b.estimate_tokens("abc") == b.estimate_tokens("abc")
        assert isinstance(b.estimate_tokens("abc"), int)


# ==================================================================
# ContextBuilder — truncate (budget 裁剪)
# ==================================================================


class TestTruncate:
    def _ctx(self, tmp_path) -> dict:
        return CB.ContextBuilder().build(make_project(tmp_path), "scorepocket")

    def test_within_budget_unchanged(self, tmp_path):
        ctx = self._ctx(tmp_path)
        out = CB.ContextBuilder().truncate(ctx, 10**9)
        assert out["meta"]["truncated"] is False
        assert out["requirements"]["value"] == ctx["requirements"]["value"]

    def test_over_budget_truncated_flag(self, tmp_path):
        out = CB.ContextBuilder().truncate(self._ctx(tmp_path), 250)
        assert out["meta"]["truncated"] is True

    def test_truncated_size_within_budget(self, tmp_path):
        out = CB.ContextBuilder().truncate(self._ctx(tmp_path), 250)
        assert out["meta"]["total_tokens"] <= 250

    def test_key_fields_kept_first(self, tmp_path):
        ctx = self._ctx(tmp_path)
        out = CB.ContextBuilder().truncate(ctx, 350)
        # 高优先级字段 (requirements/engineering) 保留, 低优先级被裁剪
        assert out["requirements"]["value"]
        assert out["engineering"]["value"]
        assert not out["previous_replans"]["value"]

    def test_low_priority_dropped_before_high(self, tmp_path):
        ctx = self._ctx(tmp_path)
        out = CB.ContextBuilder().truncate(ctx, 350)
        # 中间预算: 低优先级已丢, 高优先级仍在
        assert out["requirements"]["value"]
        assert out["current_plan"]["value"]
        assert not out["previous_decisions"]["value"]

    def test_input_not_mutated(self, tmp_path):
        ctx = self._ctx(tmp_path)
        before = json.dumps(ctx, ensure_ascii=False, sort_keys=True)
        CB.ContextBuilder().truncate(ctx, 250)
        after = json.dumps(ctx, ensure_ascii=False, sort_keys=True)
        assert before == after

    def test_budget_none_returns_copy(self, tmp_path):
        ctx = self._ctx(tmp_path)
        out = CB.ContextBuilder().truncate(ctx)
        assert out == ctx

    def test_non_dict_returns_empty(self):
        assert CB.ContextBuilder().truncate("nope", 10) == {}

    def test_dropped_field_keeps_source_structure(self, tmp_path):
        out = CB.ContextBuilder().truncate(self._ctx(tmp_path), 250)
        assert "source" in out["previous_replans"]
        assert "value" in out["previous_replans"]


# ==================================================================
# ContextBuilder — extract_evidence
# ==================================================================


class TestExtractEvidence:
    def test_validation_evidence(self):
        ev = CB.ContextBuilder().extract_evidence(
            validation_result={"success": True, "tests_total": 10,
                               "tests_passed": 9, "tests_failed": 1},
        )
        srcs = {e["source"] for e in ev}
        assert "validation_result.json" in srcs
        fields = {e["field"] for e in ev}
        assert "success" in fields and "tests" in fields

    def test_validation_error_evidence(self):
        ev = CB.ContextBuilder().extract_evidence(
            validation_result={"success": False,
                               "errors": ["test_x failed", "boom"]},
        )
        errs = [e for e in ev if e["field"] == "errors"]
        assert len(errs) == 2
        assert "test_x failed" in errs[0]["observation"]

    def test_execution_state_evidence(self):
        ev = CB.ContextBuilder().extract_evidence(
            execution_state={"replan_count": 2, "tasks": [
                {"id": "T001", "status": "completed"},
                {"id": "T002", "status": "failed"},
            ]},
        )
        fields = {e["field"] for e in ev}
        assert "completed_work" in fields
        assert "failed_work" in fields
        assert "replan_count" in fields
        assert all(e["source"] == "execution_state.json" for e in ev)

    def test_workspace_evidence(self):
        ev = CB.ContextBuilder().extract_evidence(
            workspace={"completed_tasks": ["T001"],
                       "artifacts": ["a.json"], "files": ["x.py"]},
        )
        fields = {e["field"] for e in ev}
        assert "completed_tasks" in fields
        assert "artifacts" in fields
        assert "files" in fields

    def test_empty_inputs_no_evidence(self):
        assert CB.ContextBuilder().extract_evidence() == []

    def test_non_dict_inputs_fail_safe(self):
        assert CB.ContextBuilder().extract_evidence("x", 42, None) == []

    def test_evidence_structure(self):
        ev = CB.ContextBuilder().extract_evidence(
            validation_result={"success": False},
        )
        assert set(ev[0].keys()) == {"source", "field", "observation"}


# ==================================================================
# PlanningTrace — record / 落盘 / 脱敏 / 失败安全
# ==================================================================


class TestPlanningTraceRecord:
    def test_record_returns_whitelist_fields(self, tmp_path):
        tr = PT.PlanningTrace(file=tmp_path / "planning_trace.json")
        rec = tr.record(operation="analyze_gap", provider="deepseek",
                        model="deepseek-chat", input_hash="abc123")
        for k in PT.ALLOWED_KEYS:
            assert k in rec, f"记录缺字段: {k}"
        assert "trace_id" in rec
        assert "timestamp" in rec
        assert rec["operation"] == "analyze_gap"
        assert rec["provider"] == "deepseek"

    def test_record_unknown_keys_not_stored(self, tmp_path):
        tr = PT.PlanningTrace(file=tmp_path / "planning_trace.json")
        rec = tr.record(operation="x", provider="p", model="m",
                        input_hash="h")
        # 顶层字段白名单: 只允许 ALLOWED_KEYS + trace_id/timestamp
        assert set(rec.keys()) == set(PT.ALLOWED_KEYS) | {
            "trace_id", "timestamp",
        }

    def test_record_appends_to_file(self, tmp_path):
        f = tmp_path / "planning_trace.json"
        tr = PT.PlanningTrace(file=f)
        tr.record(operation="propose_task", provider="anthropic", model="claude")
        tr.record(operation="evaluate_plan", provider="deepseek", model="m")
        data = json.loads(f.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) == 2
        assert [r["operation"] for r in data] == [
            "propose_task", "evaluate_plan",
        ]

    def test_record_confidence_rounded(self, tmp_path):
        tr = PT.PlanningTrace(file=tmp_path / "planning_trace.json")
        rec = tr.record(operation="x", confidence=0.876)
        assert rec["confidence"] == 0.88

    def test_record_token_usage_normalized(self, tmp_path):
        tr = PT.PlanningTrace(file=tmp_path / "planning_trace.json")
        rec = tr.record(
            operation="x",
            token_usage={"input_tokens": 100, "output_tokens": 50},
        )
        assert rec["token_usage"] == {
            "input_tokens": 100, "output_tokens": 50, "total_tokens": 0,
        }

    def test_record_token_usage_int(self, tmp_path):
        tr = PT.PlanningTrace(file=tmp_path / "planning_trace.json")
        rec = tr.record(operation="x", token_usage=77)
        assert rec["token_usage"] == {
            "input_tokens": 0, "output_tokens": 77, "total_tokens": 77,
        }

    def test_record_latency_float(self, tmp_path):
        tr = PT.PlanningTrace(file=tmp_path / "planning_trace.json")
        rec = tr.record(operation="x", latency=1.23456)
        assert rec["latency"] == 1.2346
        assert isinstance(rec["latency"], float)

    def test_record_fallback_used_bool(self, tmp_path):
        tr = PT.PlanningTrace(file=tmp_path / "planning_trace.json")
        assert tr.record(operation="x", fallback_used=True)["fallback_used"] is True
        assert tr.record(operation="x")["fallback_used"] is False

    def test_record_with_input_computes_hash_only(self, tmp_path):
        tr = PT.PlanningTrace(file=tmp_path / "planning_trace.json")
        rec = tr.record(operation="x", input={"secret_payload": "raw-内容"})
        assert rec["input_hash"]
        assert rec["input_hash"] == PT.PlanningTrace.hash_input(
            {"secret_payload": "raw-内容"}
        )
        assert "raw-内容" not in json.dumps(rec, ensure_ascii=False)

    def test_hash_input_deterministic(self):
        assert PT.PlanningTrace.hash_input({"a": 1}) == PT.PlanningTrace.hash_input(
            {"a": 1}
        )
        assert PT.PlanningTrace.hash_input({"a": 1}) != PT.PlanningTrace.hash_input(
            {"a": 2}
        )


class TestPlanningTraceSanitize:
    def test_sanitize_removes_api_key(self):
        out = PT.PlanningTrace.sanitize({"api_key": "sk-1", "name": "ok"})
        assert out == {"name": "ok"}

    def test_sanitize_removes_secret_password(self):
        out = PT.PlanningTrace.sanitize(
            {"client_secret": "s", "password": "p", "auth_token": "t"}
        )
        assert out == {}

    def test_sanitize_nested_dict(self):
        out = PT.PlanningTrace.sanitize(
            {"provider": "deepseek", "config": {"api_key": "sk-2", "timeout": 30}}
        )
        assert out == {"provider": "deepseek", "config": {"timeout": 30}}

    def test_sanitize_list_recursive(self):
        out = PT.PlanningTrace.sanitize(
            [{"api_key": "k"}, {"secret": "s", "ok": 1}]
        )
        assert out == [{}, {"ok": 1}]

    def test_sanitize_keeps_token_usage_counts(self):
        out = PT.PlanningTrace.sanitize(
            {"input_tokens": 5, "output_tokens": 3}
        )
        assert out == {"input_tokens": 5, "output_tokens": 3}

    def test_record_redacts_output_and_parsed_result(self, tmp_path):
        tr = PT.PlanningTrace(file=tmp_path / "planning_trace.json")
        rec = tr.record(
            operation="x",
            output={"answer": "ok", "api_key": "sk-leak"},
            parsed_result={"gap_type": "missing_test", "secret": "hide"},
        )
        assert rec["output"] == {"answer": "ok"}
        assert rec["parsed_result"] == {"gap_type": "missing_test"}

    def test_file_contains_no_sensitive_strings(self, tmp_path):
        f = tmp_path / "planning_trace.json"
        tr = PT.PlanningTrace(file=f)
        tr.record(
            operation="x",
            output={"api_key": "sk-leak-123", "name": "ok"},
            validation_result={"secret": "s", "success": True},
        )
        content = f.read_text(encoding="utf-8")
        assert "sk-leak-123" not in content
        assert "api_key" not in content
        assert "secret" not in content


class TestPlanningTraceFailSafe:
    def test_load_missing_file_returns_empty(self, tmp_path):
        tr = PT.PlanningTrace(file=tmp_path / "nope.json")
        assert tr.load() == []

    def test_load_corrupt_file_returns_empty(self, tmp_path):
        f = tmp_path / "planning_trace.json"
        f.write_text("{not json", encoding="utf-8")
        tr = PT.PlanningTrace(file=f)
        assert tr.load() == []

    def test_load_non_list_returns_empty(self, tmp_path):
        f = tmp_path / "planning_trace.json"
        f.write_text('{"a": 1}', encoding="utf-8")
        tr = PT.PlanningTrace(file=f)
        assert tr.load() == []

    def test_save_fail_safe_when_path_is_dir(self, tmp_path):
        d = tmp_path / "blocked.json"
        d.mkdir()
        tr = PT.PlanningTrace(file=d)
        rec = tr.record(operation="x")  # 落盘失败但不抛
        assert rec["operation"] == "x"
        assert tr.load() == []

    def test_records_for_filters_operation(self, tmp_path):
        tr = PT.PlanningTrace(file=tmp_path / "planning_trace.json")
        tr.record(operation="analyze_gap")
        tr.record(operation="propose_task")
        assert len(tr.records_for("analyze_gap")) == 1

    def test_for_project_path(self, tmp_path):
        tr = PT.PlanningTrace.for_project(tmp_path / "slug")
        assert tr.records_file().name == "planning_trace.json"

    def test_records_file_returns_path(self, tmp_path):
        f = tmp_path / "pt.json"
        assert PT.PlanningTrace(file=f).records_file() == f

    def test_record_roundtrip_via_load(self, tmp_path):
        f = tmp_path / "planning_trace.json"
        tr = PT.PlanningTrace(file=f)
        tr.record(operation="evaluate_plan", provider="openai", model="gpt-x",
                  confidence=0.9, fallback_used=True)
        recs = tr.previous_records()
        assert len(recs) == 1
        assert recs[0]["provider"] == "openai"
        assert recs[0]["confidence"] == 0.9
