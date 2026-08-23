"""tests/console/test_m3b_critical_path.py — M3b 关键路径标注引擎契约测试 (S10-090 M3-2)。

覆盖 (Hermes 规格 §6 验收, 手算对照):
- 5 种 DAG: 单链/分叉/汇聚/环/无依赖 — 关键路径与手算一致
- 技术层链: 同 feature db→api→frontend→test × est → duration 可断言
- CRITICAL + merge 落盘 plan.json + dependencies.json 可读
- 环 → 失败安全 (拒绝 + 审计事件, 不崩溃, 不伪造最长链)
- LLM 注入: 失败 → 确定性技术层链兜底; 成功 → 额外 llm 边
- 共享 target_file / 共享模块目录 → shared 边 (确定性检测)
- 向后兼容: M3a decompose 无依赖边输入 → 默认技术层链 (不崩溃)

basename 全仓库唯一 (test_console_* 前缀); 本目录自洽 (conftest 已挂仓库根)。
"""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path

CP = import_module("factory-console.session.critical_path")
DEC = import_module("factory-console.session.decomposer")

#: 强能力表 (M3a 兼容用例 — 单候选 → 全原子 verified)
STRONG_CAPS = {"database": 1, "backend": 1, "frontend": 1, "qa": 1}


def _leaf(tid: str, est: int, agent_type: str = "", parent: str = "", target_file: str = "") -> dict:
    """原子叶子构造 (手算用例: 显式 est_minutes; 无 parent/target_file → 推断不介入)。"""
    return {
        "id": tid,
        "name": tid,
        "goal": tid,
        "agent_type": agent_type,
        "est_minutes": est,
        "target_file": target_file,
        "parent": parent,
    }


def _engine(tmp_path: Path, **kw) -> CP.CriticalPathEngine:
    ws = tmp_path / "ws"
    ws.mkdir()
    return CP.CriticalPathEngine(workspace=ws, project_id="demo", **kw)


class _AuditStub:
    """审计桩: 收集 (event_type, fields) — 断言 PLAN_KEYPATH_COMPUTED /
    PLAN_MERGE_MARKED 已发射。"""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def emit(self, event_type: str, **fields: dict) -> None:
        self.events.append((event_type, fields))


# ---------------------------------------------------------------- 5 种 DAG

class TestSingleChain:
    def test_chain_abc(self, tmp_path):
        """单链 A→B→C (est 1/2/3) → 关键路径 A-B-C, duration=6 (1+2+3)。"""
        eng = _engine(tmp_path)
        r = eng.compute(
            [_leaf("A", 1), _leaf("B", 2), _leaf("C", 3)],
            edges=[("A", "B"), ("B", "C")],
        )
        assert r.error is None
        assert r.critical_path == ["A", "B", "C"]
        assert r.estimated_duration == 6
        assert {t["id"]: t["critical"] for t in r.tasks} == {
            "A": True, "B": True, "C": True,
        }
        assert r.merges == []
        assert r.order == ["A", "B", "C"]


class TestFork:
    def test_fork_max_branch(self, tmp_path):
        """分叉 A→{B,C} (est 5/3/7) → 关键路径 A-C, duration=12 (5+max(3,7))。"""
        eng = _engine(tmp_path)
        r = eng.compute(
            [_leaf("A", 5), _leaf("B", 3), _leaf("C", 7)],
            edges=[("A", "B"), ("A", "C")],
        )
        assert r.critical_path == ["A", "C"]
        assert r.estimated_duration == 12  # 5 + max(3, 7)
        assert {t["id"]: t["critical"] for t in r.tasks} == {
            "A": True, "B": False, "C": True,
        }
        assert r.merges == []  # B/C 入度 1 → 无汇聚点


class TestMerge:
    def test_merge_point_marked(self, tmp_path):
        """汇聚 {A,B}→C (est 3/5/4) → 关键路径 B-C, duration=9 (max(3,5)+4);
        merge=C (入度 2: A/B)。"""
        eng = _engine(tmp_path)
        r = eng.compute(
            [_leaf("A", 3), _leaf("B", 5), _leaf("C", 4)],
            edges=[("A", "C"), ("B", "C")],
        )
        assert r.critical_path == ["B", "C"]
        assert r.estimated_duration == 9  # max(3, 5) + 4
        assert r.merges == [{"task": "C", "deps": ["A", "B"]}]
        assert {t["id"]: t["critical"] for t in r.tasks} == {
            "A": False, "B": True, "C": True,
        }


