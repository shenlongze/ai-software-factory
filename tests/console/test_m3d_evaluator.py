"""tests/console/test_m3d_evaluator.py — M3d 拆解质量评估 + 四档行动契约测试 (S10-095)。

覆盖 (Hermes 规格 §6 验收):
1. 六维手算: 构造已知拆分 → 每维分可断言 (粒度=四条件通过率等)
2. 好拆解: 评分≥0.9 → adopt
3. 差拆解: <0.7 → reject(回退确定性技术层模板)
4. 无 LLM: 确定性 leaves 照常评估(不跳过)
5. 落盘: evaluation 字段(score/dims/decision)进 evidence + 审计事件
   (EVAL_COMPLETED / EVAL_REJECTED_FALLBACK)
6. 向后兼容: M3a decompose 零变化(评估器可选注入, 默认开)
额外 (规格 §2/§3/§4):
- ask_user (<0.5) 返回 questions
- adjust (0.7-0.9) 自动修正 → 标注 adjusted
- LLM 结构化 {tasks[]} 产出 → 质量门控

basename 全仓库唯一 (test_console_* 前缀); 本目录自洽 (conftest 已挂仓库根)。
"""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path

EV = import_module("factory-console.session.decomposition_evaluator")
DEC = import_module("factory-console.session.decomposer")
AUDIT = import_module("factory-console.audit.audit_event")
EVIDENCE = import_module("factory-console.session.evidence")

STRONG_CAPS = {"database": 1, "backend": 1, "frontend": 1, "qa": 1}
FEATURES = ["登录", "注册"]
TASK = {"id": "root", "name": "实现登录注册", "goal": "实现登录注册",
        "requirement": "登录接口、注册接口、页面、测试", "core_features": list(FEATURES)}
CTX = {"capabilities": STRONG_CAPS, "product": {"core_features": list(FEATURES)}}
#: 引擎集成用例: task 与 product core_features 一致 (单 feature, 确定性 4 叶子)
TASK_LOGIN = {"id": "root", "name": "实现登录功能", "goal": "实现登录功能",
              "requirement": "登录接口、登录页面、登录测试", "core_features": ["登录"]}


def _leaf(tid: str, *, feat: str, agent: str = "backend", verify: str | None = None,
          est: int = 5, risks: list | None = None, dep: list | None = None,
          target: str | None = None) -> dict:
    """原子叶子构造 (手算用例: 显式各字段; verify=None 按语言推导, "" = 缺 verify)。"""
    target = target or f"backend/{tid}.py"
    if verify is None:
        ext = target.rsplit(".", 1)[-1]
        verify = {
            "py": "pytest", "sql": "sqlfluff lint", "js": "npm test --",
        }[ext] + " " + target
    d = {
        "id": tid,
        "name": f"{feat}: {tid}",
        "goal": f"实现功能: {feat}（{tid}）",
        "requirement": f"{feat} {tid}",
        "agent_type": agent,
        "target_file": target,
        "verify_cmd": verify,
        "est_minutes": est,
    }
    if risks is not None:
        d["risks"] = risks
    if dep is not None:
        d["depends_on"] = dep
    return d


def _decomp(*leaves: dict) -> dict:
    return {"tasks": list(leaves)}


# ---------------------------------------------------------------- 六维手算

