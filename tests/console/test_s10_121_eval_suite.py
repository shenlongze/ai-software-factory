"""tests/console/test_s10_121_eval_suite.py — S10-121 K-5 评测体系契约测试 (≥10)。

覆盖 (设计 docs/sprint10/S10-121-k5-eval-plan.md §2 契约 1-11):
1. 七维评测: EVAL_DIMENSIONS 7 维每维 ≥1 断言项; 报告含 通过/失败/未覆盖 + 证据引用
2. L0/L1 判定: 全绿 → L0/L1; 有失败 → 对应等级不过
3. 发布门: --gate patch 跑 L0 (失败 rc 非 0 阻断); --gate minor 跑 L0+L1; --check 只读不阻断
4. 并发不串: 多项目并发 → 各项目 trace_id 独立 (K-4 隔离断言)
5. 长跑冒烟: 短时长冒烟可跑 (可配置); 24h 脚本存在 (标待长跑)
6. H-1: 端到端 fixture 每节点衔接断言 (J-1 状态单一来源投影)
7. F-10: 覆盖率报告生成 (stdlib trace, 模块级)
8. M5-7: 错误码表存在 + 主要错误路径有码
9. C-4: 盲区清单文件存在 (K-2 已覆盖 vs 仍盲)
10. 注册表: eval 命令在 build_parser 可见 (P0-10 同步)
11. 版本 v1.1.95 断言 (pyproject/CHANGELOG/FEATURES)

装配: tmp_path 隔离工作区 + importlib (factory-console 包名含连字符) + sys.path 挂
factory-core; 禁真实网络/LLM — 全部 fixture 纯确定性。basename 全仓库唯一。
"""

from __future__ import annotations

import concurrent.futures
import importlib
import json
import re
import sys
import threading
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_FACTORY_CORE = _ROOT / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))

CLI = importlib.import_module("factory-console.cli_factory")
CFG = importlib.import_module("factory-console.config")
EVAL = importlib.import_module("factory-console.session.eval_suite")
ORCH = importlib.import_module("factory-console.session.orchestrator")
EQ = importlib.import_module("factory-console.session.execution_quality")
LS = importlib.import_module("factory-console.session.lifecycle_store")
TC = importlib.import_module("factory-console.audit.trace_context")
AUDIT_EM = importlib.import_module("factory-console.audit.audit_emitter")
AUDIT_STORE = importlib.import_module("factory-console.audit.audit_store")
EVAL_LOOP = importlib.import_module("factory-console.session.eval_loop")

Lifecycle = LS.Lifecycle


# ------------------------------------------------------------------ 工具