class TestCycle:
    def test_cycle_rejected_failsafe(self, tmp_path):
        """环 A→B→A → 拒绝 + 审计, 不产出关键路径 (失败安全, 不崩溃)。"""
        stub = _AuditStub()
        eng = _engine(tmp_path, audit=stub)
        r = eng.compute(
            [_leaf("A", 1), _leaf("B", 2)],
            edges=[("A", "B"), ("B", "A")],
        )
        assert r.cycle_rejected is True
        assert r.error and "环" in r.error
        assert r.critical_path == []  # 不产出关键路径 (诚实不伪造)
        assert r.estimated_duration == 0
        assert all(t["critical"] is False for t in r.tasks)
        # 拒绝的边不入图: 只剩 A→B (B→A 被 add_dependency 成环拒绝)
        edge_pairs = [(e["from_task"], e["to_task"]) for e in r.edges]
        assert edge_pairs == [("A", "B")]
        # 审计: PLAN_KEYPATH_COMPUTED (status=cycle_rejected)
        assert "PLAN_KEYPATH_COMPUTED" in r.events
        emitted = [e[0] for e in stub.events]
        assert "PLAN_KEYPATH_COMPUTED" in emitted
        cp_event = [e for e in stub.events if e[0] == "PLAN_KEYPATH_COMPUTED"][0]
        assert cp_event[1]["status"] == "cycle_rejected"
        # 不崩溃: summary_text 可读
        assert "关键路径不可用" in r.summary_text


class TestNoDeps:
    def test_isolated_tasks_max_est(self, tmp_path):
        """无依赖 (est 3/7/5) → 每任务独立, duration=max est=7, 关键路径=[B]。"""
        eng = _engine(tmp_path)
        r = eng.compute([_leaf("A", 3), _leaf("B", 7), _leaf("C", 5)])
        assert r.edges == []
        assert r.critical_path == ["B"]
        assert r.estimated_duration == 7  # max(3, 7, 5)
        assert r.merges == []
        assert {t["id"]: t["critical"] for t in r.tasks} == {
            "A": False, "B": True, "C": False,
        }


# ---------------------------------------------------------------- 技术层链

class TestTechnicalChain:
    def test_default_chain_four_nodes(self, tmp_path):
        """技术层链 4 节点 × est(1/2/3/4) → duration=10 (db→api→frontend→test)。"""
        eng = _engine(tmp_path)
        leaves = [
            _leaf("root-f0-db", 1, "database", "root-f0", "db/schema_x.sql"),
            _leaf("root-f0-api", 2, "backend", "root-f0", "backend/x_api.py"),
            _leaf("root-f0-frontend", 3, "frontend", "root-f0", "frontend/x_page.js"),
            _leaf("root-f0-test", 4, "qa", "root-f0", "tests/test_x.py"),
        ]
        r = eng.compute(leaves)  # 无显式边 → 默认技术层链 (向后兼容)
        tech = [(e["from_task"], e["to_task"]) for e in r.edges if e["kind"] == "technical"]
        assert tech == [
            ("root-f0-db", "root-f0-api"),
            ("root-f0-api", "root-f0-frontend"),
            ("root-f0-frontend", "root-f0-test"),
        ]
        assert r.critical_path == [
            "root-f0-db", "root-f0-api", "root-f0-frontend", "root-f0-test",
        ]
        assert r.estimated_duration == 10  # 1+2+3+4
        assert r.error is None


# ---------------------------------------------------------------- 推断来源

class TestSharedInference:
    def test_shared_target_file_edge(self, tmp_path):
        """跨 feature 共享 target_file → shared 边 (确定性检测, id 字典序定向)。"""
        eng = _engine(tmp_path)
        leaves = [
            _leaf("f0-db", 1, "database", "f0", "db/schema.sql"),
            _leaf("f1-db", 2, "database", "f1", "db/schema.sql"),
        ]
        r = eng.compute(leaves)
        shared = [
            (e["from_task"], e["to_task"], e["source"])
            for e in r.edges if e["kind"] == "shared"
        ]
        assert ("f0-db", "f1-db", "shared_target_file") in shared

    def test_shared_module_dir_edge(self, tmp_path):
        """跨 feature 共享模块目录 (不同文件) → shared_module 边。"""
        eng = _engine(tmp_path)
        leaves = [
            _leaf("f0-db", 1, "database", "f0", "db/schema_f0.sql"),
            _leaf("f1-db", 2, "database", "f1", "db/schema_f1.sql"),
        ]
        r = eng.compute(leaves)
        shared = [
            (e["from_task"], e["to_task"], e["source"])
            for e in r.edges if e["kind"] == "shared"
        ]
        assert ("f0-db", "f1-db", "shared_module") in shared