class TestSixDimHandCalc:
    """六维确定性评分手算对照 (规格 §6.1): 构造已知拆分 → 各维分可断言。"""

    def test_good_all_dims_full(self):
        """4 叶子全单文件全 verify 全 risks, 双 feature 覆盖, 无环 → 每维 1.0。"""
        e = EV.DecompositionEvaluator()
        d = _decomp(
            _leaf("t1", feat="登录", agent="database", target="db/schema_login.sql",
                  verify="sqlfluff lint db/schema_login.sql", risks=["外键"]),
            _leaf("t2", feat="登录", agent="backend", target="backend/login_api.py",
                  risks=["鉴权"]),
            _leaf("t3", feat="注册", agent="frontend", target="frontend/register_page.js",
                  verify="npm test -- frontend/register_page.js", risks=["表单"]),
            _leaf("t4", feat="注册", agent="qa", target="tests/test_register.py",
                  risks=["环境"]),
        )
        r = e.evaluate(d, TASK, CTX)
        assert r.dims == {
            "完整性": 1.0, "粒度": 1.0, "依赖": 1.0,
            "可行性": 1.0, "可测性": 1.0, "风险": 1.0,
        }
        assert r.score == 1.0

    def test_granularity_condition_pass_rate(self):
        """粒度 = 原子四条件通过率 (每条件 0.25): 1 个缺 verify → 0.9375。"""
        e = EV.DecompositionEvaluator()
        d = _decomp(
            _leaf("t1", feat="登录", agent="database", target="db/s1.sql",
                  verify="sqlfluff lint db/s1.sql", risks=["a"]),
            _leaf("t2", feat="登录", agent="backend", target="backend/a.py",
                  verify="", risks=["b"]),          # 缺 verify → 该叶 0.75
            _leaf("t3", feat="注册", agent="backend", target="backend/b.py",
                  risks=["c"]),
            _leaf("t4", feat="注册", agent="qa", target="tests/test_b.py",
                  risks=["d"]),
        )
        r = e.evaluate(d, TASK, CTX)
        # (1.0 + 0.75 + 1.0 + 1.0) / 4 = 0.9375
        assert r.dims["粒度"] == 0.9375
        # 可测性 = 3/4
        assert r.dims["可测性"] == 0.75
        # 完整性 = 2/2
        assert r.dims["完整性"] == 1.0

    def test_completeness_missing_feature(self):
        """完整性 = core_features 覆盖: 只覆盖 登录 → 0.5 (缺失 注册 失分)。"""
        e = EV.DecompositionEvaluator()
        d = _decomp(
            _leaf("t1", feat="登录", agent="backend", target="backend/a.py", risks=["x"]),
            _leaf("t2", feat="登录", agent="qa", target="tests/test_a.py", risks=["y"]),
        )
        r = e.evaluate(d, TASK, CTX)
        assert r.dims["完整性"] == 0.5
        assert any("缺失" in reason and "注册" in reason for reason in r.reasons)

    def test_deps_cycle_zero_and_dead_node_half(self):
        """依赖: 环 → 0.0; 有边但死节点/悬空 → 0.5; 无环全连通 → 1.0。"""
        e = EV.DecompositionEvaluator()
        # 环 A→B→A
        cyc = _decomp(
            _leaf("A", feat="登录", agent="backend", target="backend/a.py",
                  risks=["x"], dep=["B"]),
            _leaf("B", feat="登录", agent="backend", target="backend/b.py",
                  risks=["y"], dep=["A"]),
        )
        assert e.evaluate(cyc, TASK, CTX).dims["依赖"] == 0.0
        # 悬空引用 (depends_on 指向不存在的 Z) → 0.5
        dangling = _decomp(
            _leaf("A", feat="登录", agent="backend", target="backend/a.py",
                  risks=["x"], dep=["Z"]),
            _leaf("B", feat="登录", agent="backend", target="backend/b.py", risks=["y"]),
        )
        assert e.evaluate(dangling, TASK, CTX).dims["依赖"] == 0.5
        # 无显式边 (M3a 顺序语义) → 1.0 (无环可判, 不误伤)
        no_edges = _decomp(
            _leaf("A", feat="登录", agent="backend", target="backend/a.py", risks=["x"]),
            _leaf("B", feat="登录", agent="qa", target="tests/test_a.py", risks=["y"]),
        )
        assert e.evaluate(no_edges, TASK, CTX).dims["依赖"] == 1.0

    def test_feasibility_unknown_agent(self):
        """可行性 = agent_type ∈ capabilities: ghost 不在能力表 → 0.5。"""
        e = EV.DecompositionEvaluator()
        d = _decomp(
            _leaf("t1", feat="登录", agent="backend", target="backend/a.py", risks=["x"]),
            _leaf("t2", feat="注册", agent="ghost", target="backend/b.py", risks=["y"]),
        )
        r = e.evaluate(d, TASK, CTX)
        assert r.dims["可行性"] == 0.5
        assert any("ghost" in reason for reason in r.reasons)

    def test_risk_no_annotations_zero(self):
        """风险: 全部无 risks 标注 → 0.0 (无 → 0)。"""
        e = EV.DecompositionEvaluator()
        d = _decomp(
            _leaf("t1", feat="登录", agent="backend", target="backend/a.py"),
            _leaf("t2", feat="注册", agent="backend", target="backend/b.py"),
        )
        r = e.evaluate(d, TASK, CTX)
        assert r.dims["风险"] == 0.0


# ---------------------------------------------------------------- 四档行动