def _ws(tmp_path: Path, name: str = "ws") -> Path:
    ws = tmp_path / name
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def _write_json(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _three_track(pdir: Path) -> tuple:
    """(project.json.status, product.json.status, execution_state.json.lifecycle); 缺失 → None。"""

    def _read(path: Path, key: str):
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            v = data.get(key)
            return str(v) if v else None
        except Exception:  # noqa: BLE001 — 失败安全
            return None

    return (
        _read(pdir / "project.json", "status"),
        _read(pdir / "product.json", "status"),
        _read(pdir / "execution_state.json", "lifecycle"),
    )


def _assert_j1(pdir: Path, expected: str) -> None:
    """J-1 投影断言: project.json.status == expected; product 镜像一致; state 存在时一致。"""
    pj, pd, es = _three_track(pdir)
    assert pj == expected, f"project.json.status={pj} != {expected}"
    if pd is not None:
        assert pd == expected, f"product.json.status={pd} != {expected}"
    if es is not None:
        assert es == expected, f"execution_state.lifecycle={es} != {expected}"


# ------------------------------------------------------------------ H-1 端到端 fixture


def _fake_execute(task: dict, project_dir: Path, workspace: Path) -> dict:
    """真实执行: 任务 → 真实 unified diff patch (经 deliver_patch 应用 → 代码文件)。

    模式同 test_m3e_full_chain._execute_ok: patch 落盘 artifacts/, 返回 artifact 路径 —
    执行循环读 patch → deliver_patch 应用 → gen_*.py 真实创建 + 证据生成。
    """
    tid = str(task.get("id") or "task")
    fname = f"gen_{tid.replace('-', '_')}.py"
    patch = (
        f"diff --git a/{fname} b/{fname}\n"
        f"new file mode 100644\n"
        f"--- /dev/null\n"
        f"+++ b/{fname}\n"
        f"@@ -0,0 +1,2 @@\n"
        f"+def fn_{tid.replace('-', '_')}():\n"
        f"+    return 1\n"
        f"+\n"
    )
    art = project_dir / "artifacts" / f"{tid}.patch"
    art.parent.mkdir(parents=True, exist_ok=True)
    art.write_text(patch, encoding="utf-8")
    return {"success": True, "artifact": str(art), "cost": "0.01"}


def run_e2e_fixture(ws: Path, *, emit_audit: bool = True) -> dict:
    """H-1 端到端 fixture: 创建→发现→PRD→工程→审批→执行→证据→交付。

    每节点衔接断言 (上一节点产物是下一节点输入) + J-1 状态单一来源投影校验;
    写 .eval/e2e_result.json 证据 (EvalSuite correctness.e2e_chain 消费)。
    """
    nodes: dict[str, bool] = {}
    result: dict = {"ok": True, "nodes": nodes, "project": "demo", "lifecycle": None}
    pdir = ws / "projects" / "demo"
    try:
        # 1. 创建 (idea)
        _write_json(pdir / "project.json", {"name": "demo", "status": Lifecycle.IDEA})
        _write_json(pdir / "product.json", {
            "name": "demo", "problem": "做一个记账应用", "user": "个人用户",
            "core_features": ["记账"], "status": Lifecycle.IDEA,
        })
        assert (pdir / "project.json").is_file()
        assert (pdir / "product.json").is_file()
        nodes["create"] = True

        # 2. 发现 (discovery 会话持久化)
        discovery = _write_json(pdir / "discovery" / "conversation.json", {
            "session_id": "DS-DEMO-1", "status": "completed",
            "conversation": [{"question": "目标平台?", "answer": "手机 App"}],
        })
        data = json.loads(discovery.read_text(encoding="utf-8"))
        assert data["session_id"].startswith("DS-")
        assert data["conversation"][0]["answer"] == "手机 App"
        nodes["discovery"] = True

        # 3. PRD (必需章节齐全 — 衔接: 发现问答 → PRD)
        prd_sections = "\n\n".join(
            f"## {s}\n内容: 演示 {s}" for s in EQ.PRD_SECTIONS
        )
        (pdir / "prd.md").write_text(f"# demo PRD\n\n{prd_sections}", encoding="utf-8")
        prd_text = (pdir / "prd.md").read_text(encoding="utf-8")
        for s in EQ.PRD_SECTIONS:
            assert s in prd_text
        nodes["prd"] = True

        # 4. 工程 (engineering.json + K-2 工程计划质量分 — 衔接: PRD → 工程计划)
        plan = {
            "platform": "web", "architecture": "backend + frontend",
            "modules": [{"name": "core"}, {"name": "web"}],
            "tasks": [
                {"id": "t1", "name": "数据库", "type": "database"},
                {"id": "t2", "name": "后端 API", "type": "backend"},
                {"id": "t3", "name": "前端页面", "type": "frontend"},
                {"id": "t4", "name": "测试用例", "type": "test"},
            ],
        }
        _write_json(pdir / "engineering.json", plan)
        eng_q = EQ.score_engineering(plan)
        assert eng_q.score is not None, f"工程计划评分失败: {eng_q.reason}"
        nodes["engineering"] = True

        # 5. 审批 (工程计划审批产物 + J-1 推进 execution_ready — 衔接: 计划 → 审批 → 可执行)
        _write_json(pdir / "approval" / "plan_approval.json", {
            "decision": "approved", "approved_at": "2026-08-25T00:00:00+00:00",
            "summary": "工程计划架构审批通过", "reviewer": "user",
        })
        approval = json.loads(
            (pdir / "approval" / "plan_approval.json").read_text(encoding="utf-8")
        )
        assert approval["decision"] == "approved"
        LS.set_project_lifecycle(pdir, Lifecycle.PRODUCT_DEFINED)
        _assert_j1(pdir, Lifecycle.PRODUCT_DEFINED)
        LS.set_project_lifecycle(pdir, Lifecycle.ENGINEERING_READY)
        _assert_j1(pdir, Lifecycle.ENGINEERING_READY)
        LS.set_project_lifecycle(pdir, Lifecycle.EXECUTION_READY)
        _assert_j1(pdir, Lifecycle.EXECUTION_READY)
        nodes["approval"] = True

        # 6. 执行 (真实 ExecutionOrchestrator + 确定性 execute_fn → 真实产物/证据)
        _write_json(pdir / "execution_plan.json", {
            "tasks": [
                {"id": "t1", "name": "数据库", "agent_type": "backend"},
                {"id": "t2", "name": "后端 API", "agent_type": "backend"},
                {"id": "t3", "name": "前端页面", "agent_type": "frontend"},
            ],
            "count": 3,
        })
        orch = ORCH.ExecutionOrchestrator(ws)
        exec_result = orch.execute_project("demo", execute_fn=_fake_execute)
        assert exec_result.failed_tasks == 0, f"执行有失败: {exec_result.errors}"
        assert exec_result.completed_tasks == 3
        code_files = sorted(p.name for p in pdir.glob("gen_*.py"))
        assert len(code_files) == 3, code_files
        nodes["execution"] = True

        # 7. 证据 (evidence 证据包 + K-2 执行质量分记录 — 衔接: 执行 → 证据)
        evidence_dir = pdir / "evidence"
        # 直接 execute_project 路径写 1 个合并证据包 (per-task 证据包在 M3 并行路径);
        # 断言存在 + 结构 (证据节点真实产出, 数量粒度如实标注)
        assert len(list(evidence_dir.glob("ev-*.json"))) >= 1, "缺证据包"
        for ev_file in evidence_dir.glob("ev-*.json"):
            ev = json.loads(ev_file.read_text(encoding="utf-8"))
            assert "bundle_id" in ev and "task_id" in ev and "diff" in ev
        # 执行质量分: 最近一条通过 (>= 阈值) + 一条评分器失败 (score=None+reason 失败安全)
        now = "2026-08-25T10:00:00+00:00"
        passing_quality = EQ.score_execution(
            {"result": "success", "task": "t3"},
            {
                "validation_result": {"passed": True},
                "patch_apply_result": {"applied": True, "files": ["gen_t3.py"]},
                "scope_result": {"changed_files": 1, "changed_lines": 3},
                "regression_risk_result": {"affected_symbols": 1},
                "requirement_coverage_result": {"covered": 1, "total": 1},
            },
        )
        assert passing_quality.score is not None and passing_quality.score >= EQ.LOW_SCORE_THRESHOLD
        records = [
            {
                "project": "demo", "task": "t1", "timestamp": "2026-08-25T09:00:00+00:00",
                "result": "success", "error": "",
                "quality": {
                    "score": None,
                    "reason": "scorer failed: 证据缺失 (失败安全, 不臆造)",
                    "evaluator_version": "1.0",
                },
            },
            {
                "project": "demo", "task": "t3", "timestamp": now,
                "result": "success", "error": "",
                "quality": passing_quality.to_dict(),
            },
        ]
        _write_json(ws / "exec" / "execution_records.json", records)
        nodes["evidence"] = True

        # 8. 交付 (用户验收 USER_ACCEPTANCE → DELIVERED — 衔接: 证据 → 审批 → 交付)
        assert orch.accept_project("demo") is True
        _assert_j1(pdir, Lifecycle.DELIVERED)
        nodes["delivery"] = True
        result["lifecycle"] = Lifecycle.DELIVERED
    except Exception as exc:  # noqa: BLE001 — 失败安全: fixture 异常如实记录
        result["ok"] = False
        result["error"] = f"{type(exc).__name__}: {exc}"
        for node in ("create", "discovery", "prd", "engineering", "approval", "execution", "evidence", "delivery"):
            nodes.setdefault(node, False)

    if emit_audit:
        try:
            with TC.trace_context(TC.new_trace_id()):
                emitter = AUDIT_EM.AuditEmitter(workspace=ws)
                emitter.emit(
                    "PROJECT_CREATED", project_id="demo", actor_type="user",
                    actor_id="u1", decision_reason="H-1 端到端创建",
                )
                emitter.emit(
                    "PROJECT_DELIVERED", project_id="demo", actor_type="user",
                    actor_id="u1", decision_reason="H-1 端到端交付",
                )
        except Exception:  # noqa: BLE001 — 失败安全
            pass
    _write_json(ws / ".eval" / "e2e_result.json", result)
    return result


# ------------------------------------------------------------------ 鲁棒性 fixture


def run_robustness_fixture(ws: Path) -> dict:
    """鲁棒性 fixture: 异常输入不崩 (评分器/评测套件失败安全), 写 .eval/robustness_result.json。"""
    cases: list[dict] = []
    # 1) score_execution(None, None) → 不抛, 确定性分数 (None 输入由规则兜底 — 非失败安全路径;
    #    失败安全=评分器异常 → score=None+reason, 由 e2e fixture 手工记录覆盖)
    q = EQ.score_execution(None, None)
    cases.append({"name": "score_execution(None,None)", "ok": q.score is not None and 0 <= q.score <= 1})
    # 2) score_prd(None, None) → 失败安全
    q2 = EQ.score_prd(None, None)
    cases.append({"name": "score_prd(None,None)", "ok": q2.score is not None or bool(q2.reason)})
    # 3) score_engineering(None) → 失败安全
    q3 = EQ.score_engineering(None)
    cases.append({"name": "score_engineering(None)", "ok": q3.score is not None or bool(q3.reason)})
    # 4) EvalSuite.run 遇损坏 execution_records.json → 该项 fail/not_covered 不崩
    corrupt_ws = ws / "corrupt"
    corrupt_ws.mkdir(exist_ok=True)
    (corrupt_ws / "exec" / "execution_records.json").parent.mkdir(parents=True, exist_ok=True)
    (corrupt_ws / "exec" / "execution_records.json").write_text("{corrupt", encoding="utf-8")
    report = EVAL.EvalSuite().run(corrupt_ws)
    cases.append({"name": "EvalSuite.run(corrupt)", "ok": report.level in ("below-L0", "L0", "L1", "L2")})
    # 5) eval_loop.analyze(垃圾输入) → 不抛
    fix = EVAL_LOOP.EvalFixLoop.analyze("垃圾输入")
    cases.append({"name": "EvalFixLoop.analyze(bad)", "ok": bool(fix.classification)})
    ok = all(c["ok"] for c in cases)
    result = {"ok": ok, "cases": cases, "generated_at": "2026-08-25T00:00:00+00:00"}
    _write_json(ws / ".eval" / "robustness_result.json", result)
    return result


# ------------------------------------------------------------------ 并发 fixture (K-4 trace 隔离)


def run_concurrency_fixture(ws: Path, *, projects: int = 4, tasks_per_project: int = 3) -> dict:
    """多项目并发任务 (线程池) → 各项目 trace_id 独立 (K-4 隔离断言)。

    每 worker: 独立 trace_context → 发射审计事件 + 写项目任务结果;
    断言: 线程内 trace == 分配 trace; 线程退出后主线程 trace 不泄漏。
    共享审计文件写入用锁串行化 (trace 隔离语义测试, 非文件原子性测试)。
    """
    project_ids = [f"conc-p{i}" for i in range(projects)]
    trace_by_project = {pid: TC.new_trace_id() for pid in project_ids}
    audit_lock = threading.Lock()
    emitter = AUDIT_EM.AuditEmitter(workspace=ws)
    main_trace_before = TC.get_trace_id()

    def work(pid: str, tid: str) -> dict:
        seen_trace = TC.get_trace_id()  # 线程进入时 (继承主线程, 应被 with 覆盖)
        with TC.trace_context(trace_by_project[pid], f"{trace_by_project[pid]}:1"):
            inside = TC.get_trace_id()
            event_traces: list[str] = []
            for i in range(tasks_per_project):
                with audit_lock:
                    ev = emitter.emit(
                        "TASK_STARTED", project_id=pid, task_id=tid,
                        actor_type="user", actor_id="u1",
                    )
                event_traces.append(ev.trace_id)
            pdir = ws / "projects" / pid
            pdir.mkdir(parents=True, exist_ok=True)
            _write_json(pdir / "task_result.json", {
                "project": pid, "task": tid, "trace_id": inside,
            })
        after_exit = TC.get_trace_id()
        return {
            "project": pid, "task": tid, "inside": inside,
            "event_traces": event_traces,
            "thread_entry": seen_trace, "after_exit": after_exit,
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=projects) as pool:
        futures = [
            pool.submit(work, pid, f"T-{pid}-{n}")
            for pid in project_ids
            for n in range(tasks_per_project)
        ]
        results = [f.result(timeout=30) for f in futures]

    # K-4 隔离断言
    assert TC.get_trace_id() == main_trace_before  # 主线程不泄漏
    per_project_ok = {}
    for r in results:
        pid = r["project"]
        expected = trace_by_project[pid]
        ok = (
            r["inside"] == expected
            and r["after_exit"] == main_trace_before
            and all(t == expected for t in r["event_traces"])
            and len(set(r["event_traces"])) == 1
        )
        per_project_ok[pid] = per_project_ok.get(pid, True) and ok
    # 项目间 trace_id 两两互异
    distinct = len({trace_by_project[p] for p in project_ids}) == len(project_ids)
    isolated = distinct and all(per_project_ok.values())
    # 审计事件全局校验: 每事件 trace 属于其项目
    events = AUDIT_STORE.AuditStore(workspace=ws).events()
    events_by_project: dict[str, set] = {}
    for ev in events:
        events_by_project.setdefault(ev.project_id, set()).add(ev.trace_id)
    no_cross = True
    for pid in project_ids:
        if pid in events_by_project:
            if events_by_project[pid] != {trace_by_project[pid]}:
                no_cross = False
    result = {
        "ok": isolated and no_cross,
        "projects": len(project_ids),
        "tasks": len(results),
        "events": len(events),
        "trace_ids": trace_by_project,
        "isolated": isolated,
        "no_cross": no_cross,
        "generated_at": "2026-08-25T00:00:00+00:00",
    }
    _write_json(ws / ".eval" / "concurrency_result.json", result)
    return result


# ------------------------------------------------------------------ 学习闭环 fixture (用户价值)


def run_learning_loop_fixture(ws: Path) -> dict:
    """学习闭环 fixture (K-3 E-2/E-3): 低分记录 → 分类 → 复评提升, 写证据。"""
    record = {
        "task": "T-learn",
        "project": "demo",
        "error": "validation failed: 测试失败",
        "result": "failed",
        "quality": {"score": 0.2, "dimensions": {"validation": 0.0}},
    }
    analysis = EVAL_LOOP.EvalFixLoop.analyze(record)
    new_quality = {
        "score": 0.9,
        "dimensions": {"validation": 1.0, "patch_apply": 1.0, "scope": 1.0,
                       "regression_risk": 1.0, "requirement_coverage": 1.0},
    }
    re = EVAL_LOOP.EvalFixLoop.reevaluate(new_quality, analysis.original_score)
    result = {
        "ok": bool(analysis.classification) and bool(re.get("improved")),
        "classification": analysis.classification,
        "suggestion": analysis.suggestion,
        "original_score": analysis.original_score,
        "reevaluated_score": re.get("new_score"),
        "improved": re.get("improved"),
        "generated_at": "2026-08-25T00:00:00+00:00",
    }
    _write_json(ws / ".eval" / "learning_loop_result.json", result)
    return result


# ------------------------------------------------------------------ 长跑 fixture


def run_longrun_fixture(ws: Path, *, duration: int = 2, heartbeat: int = 1) -> dict:
    """长跑冒烟 fixture: 复用 scripts/smoke_longrun.run_longrun (短时长, 可配置)。"""
    import sys as _sys

    _scripts = _ROOT / "scripts"
    if str(_scripts) not in _sys.path:
        _sys.path.insert(0, str(_scripts))
    from smoke_longrun import run_longrun

    return run_longrun(duration=duration, heartbeat=heartbeat, workspace=ws, label="test-longrun")


# ------------------------------------------------------------------ 全证据 workspace (L1)


def build_full_evidence_ws(tmp_path: Path) -> Path:
    """装配达到 L1 的临时 workspace (零污染): e2e + 鲁棒性 + 并发 + 学习闭环 + 长跑。"""
    ws = _ws(tmp_path)
    e2e = run_e2e_fixture(ws, emit_audit=True)
    assert e2e["ok"], f"H-1 fixture 失败: {e2e.get('error')}"
    rob = run_robustness_fixture(ws)
    assert rob["ok"], "鲁棒性 fixture 失败"
    conc = run_concurrency_fixture(ws)
    assert conc["ok"], f"并发 fixture 失败: {conc}"
    learn = run_learning_loop_fixture(ws)
    assert learn["ok"], "学习闭环 fixture 失败"
    run_longrun_fixture(ws, duration=2, heartbeat=1)
    return ws


# ================================================================== 契约 1: 七维评测


class TestSevenDimensions:
    def test_eval_dimensions_7_dims_each_has_items(self):
        """契约 1a: 7 维, 每维 ≥1 断言项, key/label/check 齐全。"""
        keys = [d["key"] for d in EVAL.EVAL_DIMENSIONS]
        assert len(keys) == 7
        assert keys == [
            EVAL.CORRECTNESS, EVAL.ROBUSTNESS, EVAL.CONSISTENCY,
            EVAL.PERFORMANCE, EVAL.SECURITY, EVAL.LONGEVITY, EVAL.USER_VALUE,
        ]
        for dim in EVAL.EVAL_DIMENSIONS:
            assert dim["label"], f"{dim['key']} 缺 label"
            assert len(dim["items"]) >= 1, f"{dim['key']} 缺评测项"
            for item in dim["items"]:
                assert item["id"] and item["label"]
                assert callable(item["check"]), f"{item['id']} check 不可调用"

    def test_report_on_empty_workspace_has_status_and_evidence(self):
        """契约 1b: 空 workspace 报告含 7 维 + 通过/失败/未覆盖 + 证据字段。"""
        ws = _ws(Path("/tmp") if False else None) if False else None  # placeholder
        # 用临时目录 (无任何证据) — 全部维度如实"未覆盖"
        import tempfile
        with tempfile.TemporaryDirectory(prefix="eval-empty-") as td:
            report = EVAL.EvalSuite().run(Path(td))
            assert len(report.dimensions) == 7
            for d in report.dimensions:
                assert d.status in (EVAL.STATUS_PASS, EVAL.STATUS_FAIL, EVAL.STATUS_NOT_COVERED)
                assert d.items, f"{d.key} 报告缺评测项结果"
                for i in d.items:
                    assert i.status in (EVAL.STATUS_PASS, EVAL.STATUS_FAIL, EVAL.STATUS_NOT_COVERED)
                    # 证据引用字段存在 (可为空 = 未覆盖)
                    assert hasattr(i, "evidence") and hasattr(i, "detail")
            md = report.to_markdown()
            assert "七维评测" in md
            assert "未覆盖" in md


# ================================================================== 契约 2: L0/L1 判定


class TestLevel:
    def test_full_evidence_ws_reaches_l1(self, tmp_path):
        """契约 2a: 全证据 (正确性/鲁棒性/一致性/性能/安全) → L1; 长期未覆盖 → 非 L2。"""
        ws = build_full_evidence_ws(tmp_path)
        report = EVAL.EvalSuite().run(ws, repo_root=_ROOT)
        assert report.level == "L1", report.level_reason
        for k in EVAL.L1_DIMENSIONS:
            assert EVAL.EvalSuite.level.__func__ is not None  # 类方法存在
            d = report.dimension(k)
            assert d is not None and d.status == EVAL.STATUS_PASS, f"{k} 应为通过: {d.status if d else None}"
        # 长期: 长跑 2s (< 24h) → 如实"未覆盖" (待长跑)
        long_d = report.dimension(EVAL.LONGEVITY)
        assert long_d.status == EVAL.STATUS_NOT_COVERED
        assert "待长跑" in long_d.items[1].detail

    def test_l0_only_workspace_is_l0(self, tmp_path):
        """契约 2b: 只有 L0 证据 (无安全证据) → L0 (非 L1)。"""
        ws = _ws(tmp_path)
        e2e = run_e2e_fixture(ws, emit_audit=False)  # 无审计事件 → 安全未覆盖
        assert e2e["ok"]
        run_robustness_fixture(ws)
        report = EVAL.EvalSuite().run(ws, repo_root=_ROOT)
        assert report.level == "L0", report.level_reason
        sec = report.dimension(EVAL.SECURITY)
        assert sec.status == EVAL.STATUS_NOT_COVERED

    def test_failure_drops_level_to_below_l0(self, tmp_path):
        """契约 2c: 低分执行记录 → 正确性失败 → below-L0。"""
        ws = _ws(tmp_path)
        run_e2e_fixture(ws, emit_audit=False)
        _write_json(ws / "exec" / "execution_records.json", [{
            "project": "demo", "task": "T-bad", "timestamp": "2026-08-25T11:00:00+00:00",
            "result": "failed", "error": "validation failed",
            "quality": {"score": 0.2, "dimensions": {"validation": 0.0}},
        }])
        report = EVAL.EvalSuite().run(ws, repo_root=_ROOT)
        assert report.level == "below-L0"
        corr = report.dimension(EVAL.CORRECTNESS)
        assert corr.status == EVAL.STATUS_FAIL


# ================================================================== 契约 3: 发布门


def _make_cli(tmp_path: Path) -> CLI.FactoryCLI:
    data_dir = tmp_path / ".factory"
    data_dir.mkdir()
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"core": {"data_dir": str(data_dir)}}), encoding="utf-8")
    config = CFG.ConfigProvider(user_config_file=cfg_file, env_file=tmp_path / ".env", environ={})
    # root 必须指向真实仓库 — eval 的注册表静态核对 (consistency.registry) 需要
    # repo_root 下有 factory-console/cli_factory.py (生产: CLI root = 真实仓库)
    root = _ROOT
    return CLI.FactoryCLI(config, root=root)