class TestLlmInjection:
    def test_llm_failure_falls_back_to_technical(self, tmp_path):
        """LLM 推断失败 → 跳过, 确定性技术层链兜底 (不伪造)。"""
        eng = _engine(tmp_path)
        leaves = [
            _leaf("root-f0-db", 1, "database", "root-f0", "db/schema_x.sql"),
            _leaf("root-f0-api", 2, "backend", "root-f0", "backend/x_api.py"),
            _leaf("root-f0-frontend", 3, "frontend", "root-f0", "frontend/x_page.js"),
            _leaf("root-f0-test", 4, "qa", "root-f0", "tests/test_x.py"),
        ]

        def broken_llm(leaves_, edges_):
            raise RuntimeError("llm down")

        r = eng.compute(leaves, llm_fn=broken_llm)
        assert r.error is None  # 失败被吞 → 确定性兜底, 不崩溃
        assert not any(e["kind"] == "llm" for e in r.edges)
        tech = [e for e in r.edges if e["kind"] == "technical"]
        assert len(tech) == 3  # db→api→frontend→test

    def test_llm_injection_adds_extra_edge(self, tmp_path):
        """LLM 注入成功 → 额外 llm 边入图并参与关键路径。"""
        eng = _engine(tmp_path)
        leaves = [
            _leaf("root-f0-db", 1, "database", "root-f0", "db/schema_x.sql"),
            _leaf("root-f0-api", 2, "backend", "root-f0", "backend/x_api.py"),
            _leaf("root-f0-frontend", 3, "frontend", "root-f0", "frontend/x_page.js"),
            _leaf("root-f0-test", 4, "qa", "root-f0", "tests/test_x.py"),
        ]

        def llm(leaves_, edges_):
            return [{
                "from_task": "root-f0-db", "to_task": "root-f0-test",
                "kind": "llm", "source": "llm_injected",
            }]

        r = eng.compute(leaves, llm_fn=llm)
        kinds = {(e["from_task"], e["to_task"]): e["kind"] for e in r.edges}
        assert kinds[("root-f0-db", "root-f0-test")] == "llm"
        # 关键路径仍为技术层链 (llm 边不改变最长链: db→api→frontend→test 更长)
        assert r.estimated_duration == 10


# ---------------------------------------------------------------- 落盘

class TestPersist:
    def test_plan_and_dependencies_json(self, tmp_path):
        """plan.json + dependencies.json 落盘可读; plan 含 tasks/edges/
        critical_path/merges/estimated_duration。"""
        eng = _engine(tmp_path)
        r = eng.compute(
            [_leaf("A", 3), _leaf("B", 5), _leaf("C", 4)],
            edges=[("A", "C"), ("B", "C")],
        )
        plan = tmp_path / "ws" / "projects" / "demo" / "plan.json"
        deps = tmp_path / "ws" / "projects" / "demo" / "dependencies.json"
        assert plan.is_file() and deps.is_file()

        plan_data = json.loads(plan.read_text(encoding="utf-8"))
        assert plan_data["project_id"] == "demo"
        assert plan_data["critical_path"] == ["B", "C"]
        assert plan_data["estimated_duration"] == 9
        assert plan_data["merges"] == [{"task": "C", "deps": ["A", "B"]}]
        assert {t["id"] for t in plan_data["tasks"]} == {"A", "B", "C"}
        crit = {t["id"]: t["critical"] for t in plan_data["tasks"]}
        assert crit == {"A": False, "B": True, "C": True}
        assert plan_data["edges"] and "from_task" in plan_data["edges"][0]
        assert "summary_text" in plan_data

        deps_data = json.loads(deps.read_text(encoding="utf-8"))
        assert deps_data["project_id"] == "demo"
        assert deps_data["graph"] == {"C": ["A", "B"]}
        assert len(deps_data["edges"]) == 2
        # 可复用回注: load_dependencies → 同边
        loaded = CP.CriticalPathEngine.load_dependencies(tmp_path / "ws", "demo")
        assert {(e["from_task"], e["to_task"]) for e in loaded} == {("A", "C"), ("B", "C")}

    def test_cycle_plan_persisted_failsafe(self, tmp_path):
        """环拒绝时 plan.json 仍落盘 (cycle_rejected=True, critical_path 空)。"""
        eng = _engine(tmp_path)
        r = eng.compute([_leaf("A", 1), _leaf("B", 2)], edges=[("A", "B"), ("B", "A")])
        plan = tmp_path / "ws" / "projects" / "demo" / "plan.json"
        assert plan.is_file()
        plan_data = json.loads(plan.read_text(encoding="utf-8"))
        assert plan_data["cycle_rejected"] is True
        assert plan_data["critical_path"] == []
        assert r.cycle_rejected is True


# ---------------------------------------------------------------- 审计