class TestDecisionTiers:
    def test_good_decomposition_adopt(self):
        """好拆解: 评分 1.0 ≥0.9 → adopt (六维全满)。"""
        e = EV.DecompositionEvaluator()
        d = _decomp(
            _leaf("t1", feat="登录", agent="database", target="db/s1.sql",
                  verify="sqlfluff lint db/s1.sql", risks=["外键"]),
            _leaf("t2", feat="登录", agent="backend", target="backend/a.py", risks=["鉴权"]),
            _leaf("t3", feat="注册", agent="frontend", target="frontend/r.js",
                  verify="npm test -- frontend/r.js", risks=["表单"]),
            _leaf("t4", feat="注册", agent="qa", target="tests/test_r.py", risks=["环境"]),
        )
        r = e.evaluate(d, TASK, CTX)
        assert r.score >= 0.9
        assert r.decision == "adopt"

    def test_bad_decomposition_reject(self):
        """差拆解: 缺失 feature + 依赖环 + 无 risks → 0.575 <0.7 → reject。"""
        e = EV.DecompositionEvaluator()
        # 只覆盖 登录 (完整性 0.5), t1↔t4 成环 (依赖 0), 无 risks
        d = _decomp(
            _leaf("t1", feat="登录", agent="database", target="db/s1.sql",
                  verify="sqlfluff lint db/s1.sql", dep=["t4"]),
            _leaf("t2", feat="登录", agent="backend", target="backend/a.py"),
            _leaf("t3", feat="登录", agent="frontend", target="frontend/l.js",
                  verify="npm test -- frontend/l.js"),
            _leaf("t4", feat="登录", agent="qa", target="tests/test_l.py", dep=["t1"]),
        )
        r = e.evaluate(d, TASK, CTX)
        # 0.25*0.5 + 0.2*1 + 0.2*0 + 0.15*1 + 0.1*1 + 0.1*0 = 0.575
        assert r.score == 0.575
        assert 0.5 <= r.score < 0.7
        assert r.decision == "reject"
        assert r.dims["依赖"] == 0.0

    def test_ask_user_returns_questions(self):
        """<0.5 → ask_user + questions (REPL 层处理后重评)。"""
        e = EV.DecompositionEvaluator()
        # 叶子不覆盖任何 feature (完整性 0) + 缺 verify + ghost agent + 无 risks
        d = _decomp(
            _leaf("t1", feat="其他", agent="backend", target="backend/a.py", verify=""),
            _leaf("t2", feat="杂项", agent="ghost", target="backend/b.py", verify=""),
        )
        r = e.evaluate(d, TASK, CTX)
        # 0 + 0.2*0.75 + 0.2*1 + 0.15*0.5 + 0 + 0 = 0.425
        assert r.score == 0.425
        assert r.score < 0.5
        assert r.decision == "ask_user"
        assert r.questions, "ask_user 必须返回 questions"
        assert any("core_features" in q or "缺失" in q for q in r.questions)

    def test_adjust_tier_auto_fix_marks_adjusted(self):
        """0.7-0.9 → adjust: 补缺失 feature + 补 verify → 修正后采用 (adjusted)。"""
        e = EV.DecompositionEvaluator()
        # 只覆盖 登录 (缺 注册), t1 缺 verify → 0.85 → adjust
        d = _decomp(
            _leaf("t1", feat="登录", agent="backend", target="backend/a.py", verify=""),
            _leaf("t2", feat="登录", agent="qa", target="tests/test_a.py"),
            _leaf("t3", feat="登录", agent="database", target="db/s1.sql",
                  verify="sqlfluff lint db/s1.sql"),
            _leaf("t4", feat="登录", agent="frontend", target="frontend/l.js",
                  verify="npm test -- frontend/l.js"),
        )
        r = e.evaluate(d, TASK, CTX)
        assert r.decision == "adjust"
        fixed, ar = e.adjust(d, TASK, CTX)
        assert ar.adjusted is True
        assert ar.decision == "adopt", f"修正后应 ≥0.7 采用, got {ar.score}"
        assert ar.adjustments, "必须记录自动修正项"
        # 缺失 feature 已补齐 (注册 任务被添加)
        assert any("注册" in str(t.get("goal") or t.get("name") or "") for t in fixed["tasks"])
        assert any(t.get("source") == "evaluator_adjust" for t in fixed["tasks"])
        # verify 已补默认 (t1)
        t1 = next(t for t in fixed["tasks"] if t["id"] == "t1")
        assert t1["verify_cmd"] == "pytest backend/a.py"

    def test_adjust_prunes_cycle_edges(self):
        """adjust 修剪依赖环: 成环边丢弃 → DAG 保持, 依赖维回升。"""
        e = EV.DecompositionEvaluator()
        d = _decomp(
            _leaf("A", feat="登录", agent="backend", target="backend/a.py",
                  risks=["x"], dep=["B"]),
            _leaf("B", feat="登录", agent="backend", target="backend/b.py",
                  risks=["y"], dep=["A"]),
        )
        r = e.evaluate(d, TASK, CTX)
        assert r.dims["依赖"] == 0.0
        fixed, ar = e.adjust(d, TASK, CTX)
        assert any("环" in a for a in ar.adjustments)
        by_id = {t["id"]: t for t in fixed["tasks"]}
        assert by_id["A"].get("depends_on") == ["B"] or by_id["B"].get("depends_on") == ["A"]
        # 修剪后无环 (任取一边方向不成环)
        re = e.evaluate(fixed, TASK, CTX)
        assert re.dims["依赖"] > 0.0