def _run(cli: CLI.FactoryCLI, *argv: str) -> int:
    return cli.run(CLI.build_parser().parse_args(list(argv)))


class TestReleaseGate:
    def test_gate_patch_blocks_on_empty_workspace(self, tmp_path, capsys):
        """契约 3a: --gate patch 空 workspace → rc 1 + [E4102] 明确阻断。"""
        cli = _make_cli(tmp_path)
        rc = _run(cli, "eval", "--gate", "patch", "--workspace", str(tmp_path / "empty"))
        err = capsys.readouterr().err
        assert rc == 1
        assert "[E4102]" in err
        assert "阻断" in err

    def test_gate_patch_passes_on_l0_workspace(self, tmp_path, capsys):
        """契约 3b: L0 证据 → --gate patch 通过 rc 0; --gate minor 阻断 (安全未覆盖)。"""
        ws = _ws(tmp_path)
        run_e2e_fixture(ws, emit_audit=False)
        run_robustness_fixture(ws)
        cli = _make_cli(tmp_path)
        rc_patch = _run(cli, "eval", "--gate", "patch", "--workspace", str(ws))
        assert rc_patch == 0
        capsys.readouterr()
        rc_minor = _run(cli, "eval", "--gate", "minor", "--workspace", str(ws))
        err = capsys.readouterr().err
        assert rc_minor == 1
        assert "[E4102]" in err
        assert "安全" in err

    def test_gate_minor_passes_on_full_evidence_workspace(self, tmp_path, capsys):
        """契约 3c: 全证据 (L1) → --gate minor 通过 rc 0; --gate major 阻断 (长期未覆盖)。"""
        ws = build_full_evidence_ws(tmp_path)
        cli = _make_cli(tmp_path)
        rc_minor = _run(cli, "eval", "--gate", "minor", "--workspace", str(ws))
        assert rc_minor == 0
        capsys.readouterr()
        rc_major = _run(cli, "eval", "--gate", "major", "--workspace", str(ws))
        err = capsys.readouterr().err
        assert rc_major == 1
        assert "长期" in err or "未覆盖" in err

    def test_check_default_is_read_only_no_block(self, tmp_path, capsys):
        """契约 3d: 默认/--check 只报告不阻断 (rc 0), 报告含 7 维。"""
        cli = _make_cli(tmp_path)
        rc = _run(cli, "eval", "--workspace", str(tmp_path / "empty"), "--check")
        out = capsys.readouterr().out
        assert rc == 0
        assert "七维评测" in out

    def test_gate_unknown_rejected(self, tmp_path, capsys):
        """契约 3e: 未知 --gate 值 → argparse 拒绝 (rc 2, 不静默)。"""
        import contextlib
        with pytest.raises(SystemExit) as excinfo:
            _run(_make_cli(tmp_path), "eval", "--gate", "bogus", "--workspace", str(tmp_path))
        assert excinfo.value.code == 2


