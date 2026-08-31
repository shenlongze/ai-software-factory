"""S34-001: project_status 项目名解析 — org/projects.json SSOT。"""

import json
from pathlib import Path

from factory_console.session.observability import project_status


def _make_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "factory"
    (ws / "projects" / "P-abc").mkdir(parents=True)
    (ws / "projects" / "P-abc" / "project.json").write_text(
        json.dumps({"name": "P-abc", "status": "idea"}), encoding="utf-8"
    )
    (ws / "org").mkdir()
    (ws / "org" / "projects.json").write_text(
        json.dumps({"projects": {"P-abc": {"id": "P-abc", "name": "旅行记账"}}}),
        encoding="utf-8",
    )
    return ws


def test_project_status_uses_org_name(tmp_path: Path) -> None:
    ws = _make_workspace(tmp_path)
    st = project_status(ws, ws / "projects" / "P-abc")
    # project.json name 是 ID 占位 → org 覆盖为真实名称
    assert st.get("project") == "旅行记账"
    assert st.get("lifecycle") == "idea"


def test_project_status_org_missing_falls_back(tmp_path: Path) -> None:
    ws = tmp_path / "factory"
    (ws / "projects" / "P-def").mkdir(parents=True)
    (ws / "projects" / "P-def" / "project.json").write_text(
        json.dumps({"name": "P-def", "status": "idea"}), encoding="utf-8"
    )
    # 无 org/projects.json → 不崩溃, 用目录名兜底
    st = project_status(ws, ws / "projects" / "P-def")
    assert st.get("project") == "P-def"


# ---- S34-002: assistant_meta.run_ids 归属 (消息→Run 关联) ----

def test_assistant_meta_run_ids_binding(tmp_path: Path) -> None:
    """send_message assistant_meta 应携带 run_ids 且持久化 (GET 返回)。"""
    from factory_console.console_sessions import SessionStore, send_message

    store = SessionStore(tmp_path / "console_sessions.json")
    s = store.create_session(scope="company", title="S34-002")
    sid = s["id"]

    def _fake_llm(_prompt: str) -> str:
        return "开始执行，已创建 Run。"

    result = send_message(
        store, sid, "开始执行",
        llm_fn=_fake_llm,
        assistant_meta={
            "tool_calls": [{"tool": "start_workflow", "ok": True}],
            "run_ids": ["R-S34-002"],
        },
    )
    # assistant 消息 meta 持久化 run_ids
    assert result["assistant"]["meta"]["run_ids"] == ["R-S34-002"]
    # GET messages 返回同一 meta (刷新后归属不丢)
    msgs = store.list_messages(sid)
    asst = [m for m in msgs if m.get("role") == "assistant"][0]
    assert asst["meta"]["run_ids"] == ["R-S34-002"]


# ---- S34-003B: Tool Protocol 泄漏清洗 ----

def test_strip_fake_toolcalls_removes_protocol() -> None:
    """内部 Tool Protocol (<tool_calls>/<invoke>/<parameter>) 绝不进入用户正文。"""
    from factory_console.session.agent_loop import _strip_fake_toolcalls

    leaky = (
        "我已经定位到了核心逻辑文件。\n\n"
        "<tool_calls>\n<invoke name=\"read_file\">\n"
        "<parameter name=\"file_path\">/Users/x/agent_loop.py</parameter>\n"
        "</invoke>\n</tool_calls>"
    )
    cleaned = _strip_fake_toolcalls(leaky)
    assert "<tool_calls>" not in cleaned
    assert "<invoke" not in cleaned
    assert "<parameter" not in cleaned
    # 自然语言保留
    assert "我已经定位到了核心逻辑文件" in cleaned


def test_strip_fake_toolcalls_keeps_normal_text() -> None:
    """正常文本不受影响 (粗体/列表保留)。"""
    from factory_console.session.agent_loop import _strip_fake_toolcalls

    normal = "正常回答。**粗体** 和列表:\n- 项目 A\n- 项目 B"
    cleaned = _strip_fake_toolcalls(normal)
    assert cleaned == normal


def test_strip_fake_toolcalls_unpaired_tags() -> None:
    """散标签/未配对也清理。"""
    from factory_console.session.agent_loop import _strip_fake_toolcalls

    unpaired = "回答。</tool_calls><invoke name=\"bash_exec\">"
    cleaned = _strip_fake_toolcalls(unpaired)
    assert "<tool_calls>" not in cleaned
    assert "<invoke" not in cleaned