# ---------------------------------------------------------------- 引擎集成

class TestEngineIntegration:
    def test_llm_structured_output_quality_gated(self, tmp_path):
        """LLM 结构化 {tasks[]} → 质量门控: 好拆解 adopt, 字段透传。"""
        eng = DEC.DecomposeEngine(workspace=_ws(tmp_path), project_id="demo")

        def good_llm(t, product):
            return {"tasks": [
                {"id": "llm-db", "name": "数据库: 登录", "requirement": "登录 schema",
                 "agent_type": "database", "target_file": "db/schema_login.sql",
                 "verify_cmd": "sqlfluff lint db/schema_login.sql", "est": 5,
                 "depends_on": [], "risks": ["外键"]},
                {"id": "llm-api", "name": "后端接口: 登录", "requirement": "登录 api",
                 "agent_type": "backend", "target_file": "backend/login_api.py",
                 "verify_cmd": "pytest backend/login_api.py", "est": 8,
                 "depends_on": ["llm-db"], "risks": ["鉴权"]},
                {"id": "llm-fe", "name": "前端页面: 登录", "requirement": "登录页面",
                 "agent_type": "frontend", "target_file": "frontend/login_page.js",
                 "verify_cmd": "npm test -- frontend/login_page.js", "est": 6,
                 "depends_on": ["llm-api"], "risks": ["表单"]},
                {"id": "llm-qa", "name": "测试: 登录", "requirement": "登录测试",
                 "agent_type": "qa", "target_file": "tests/test_login.py",
                 "verify_cmd": "pytest tests/test_login.py", "est": 5,
                 "depends_on": ["llm-fe"], "risks": ["环境"]},
            ], "summary": "登录四层拆解"}

        r = eng.decompose(dict(TASK_LOGIN), product={"core_features": ["登录"]},
                          capabilities=STRONG_CAPS, llm_fn=good_llm)
        ev = r.state["evaluation"]
        assert ev["decision"] == "adopt"
        assert ev["score"] >= 0.9
        # 结构化字段透传到叶子 (评估输入)
        assert all(lf.get("risks") for lf in r.leaves)
        assert any(lf.get("depends_on") for lf in r.leaves)

    def test_bad_llm_reject_falls_back_to_deterministic(self, tmp_path):
        """差拆解 <0.7 → EVAL_REJECTED_FALLBACK + 回退确定性技术层模板。"""
        eng = DEC.DecomposeEngine(workspace=_ws(tmp_path), project_id="demo")

        def bad_llm(t, product):
            return {"tasks": [
                {"id": "x1", "name": "实现登录", "requirement": "登录",
                 "agent_type": "ghost", "target_file": "a.py",
                 "verify_cmd": "pytest a.py", "est": 5,
                 "depends_on": ["x1"], "risks": []},
            ], "summary": "bad"}

        r = eng.decompose(dict(TASK_LOGIN), product={"core_features": ["登录"]},
                          capabilities=STRONG_CAPS, llm_fn=bad_llm)
        ev = r.state["evaluation"]
        assert ev["decision"] == "reject"
        assert "EVAL_COMPLETED" in r.state["events"]
        assert "EVAL_REJECTED_FALLBACK" in r.state["events"]
        # 回退 = 确定性技术层模板 (db/api/frontend/test 层叶子)
        agents = {lf["agent_type"] for lf in r.leaves}
        assert agents & {"database", "backend", "frontend", "qa"}

    def test_no_llm_deterministic_evaluated_as_usual(self, tmp_path):
        """无 LLM: 确定性 leaves 照常评估 (不跳过), EVAL_COMPLETED 落盘。"""
        eng = DEC.DecomposeEngine(workspace=_ws(tmp_path), project_id="demo")
        r = eng.decompose(dict(TASK_LOGIN), product={"core_features": ["登录"]},
                          capabilities=STRONG_CAPS)
        ev = r.state["evaluation"]
        assert ev is not None, "无 LLM 也必须评估 (不跳过)"
        assert "EVAL_COMPLETED" in r.state["events"]
        # 确定性 8 叶子 (2 feature × 4 层) 或 4 叶子 (1 feature × 4 层) 全原子
        assert all(lf["verified"] for lf in r.leaves)

    def test_evaluation_persisted_evidence_and_state(self, tmp_path):
        """落盘: evaluation (score/dims/decision) 进 evidence + decomposition.json。"""
        ws = _ws(tmp_path)
        eng = DEC.DecomposeEngine(workspace=ws, project_id="demo")
        eng.decompose(dict(TASK_LOGIN), product={"core_features": ["登录"]},
                      capabilities=STRONG_CAPS)
        # decomposition.json state
        djson = json.loads((ws / "projects" / "demo" / "decomposition.json").read_text(encoding="utf-8"))
        ev = djson["evaluation"]
        assert set(ev) >= {"score", "dims", "decision", "reasons"}
        assert ev["decision"] == "adopt"
        # evidence 证据包
        bundles = EVIDENCE.EvidenceStore(workspace=ws, slug="demo").list()
        assert bundles, "评估必须落盘 evidence"
        b = bundles[-1]
        assert b.evaluation and b.evaluation["decision"] == ev["decision"]
        assert b.evaluation["score"] == ev["score"]
        assert set(b.evaluation["dims"]) == {"完整性", "粒度", "依赖", "可行性", "可测性", "风险"}

    def test_audit_events_registered_and_emitted(self, tmp_path):
        """审计: EVAL_COMPLETED / EVAL_REJECTED_FALLBACK ∈ EVENT_TYPES 且真实发射。"""
        assert "EVAL_COMPLETED" in AUDIT.EVENT_TYPES
        assert "EVAL_REJECTED_FALLBACK" in AUDIT.EVENT_TYPES

        class _AuditStub:
            def __init__(self):
                self.events = []

            def emit(self, event_type, **fields):
                self.events.append((event_type, fields))

        stub = _AuditStub()
        eng = DEC.DecomposeEngine(audit=stub, project_id="demo")
        eng.decompose(dict(TASK_LOGIN), product={"core_features": ["登录"]},
                      capabilities=STRONG_CAPS)
        types = [t for t, _ in stub.events]
        assert "EVAL_COMPLETED" in types

        stub2 = _AuditStub()
        eng2 = DEC.DecomposeEngine(audit=stub2, project_id="demo")

        def bad_llm(t, product):
            return {"tasks": [
                {"id": "x1", "name": "实现登录", "requirement": "登录",
                 "agent_type": "ghost", "target_file": "a.py",
                 "verify_cmd": "pytest a.py", "est": 5, "depends_on": ["x1"], "risks": []},
            ], "summary": "bad"}

        eng2.decompose(dict(TASK_LOGIN), product={"core_features": ["登录"]},
                       capabilities=STRONG_CAPS, llm_fn=bad_llm)
        types2 = [t for t, _ in stub2.events]
        assert "EVAL_COMPLETED" in types2
        assert "EVAL_REJECTED_FALLBACK" in types2

    def test_evaluator_injectable_and_disablable(self, tmp_path):
        """向后兼容: 评估器可选注入; evaluate_after=False → M3a 零变化。"""
        ws = _ws(tmp_path)
        # 自定义注入评估器 (可替换默认)
        injected = EV.DecompositionEvaluator(workspace=ws, project_id="demo")
        eng = DEC.DecomposeEngine(workspace=ws, project_id="demo", evaluator=injected)
        r = eng.decompose(dict(TASK_LOGIN), product={"core_features": ["登录"]},
                          capabilities=STRONG_CAPS)
        assert r.state["evaluation"]["decision"] == "adopt"
        # 显式关闭后置评估 → 无 evaluation 字段, 无评估事件
        eng2 = DEC.DecomposeEngine(workspace=ws, project_id="demo", evaluate_after=False)
        r2 = eng2.decompose(dict(TASK_LOGIN), product={"core_features": ["登录"]},
                            capabilities=STRONG_CAPS)
        assert r2.state["evaluation"] is None
        assert "EVAL_COMPLETED" not in r2.state["events"]
        # M3a 核心行为不变: 叶子全原子 (默认开时同样 adopt 不改变 leaves)
        assert all(lf["verified"] for lf in r2.leaves)
        assert all(lf["verified"] for lf in r.leaves)
        assert [lf["id"] for lf in r.leaves] == [lf["id"] for lf in r2.leaves]


def _ws(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir(exist_ok=True)
    return ws