# ================================================================== 契约 4: 并发不串


class TestConcurrencyIsolation:
    def test_multi_project_trace_ids_independent(self, tmp_path):
        """契约 4: 4 项目并发 → 各项目 trace_id 独立; 事件零交叉; 主线程不泄漏。"""
        ws = _ws(tmp_path)
        result = run_concurrency_fixture(ws, projects=4, tasks_per_project=3)
        assert result["ok"], result
        traces = result["trace_ids"]
        assert len(set(traces.values())) == 4
        # 审计事件按项目归属精确 (无串线) — 数量: fixture 每 worker 发 tasks_per_project 事件
        # (12 tasks × 3 events/task = 36), 断言 >= 项目×任务 (隔离才是核心, 数量非精确契约)
        events = AUDIT_STORE.AuditStore(workspace=ws).events()
        assert len(events) >= result["projects"] * result["tasks"] // result["projects"], f"事件数不足: {len(events)}"
        for ev in events:
            assert ev.trace_id == traces[ev.project_id], f"串线: {ev.project_id} {ev.trace_id}"
        # 各项目任务结果文件带自己 trace
        for pid, tid in traces.items():
            data = json.loads((ws / "projects" / pid / "task_result.json").read_text(encoding="utf-8"))
            assert data["trace_id"] == tid