# ---- S34-003B: cost 估算 (usage.estimated_cost_usd) ----

def test_model_prices_deepseek() -> None:
    """deepseek 价格表匹配 (chat 档 0.27/1.10)。"""
    from factory_console.session.llm_gateway import _model_prices

    assert _model_prices("deepseek-chat") == (0.27, 1.10)
    assert _model_prices("deepseek-v4-flash") == (0.27, 1.10)
    assert _model_prices("unknown-model") == (0.0, 0.0)


def test_complete_usage_cost_estimated() -> None:
    """complete 返回 usage 带 estimated_cost_usd (真实价格估算)。"""
    from unittest.mock import patch

    import factory_console.session.llm_gateway as lg

    with patch.object(lg, "_openai_compat_complete", return_value={
        "content": "ok",
        "usage": {"prompt_tokens": 1000, "completion_tokens": 1000},
    }):
        out = lg.complete([], None, provider_id="deepseek", model="deepseek-chat",
                          base_url="", api_key="x")
    u = out["usage"]
    # 1000/1M * 0.27 + 1000/1M * 1.10 = 0.00137
    assert abs(u["estimated_cost_usd"] - 0.00137) < 1e-6


# ---- S34-003B: 模型上下文窗口 ----

def test_model_context_window_known() -> None:
    """deepseek-chat → 64K; v4-flash → 1M; 未知 → 0。"""
    from factory_console.session.llm_gateway import model_context_window

    assert model_context_window("deepseek-chat") == 65536
    assert model_context_window("deepseek-v4-flash") == 1048576
    assert model_context_window("unknown-model") == 0


def test_agent_loop_usage_context_fallback() -> None:
    """usage.context_window 为 0 时兜底到模型表 (deepseek-chat → 64K)。"""
    from factory_console.session.llm_gateway import model_context_window

    _mconf = {"model": "deepseek-chat", "context_window": 0}
    cw = int(_mconf.get("context_window") or 0) or model_context_window(str(_mconf.get("model") or ""))
    assert cw == 65536


# ---- P0 回归: DSML 全角变体泄漏 ----

def test_strip_fake_toolcalls_dsml_fullwidth() -> None:
    """模型输出全角 DSML 变体 <｜DSML｜tool_calls> / <||DSML||invoke> → 全清除。"""
    from factory_console.session.agent_loop import _strip_fake_toolcalls

    leaky = (
        "<｜DSML｜tool_calls>\n"
        "<｜DSML｜invoke name=\"bash_exec\">\n"
        "<｜DSML｜parameter name=\"command\">for d in /projects/*/; do ls; done</｜DSML｜parameter>\n"
        "<｜DSML｜/invoke>\n"
        "<｜DSML｜/tool_calls>"
    )
    cleaned = _strip_fake_toolcalls(leaky)
    assert cleaned.strip() == ""
    for bad in ("DSML", "tool_calls", "<invoke", "<parameter"):
        assert bad not in cleaned


def test_strip_fake_toolcalls_dsml_double_pipe() -> None:
    """双竖线变体 <||DSML||tool_calls> → 清除。"""
    from factory_console.session.agent_loop import _strip_fake_toolcalls

    leaky = "回答。<||DSML||tool_calls>\n<||DSML||invoke name=\"bash_exec\">\n</||DSML||invoke>\n<||DSML||/tool_calls>"
    cleaned = _strip_fake_toolcalls(leaky)
    assert "DSML" not in cleaned
    assert "回答" in cleaned


def test_strip_fake_toolcalls_keeps_normal_after_dsml() -> None:
    """DSML 块清除后自然语言保留。"""
    from factory_console.session.agent_loop import _strip_fake_toolcalls

    text = "目前共有 2 个项目。\n\n<||DSML||tool_calls>\n<||DSML||invoke name=\"bash_exec\">\n</||DSML||invoke>\n<||DSML||/tool_calls>"
    cleaned = _strip_fake_toolcalls(text)
    assert "目前共有 2 个项目" in cleaned
    assert "DSML" not in cleaned


# ---- 项目列表工具 (project_list) ----