class TestAuditEvents:
    def test_keypath_and_merge_marked(self, tmp_path):
        """PLAN_KEYPATH_COMPUTED + PLAN_MERGE_MARKED 已发射 (汇聚用例)。"""
        stub = _AuditStub()
        eng = _engine(tmp_path, audit=stub)
        eng.compute(
            [_leaf("A", 3), _leaf("B", 5), _leaf("C", 4)],
            edges=[("A", "C"), ("B", "C")],
        )
        emitted = [e[0] for e in stub.events]
        assert "PLAN_KEYPATH_COMPUTED" in emitted
        assert "PLAN_MERGE_MARKED" in emitted
        merge_events = [e for e in stub.events if e[0] == "PLAN_MERGE_MARKED"]
        assert len(merge_events) == 1
        assert merge_events[0][1]["task_id"] == "C"
        assert merge_events[0][1]["result"]["indegree"] == 2
        assert "PLAN_KEYPATH_COMPUTED" in eng._events  # 结果事件列表同步

    def test_no_merge_no_event(self, tmp_path):
        """无汇聚点 → 不发射 PLAN_MERGE_MARKED (只标注真实汇聚)。"""
        stub = _AuditStub()
        eng = _engine(tmp_path, audit=stub)
        eng.compute([_leaf("A", 1), _leaf("B", 2), _leaf("C", 3)],
                    edges=[("A", "B"), ("B", "C")])
        assert "PLAN_KEYPATH_COMPUTED" in [e[0] for e in stub.events]
        assert "PLAN_MERGE_MARKED" not in [e[0] for e in stub.events]


# ---------------------------------------------------------------- 向后兼容

class TestBackwardCompat:
    def test_m3a_leaves_default_technical_chain(self, tmp_path):
        """M3a decompose 无依赖边输出 → 默认技术层链 (不崩溃, 兼容旧行为)。"""
        eng = _engine(tmp_path)
        dres = DEC.DecomposeEngine(workspace=tmp_path / "ws", project_id="demo").decompose(
            {
                "id": "root",
                "name": "实现登录功能",
                "goal": "实现登录功能",
                "requirement": "登录接口、登录页面、登录测试",
            },
            product={"core_features": ["登录"]},
            capabilities=STRONG_CAPS,
        )
        assert dres.error is None and dres.leaves
        r = eng.compute(dres.leaves)  # 无显式边 → 引擎兜底技术层链
        assert r.error is None  # 不崩溃
        # 每个 feature 内 db→api→frontend→test 技术链边存在
        by_parent: dict[str, list[dict]] = {}
        for lf in dres.leaves:
            by_parent.setdefault(lf.get("parent") or "", []).append(lf)
        tech_pairs = {
            (e["from_task"], e["to_task"])
            for e in r.edges if e["kind"] == "technical"
        }
        assert by_parent, "decompose 应有 feature 分组"
        for pid, group in by_parent.items():
            layer_by_id = {}
            for lf in group:
                idx = CP.CriticalPathEngine._layer_index(lf)
                assert idx is not None, f"{lf['id']} 应可映射技术层"
                layer_by_id[lf["id"]] = idx
            ordered = sorted(layer_by_id.items(), key=lambda kv: kv[1])
            for i in range(len(ordered) - 1):
                if ordered[i][1] < ordered[i + 1][1]:
                    assert (ordered[i][0], ordered[i + 1][0]) in tech_pairs
        # 关键路径自洽: duration == 沿路径 est 之和; critical 恰好是路径上任务
        est = {lf["id"]: int(lf.get("est_minutes") or 0) for lf in dres.leaves}
        assert r.estimated_duration == sum(est[tid] for tid in r.critical_path)
        assert r.critical_path  # 非空
        edge_set = {(e["from_task"], e["to_task"]) for e in r.edges}
        for a, b in zip(r.critical_path, r.critical_path[1:]):
            assert (a, b) in edge_set, f"关键路径边 {a}→{b} 应存在"
        crit = {t["id"]: t["critical"] for t in r.tasks}
        assert set(crit) == {lf["id"] for lf in dres.leaves}
        assert [tid for tid, c in crit.items() if c] == r.critical_path
        # plan.json 已落盘
        assert (tmp_path / "ws" / "projects" / "demo" / "plan.json").is_file()

    def test_engine_summary_text(self, tmp_path):
        """summary_text CLI 展示 (§5): 关键路径 + 预估 + 汇聚点。"""
        eng = _engine(tmp_path)
        r = eng.compute(
            [_leaf("A", 3), _leaf("B", 5), _leaf("C", 4)],
            edges=[("A", "C"), ("B", "C")],
        )
        assert "关键路径: B → C" in r.summary_text
        assert "预计 9 分钟" in r.summary_text
        assert "汇聚点 C(A/B)" in r.summary_text