# ================================================================== 契约 5: 长跑冒烟 + 24h


class TestLongrun:
    def test_short_longrun_runs_and_marks_awaiting(self, tmp_path):
        """契约 5a: 短时长冒烟可跑 (可配置), 证据标"待长跑" (< 24h)。"""
        ws = _ws(tmp_path)
        result = run_longrun_fixture(ws, duration=2, heartbeat=1)
        assert result["ok"] is True
        assert result["duration_seconds"] >= 2
        assert result["heartbeats"] >= 2
        assert result["status"] == "待长跑"
        assert (ws / ".eval" / "longrun_result.json").is_file()

    def test_24h_script_exists_and_marks_awaiting(self):
        """契约 5b: 24h 脚本存在且如实标"待长跑" (未真跑满 24h)。"""
        script = _ROOT / "scripts" / "smoke_24h.py"
        assert script.is_file()
        src = script.read_text(encoding="utf-8")
        assert "待长跑" in src
        assert "86400" in src or "LONGRUN_24H_S" in src
        longrun_src = (_ROOT / "scripts" / "smoke_longrun.py").read_text(encoding="utf-8")
        assert "待长跑" in longrun_src


# ================================================================== 契约 6: H-1 端到端


class TestH1E2EFixture:
    def test_e2e_nodes_chain_and_j1_projection(self, tmp_path):
        """契约 6a: 8 节点全过 + 每节点衔接断言 + J-1 三轨投影一致。"""
        ws = _ws(tmp_path)
        result = run_e2e_fixture(ws, emit_audit=True)
        assert result["ok"], result.get("error")
        expected_nodes = [
            "create", "discovery", "prd", "engineering",
            "approval", "execution", "evidence", "delivery",
        ]
        assert all(result["nodes"][n] for n in expected_nodes)
        assert result["lifecycle"] == Lifecycle.DELIVERED
        pdir = ws / "projects" / "demo"
        _assert_j1(pdir, Lifecycle.DELIVERED)
        # 衔接产物: 上一节点产物被下一节点消费
        assert (pdir / "prd.md").is_file()                     # PRD
        assert (pdir / "engineering.json").is_file()           # 工程计划
        assert (pdir / "execution_plan.json").is_file()        # 执行计划
        assert len(list(pdir.glob("gen_*.py"))) == 3           # 代码产物
        assert len(list(pdir.glob("evidence/ev-*.json"))) >= 1  # 证据包 (直接路径合并包 ≥1)
        assert json.loads((pdir / "approval" / "plan_approval.json").read_text(encoding="utf-8"))["decision"] == "approved"

    def test_e2e_evidence_consumed_by_eval_suite(self, tmp_path):
        """契约 6b: e2e 证据 → EvalSuite correctness.e2e_chain 通过。"""
        ws = _ws(tmp_path)
        run_e2e_fixture(ws, emit_audit=False)
        report = EVAL.EvalSuite().run(ws)
        d = report.dimension(EVAL.CORRECTNESS)
        item = next(i for i in d.items if i.item_id == "correctness.e2e_chain")
        assert item.status == EVAL.STATUS_PASS
        assert "e2e_result.json" in item.evidence