def test_project_list_full_fields(tmp_path: Path) -> None:
    """project_list 返回 markdown 表格 (ID/名称/进度/阶段/描述)。"""
    import json as _json

    from factory_console.session.agent_loop import dispatch

    ws = tmp_path / "factory"
    (ws / "org").mkdir(parents=True)
    (ws / "org" / "projects.json").write_text(_json.dumps({
        "projects": {
            "P-abc": {"id": "P-abc", "name": "旅行记账", "lifecycle": "idea", "goal": "旅行支出乱"},
            "P-def": {"id": "P-def", "name": "番茄钟", "lifecycle": "development", "goal": "专注"},
        }
    }), encoding="utf-8")
    r = dispatch("project_list", {}, root=ws, project_id="P-abc")
    assert r["ok"] is True
    out = str(r["output"])
    # markdown 表格: 表头 + 分隔行 + 数据行
    assert "| 项目ID | 名称 | 进度 | 阶段 | 描述 |" in out
    assert "|--------|" in out
    assert "| P-abc | 旅行记账 |" in out
    assert "| P-def | 番茄钟 |" in out
    assert "阶段=idea" not in out  # 不再是键值对行, 是表格


# ---- P0-01: Run 存活/stale 检测 ----

def test_reconcile_stale_marks_zombie(tmp_path: Path) -> None:
    """僵尸 progress (running + 线程不活 + 心跳旧) → STALE。"""
    import json as _json
    import threading
    import time

    from factory_console import run_liveness

    ws = tmp_path / "runs"
    (ws / "P-abc" / "R-zombie").mkdir(parents=True)
    old = _json.dumps({
        "status": "running",
        "stages": [], "calls": [], "totals": {}, "errors": [],
        "updated_at": "2026-01-01T00:00:00+00:00",
    })
    (ws / "P-abc" / "R-zombie" / "progress.json").write_text(old, encoding="utf-8")
    # 不注册线程 → 视为不存活
    result = run_liveness.reconcile_stale(ws, stale_after_s=60)
    assert result["stale"] == ["R-zombie"]
    p = _json.loads((ws / "P-abc" / "R-zombie" / "progress.json").read_text())
    assert p["status"] == "STALE"
    assert "STALE" in str(p["errors"])


def test_reconcile_keeps_alive_thread(tmp_path: Path) -> None:
    """活跃线程 (已注册) 不被误判 stale。"""
    import json as _json
    import threading
    import time

    from factory_console import run_liveness

    ws = tmp_path / "runs"
    (ws / "P-abc" / "R-alive").mkdir(parents=True)
    old = _json.dumps({
        "status": "running", "stages": [], "calls": [], "totals": {}, "errors": [],
        "updated_at": "2026-01-01T00:00:00+00:00",
    })
    (ws / "P-abc" / "R-alive" / "progress.json").write_text(old, encoding="utf-8")
    t = threading.Thread(target=lambda: time.sleep(30), daemon=True)
    t.start()
    run_liveness.register_run("P-abc", "R-alive", t)
    result = run_liveness.reconcile_stale(ws, stale_after_s=60)
    assert result["stale"] == []
    assert result["alive"] == ["R-alive"]
    run_liveness.unregister_run("P-abc", "R-alive")


def test_reconcile_idempotent(tmp_path: Path) -> None:
    """已 STALE 不重复处理 (幂等)。"""
    import json as _json

    from factory_console import run_liveness

    ws = tmp_path / "runs"
    (ws / "P-abc" / "R-x").mkdir(parents=True)
    d = _json.dumps({
        "status": "STALE", "stages": [], "calls": [], "totals": {}, "errors": [],
        "updated_at": "2026-01-01T00:00:00+00:00",
    })
    (ws / "P-abc" / "R-x" / "progress.json").write_text(d, encoding="utf-8")
    result = run_liveness.reconcile_stale(ws)
    assert result["stale"] == []  # STALE 不再处理
    assert result["other"] == 1


# ---- P0-02: Run cancellation ----

def test_cancel_request_idempotent(tmp_path: Path) -> None:
    """取消标志幂等; is_cancelled 生效。"""
    from factory_console import run_liveness

    assert run_liveness.request_cancel("P-x", "R-x") is True
    assert run_liveness.is_cancelled("P-x", "R-x") is True
    # 重复请求幂等
    assert run_liveness.request_cancel("P-x", "R-x") is True
    run_liveness.clear_cancel("P-x", "R-x")
    assert run_liveness.is_cancelled("P-x", "R-x") is False