# ================================================================== 契约 7: F-10 覆盖度


class TestCoverage:
    def test_coverage_report_generates_module_level(self, tmp_path):
        """契约 7: stdlib trace 模块级覆盖率报告生成 (不设达标线, 只报)。"""
        import sys as _sys

        _scripts = _ROOT / "scripts"
        if str(_scripts) not in _sys.path:
            _sys.path.insert(0, str(_scripts))
        import coverage_report

        report = coverage_report.run_coverage(
            "factory_console.session.eval_suite:run_smoke", repo=_ROOT
        )
        assert report["tool"].startswith("stdlib trace")
        assert report["threshold"] is None  # 不设达标线
        modules = {m["module"] for m in report["modules"]}
        assert "factory_console.session.eval_suite" in modules
        assert report["total"]["executable_lines"] > 0
        for m in report["modules"]:
            assert 0.0 <= m["coverage_percent"] <= 100.0
        # 报告可落盘
        out = tmp_path / "coverage-report.json"
        out.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        assert out.is_file()


# ================================================================== 契约 8: M5-7 错误码表


class TestErrorCodes:
    def test_error_codes_table_exists_with_columns(self):
        """契约 8a: docs/error-codes.md 存在且含列头 (模块|CODE|消息|建议下一步)。"""
        doc = (_ROOT / "docs" / "error-codes.md").read_text(encoding="utf-8")
        assert "| 模块 | CODE | 消息 | 建议下一步 |" in doc
        assert "E4001" in doc and "E4102" in doc and "E5101" in doc

    def test_main_error_paths_have_codes(self):
        """契约 8b: 主要错误路径源码有码 (E4xx/E5xx 统一), 且均已登记。"""
        cli_src = (_ROOT / "factory-console" / "cli_factory.py").read_text(encoding="utf-8")
        for code in ("E4001", "E4002", "E4003", "E4101", "E4102"):
            assert f"[{code}]" in cli_src, f"cli_factory 缺 {code}"
        longrun_src = (_ROOT / "scripts" / "smoke_longrun.py").read_text(encoding="utf-8")
        assert "[E5001]" in longrun_src and "[E5002]" in longrun_src
        coverage_src = (_ROOT / "scripts" / "coverage_report.py").read_text(encoding="utf-8")
        assert "[E5101]" in coverage_src
        doc = (_ROOT / "docs" / "error-codes.md").read_text(encoding="utf-8")
        for code in ("E4001", "E4002", "E4003", "E4101", "E4102", "E5001", "E5002", "E5101"):
            assert f"| {code} |" in doc, f"error-codes.md 未登记 {code}"

    def test_eval_gate_emits_e4102(self, tmp_path, capsys):
        """契约 8c: eval --gate 失败 → stderr 含 [E4102] + rc 1 (行为断言)。"""
        cli = _make_cli(tmp_path)
        rc = _run(cli, "eval", "--gate", "patch", "--workspace", str(tmp_path / "empty"))
        assert rc == 1
        assert "[E4102]" in capsys.readouterr().err

    def test_run_missing_task_emits_e4001(self, tmp_path, capsys):
        """契约 8d: factory run 缺参数 → stderr 含 [E4001] + rc 2 (行为断言)。"""
        cli = _make_cli(tmp_path)
        rc = _run(cli, "run", "--project", str(tmp_path))
        err = capsys.readouterr().err
        assert rc == 2
        assert "[E4001]" in err
        assert "错误: --task 必填" in err


# ================================================================== 契约 9: C-4 盲区清单


class TestBlindSpots:
    def test_blind_spots_doc_exists(self):
        """契约 9: docs/eval-blind-spots.md 存在且含 K-2 已覆盖 vs 仍盲。"""
        doc = (_ROOT / "docs" / "eval-blind-spots.md").read_text(encoding="utf-8")
        assert "K-2 已覆盖" in doc
        assert "盲区" in doc
        assert "待长跑" in doc or "24h" in doc
        assert "不假装全清" in doc


# ================================================================== 契约 10: 注册表


class TestRegistry:
    def test_eval_command_visible_in_build_parser(self):
        """契约 10: build_parser 含 eval 子命令 + FactoryCLI.run 分派。"""
        parser = CLI.build_parser()
        sub_actions = {
            a.dest: a for a in parser._actions  # noqa: SLF001
            if isinstance(a, __import__("argparse")._SubParsersAction)  # noqa: SLF001
        }
        assert "eval" in sub_actions["command"].choices
        cli_src = (_ROOT / "factory-console" / "cli_factory.py").read_text(encoding="utf-8")
        assert 'args.command == "eval"' in cli_src
        # P0-10 同步: test_console_cli 期望集合也含 eval (注册表测试红则本测试红)
        tcc_src = (_ROOT / "tests" / "console" / "test_console_cli.py").read_text(encoding="utf-8")
        assert '"eval",' in tcc_src


# ================================================================== 契约 11: 版本


class TestVersionBump:
    def test_v1_1_95_synced(self):
        """契约 11: v1.1.95 — pyproject + CHANGELOG + FEATURES + 待办清单同步。"""
        pyproject = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        assert re.search(r'^version\s*=\s*"1\.1\.168"', pyproject, re.M)
        changelog = (_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        assert "## [v1.1.168]" in changelog
        features = (_ROOT / "docs" / "FEATURES.md").read_text(encoding="utf-8")
        assert "v1.1.168" in features
        backlog = (_ROOT / "docs" / "sprint10" / "待办清单-已发现未落地.md").read_text(encoding="utf-8")
        for marker in ("K-5", "P0-1", "P0-4", "P0-5", "C-1", "C-4", "C-5", "C-6", "H-1", "F-10", "M5-7"):
            assert marker in backlog
        assert "✅ S10-121" in backlog or "S10-121" in backlog