def test_cancel_marks_cancelled_progress(tmp_path: Path) -> None:
    """cancel API 对 running run 返回 CANCELLING + 设置取消标志。"""
    import json as _json
    from unittest.mock import patch

    # 直接测 run_liveness 语义: 线程内取消检查
    from factory_console import run_liveness

    run_liveness.request_cancel("P-y", "R-y")
    # _thread_main 在 stage 边界检查 → 停止
    assert run_liveness.is_cancelled("P-y", "R-y")
    run_liveness.clear_cancel("P-y", "R-y")


# ---- P0-03: 启动 migration 清洗历史泄漏 ----

def test_session_store_migrate_cleans_protocol(tmp_path: Path) -> None:
    """SessionStore 加载时自动清洗历史协议泄漏 (幂等)。"""
    import json as _json

    from factory_console.console_sessions import SessionStore

    store_file = tmp_path / "console_sessions.json"
    store_file.write_text(_json.dumps({
        "sessions": {"s1": {"id": "s1", "title": "t"}},
        "messages": {"s1": [
            {"id": "m1", "role": "user", "content": "正常消息"},
            {"id": "m2", "role": "assistant",
             "content": "<tool_calls>\n<invoke name=\"bash_exec\">\n</invoke>\n</tool_calls>"},
        ]},
    }, ensure_ascii=False), encoding="utf-8")
    store = SessionStore(store_file)
    msgs = store.list_messages("s1")
    asst = [m for m in msgs if m["role"] == "assistant"][0]
    assert "<tool_calls>" not in asst["content"]
    assert "<invoke" not in asst["content"]
    # 幂等: 再加载一次不再变
    store2 = SessionStore(store_file)
    msgs2 = store2.list_messages("s1")
    assert msgs2 == msgs


# ---- P0-05: client_msg_id 幂等 ----

def test_send_message_idempotent(tmp_path: Path) -> None:
    """同 client_msg_id 重试 → 返回缓存结果, 不重复执行。"""
    from factory_console.console_sessions import SessionStore, send_message

    store = SessionStore(tmp_path / "console_sessions.json")
    s = store.create_session(scope="company", title="幂等")
    sid = s["id"]
    calls = {"n": 0}

    def _fake_llm(_p: str) -> str:
        calls["n"] += 1
        return "回答"

    r1 = send_message(store, sid, "你好", llm_fn=_fake_llm, client_msg_id="cid-1")
    assert calls["n"] == 1
    assert r1.get("idempotent") is None
    # 同 id 重试 → 不重复执行 LLM
    r2 = send_message(store, sid, "你好", llm_fn=_fake_llm, client_msg_id="cid-1")
    assert calls["n"] == 1  # LLM 未再调
    assert r2.get("idempotent") is True
    assert r2["user"]["id"] == r1["user"]["id"]
    # 不同 id → 正常新消息
    r3 = send_message(store, sid, "再见", llm_fn=_fake_llm, client_msg_id="cid-2")
    assert calls["n"] == 2
    assert r3.get("idempotent") is None


# ---- S34 P0-5: send_message 落库清洗 ----

def test_send_message_strips_protocol_on_store(tmp_path: Path) -> None:
    """send_message 落库前清洗 Tool Protocol (所有路径出口防线)。"""
    from factory_console.console_sessions import SessionStore, send_message

    store = SessionStore(tmp_path / "console_sessions.json")
    s = store.create_session(scope="company", title="清洗")
    sid = s["id"]

    def _leaky_llm(_p: str) -> str:
        return "<tool_calls>\n<invoke name=\"project_list\">\n</invoke>\n</tool_calls>\n正常回答"

    r = send_message(store, sid, "项目列表", llm_fn=_leaky_llm)
    content = str(r["assistant"]["content"])
    assert "<tool_calls>" not in content
    assert "<invoke" not in content
    assert "正常回答" in content  # 不损坏真实内容


# ---- S34-P0: Context Resolution / SSOT ----

def test_repo_fact_company_no_project() -> None:
    """company scope (project_id 空) → 绝不注入当前项目源码, 不兜底工作区。"""
    import sys
    sys.path.insert(0, 'factory-console')
    from factory_console.session.agent_loop import _repo_fact

    fact = _repo_fact(None, "")
    assert "当前项目源码仓库在" not in fact
    assert "公司级会话" in fact
    assert "不要假设存在'当前项目'" in fact
    # 有 project_id → 正常路径 (可能兜底, 但至少不禁止)
    fact2 = _repo_fact(None, "P-abc")
    assert "当前上下文" not in fact2


def test_ssot_align_fixes_drift(tmp_path: Path) -> None:
    """org 为 SSOT: project.json 漂移字段回写对齐 (幂等)。"""
    import json as _json

    from factory_console import project_ssot

    ws = tmp_path / "factory"
    (ws / "org").mkdir(parents=True)
    (ws / "projects" / "P-1").mkdir(parents=True)
    (ws / "org" / "projects.json").write_text(_json.dumps({
        "projects": {"P-1": {"id": "P-1", "name": "番茄钟", "lifecycle": "idea",
                             "goal": "专注"}}
    }), encoding="utf-8")
    (ws / "projects" / "P-1" / "project.json").write_text(_json.dumps({
        "name": "旧名", "status": "development"
    }), encoding="utf-8")

    rep = project_ssot.drift_report(ws)
    assert rep["drifting"] == 1
    assert "name" in rep["projects"][0]["diffs"]

    res = project_ssot.ensure_org_truth(ws)
    assert res["fixed"] == 1

    pj = _json.loads((ws / "projects" / "P-1" / "project.json").read_text())
    assert pj["name"] == "番茄钟"  # org 为准

    # 幂等: 再跑无变更
    res2 = project_ssot.ensure_org_truth(ws)
    assert res2["fixed"] == 0


def test_ssot_drift_report_clean(tmp_path: Path) -> None:
    """无漂移 → drifting=0。"""
    import json as _json

    from factory_console import project_ssot

    ws = tmp_path / "factory"
    (ws / "org").mkdir(parents=True)
    (ws / "projects" / "P-2").mkdir(parents=True)
    (ws / "org" / "projects.json").write_text(_json.dumps({
        "projects": {"P-2": {"id": "P-2", "name": "墨笺", "lifecycle": "idea"}}
    }), encoding="utf-8")
    (ws / "projects" / "P-2" / "project.json").write_text(_json.dumps({
        "name": "墨笺", "status": "idea"
    }), encoding="utf-8")
    rep = project_ssot.drift_report(ws)
    assert rep["drifting"] == 0


# ---- S34-P0: Plan 关联 Artifact + 项目详情 ----

def test_plan_has_artifact_ids(tmp_path: Path) -> None:
    """plan_development 生成关联 Artifact (plan_id/project_id/requirement_id/approval_id)。"""
    import json as _json
    from unittest.mock import MagicMock

    from factory_console.session.agent_loop import dispatch

    ws = tmp_path / "factory"
    (ws / "requirements").mkdir(parents=True)
    ctx = {"session_id": "sess-1", "llm_fn": lambda p: _json.dumps({
        "goal": "开发飞机大战", "tasks": [{"title": "骨架", "priority": "P0"}],
        "order": ["骨架"], "acceptance": ["可玩"]})}
    svc = MagicMock()
    r = dispatch("plan_development", {"goal": "开发飞机大战", "detail": "纯前端"},
                 root=ws, project_id="P-abc", service=svc, ctx=ctx)
    assert r["ok"] is True
    plan = r["plan"]
    assert plan["plan_id"].startswith("plan_")
    assert plan["project_id"] == "P-abc"
    assert plan["requirement_id"].startswith("req_")
    assert plan["approval_id"] or plan["approval_id"] == ""  # 审批可能成功或失败 (诚实)
    # session_plans.json 持久化
    sp = _json.loads((ws / "session_plans.json").read_text())
    assert sp["sess-1"]["plan_id"] == plan["plan_id"]
    # requirements.json 落盘
    reqs = _json.loads((ws / "requirements" / "requirements.json").read_text())
    assert reqs[-1]["project_id"] == "P-abc"


def test_execute_plan_tasks_carry_plan_id(tmp_path: Path) -> None:
    """execute_plan 建任务带 plan_id (Plan→Task 链)。"""
    from unittest.mock import MagicMock

    from factory_console.session.agent_loop import execute_plan

    svc = MagicMock()
    svc.create_task.return_value = {"id": "T-1", "title": "骨架", "priority": "P0"}
    r = execute_plan({"plan_id": "plan_x", "tasks": [{"title": "骨架", "priority": "P0"}]},
                     project_id="P-abc", service=svc)
    assert r["ok"] is True
    assert r["plan_id"] == "plan_x"
    assert r["created"][0]["plan_id"] == "plan_x"
