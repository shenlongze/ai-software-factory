"""tests/console/test_m3a_decomposer.py — M3a 递归原子拆解引擎契约测试 (S10-090)。

覆盖 (Hermes 规格 §6 验收):
- 复合任务 → 原子叶子 (四条件断言: agent_type 单数 / 文件数=1 / verify_cmd
  存在 / est≤10)
- 深度收敛: capabilities 注入不同配置 → 深度/verified 不同 (能力边界诚实)
- 成环拒绝: DECOMPOSE_CYCLE_REJECTED + 不静默
- 无 LLM 降级: llm_fn=None → 确定性拆分非空 + unverified 诚实标注
- 向后兼容: 旧 TaskTree/FeatureTaskGenerator 流程 (pipeline.py) 不受影响
- 状态落盘: decomposition.json 可追溯

basename 全仓库唯一 (test_console_* 前缀); 本目录自洽 (conftest 已挂仓库根)。
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

DEC = import_module("factory-console.session.decomposer")
PIPELINE = import_module("factory-console.session.pipeline")
PRODUCT = import_module("factory-console.session.product")

#: 复合任务样例（"一步一个坑"典型: 实现一个功能 = 数据/接口/页面/测试）
COMPOSITE = {
    "id": "root",
    "name": "实现登录功能",
    "goal": "实现登录功能",
    "requirement": "登录接口、登录页面、登录测试",
}
STRONG_CAPS = {"database": 1, "backend": 1, "frontend": 1, "qa": 1}
PRODUCT_DICT = {"core_features": ["登录", "注册"]}


def _engine(tmp_path: Path, **kw) -> DEC.DecomposeEngine:
    ws = tmp_path / "ws"
    ws.mkdir()
    return DEC.DecomposeEngine(workspace=ws, project_id="demo", **kw)


class TestCompositeToAtomic:
    def test_leaves_all_atomic_four_conditions(self, tmp_path):
        eng = _engine(tmp_path)
        r = eng.decompose(dict(COMPOSITE), product=PRODUCT_DICT, capabilities=STRONG_CAPS)
        assert r.error is None
        assert len(r.leaves) >= 4  # 2 features × 4 技术层 = 8
        for leaf in r.leaves:
            # ① agent_type 单数（strong caps 下候选=1）
            assert leaf["agent_type"] in STRONG_CAPS
            assert STRONG_CAPS[leaf["agent_type"]] == 1
            # ② 单文件（target_file 恰好 1 个）
            files = DEC.DecomposeEngine.extract_files(leaf)
            assert len(files) == 1, f"{leaf['id']} 应单文件: {files}"
            # ③ 可验证（verify_cmd 存在）
            assert leaf["verify_cmd"], f"{leaf['id']} 缺验证命令"
            # ④ ≤10 分钟
            assert leaf["est_minutes"] <= 10, f"{leaf['id']} 估计 {leaf['est_minutes']}min"
            # 诚实标注
            assert leaf["verified"] is True
            assert leaf["unverified"] is False

    def test_tree_has_compound_and_atomic_nodes(self, tmp_path):
        eng = _engine(tmp_path)
        r = eng.decompose(dict(COMPOSITE), product=PRODUCT_DICT, capabilities=STRONG_CAPS)
        types = {n["type"] for n in r.tree}
        assert "compound" in types and "atomic" in types
        # 叶子 id 全在 tree 里
        tree_ids = {n["id"] for n in r.tree}
        assert all(lf["id"] in tree_ids for lf in r.leaves)


class TestIsAtomic:
    def test_single_file_atomic(self, tmp_path):
        eng = _engine(tmp_path)
        task = {
            "id": "t1",
            "name": "修复 main.py",
            "goal": "修复 main.py 的 bug",
            "requirement": "修复 main.py",
            "agent_type": "backend",
            "verify_cmd": "pytest main.py",
        }
        ok, reasons = eng.is_atomic(task, STRONG_CAPS)
        assert ok is True
        assert reasons == []

    def test_multi_file_not_atomic(self, tmp_path):
        eng = _engine(tmp_path)
        task = {
            "id": "t2",
            "name": "改 main.py 和 util.py",
            "goal": "改 main.py 和 util.py",
            "requirement": "改 main.py 和 util.py",
            "agent_type": "backend",
        }
        ok, reasons = eng.is_atomic(task, STRONG_CAPS)
        assert ok is False
        assert any("2 个文件" in r for r in reasons)


class TestDepthConverges:
    def test_strong_caps_all_verified_weak_caps_honest_unverified(self, tmp_path):
        eng = _engine(tmp_path)
        task = dict(COMPOSITE)

        strong = eng.decompose(task, product={"core_features": ["登录"]}, capabilities=STRONG_CAPS)
        # 弱能力: backend 有 2 个候选 → backend 任务无法单 Agent → 诚实 unverified
        weak = eng.decompose(
            task,
            product={"core_features": ["登录"]},
            capabilities={"database": 1, "backend": 2, "frontend": 1, "qa": 1},
        )

        assert strong.state["stats"]["atomic_verified"] > weak.state["stats"]["atomic_verified"]
        assert weak.state["stats"]["unverified"] >= 1
        # 能力不足 → 诚实标注（不伪造原子性）
        weak_backend = [lf for lf in weak.leaves if lf["agent_type"] == "backend"]
        assert weak_backend and all(lf["verified"] is False for lf in weak_backend)


class TestCycleRejected:
    def test_cycle_via_llm_rejected_with_event(self, tmp_path):
        eng = _engine(tmp_path)

        def loop_llm(task, product):
            # 返回与祖先同 id 的子任务 → 成环
            if task.get("id") == "root":
                return [{"id": "root", "name": "循环子任务"}]
            return []

        r = eng.decompose(dict(COMPOSITE), product={}, llm_fn=loop_llm)
        assert "DECOMPOSE_CYCLE_REJECTED" in r.state["events"]
        assert r.error and "环" in r.error


class TestNoLlmFallback:
    def test_deterministic_split_nonempty_honest(self, tmp_path):
        eng = _engine(tmp_path)
        # llm_fn=None → 全确定性路径
        r = eng.decompose(dict(COMPOSITE), product=PRODUCT_DICT, capabilities=STRONG_CAPS)
        assert len(r.leaves) >= 4
        assert "DECOMPOSE_STARTED" in r.state["events"]
        assert "DECOMPOSE_COMPLETED" in r.state["events"]
        # 无 LLM 不伪造: 每个叶子要么 verified 由确定性四条件支撑, 要么 unverified 诚实标注
        for lf in r.leaves:
            assert lf["verified"] in (True, False)
            assert lf["unverified"] is (not lf["verified"])


class TestMaxDepth:
    def test_depth_cap_honest_unverified(self, tmp_path):
        eng = _engine(tmp_path, max_depth=1)
        r = eng.decompose(dict(COMPOSITE), product=PRODUCT_DICT, capabilities=STRONG_CAPS)
        assert r.state["stats"]["unverified"] >= 1
        assert all(lf["depth"] <= 1 for lf in r.leaves)
        assert any(lf.get("depth_cap") for lf in r.leaves)


class TestStatePersisted:
    def test_decomposition_json_written(self, tmp_path):
        eng = _engine(tmp_path)
        eng.decompose(dict(COMPOSITE), product=PRODUCT_DICT, capabilities=STRONG_CAPS)
        out = tmp_path / "ws" / "projects" / "demo" / "decomposition.json"
        assert out.is_file()
        import json

        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["project_id"] == "demo"
        assert data["stats"]["leaf_count"] == len(data["leaves"])
        assert "events" in data


class TestBackwardCompat:
    def test_feature_task_generator_still_works(self, tmp_path):
        """旧 TaskTree/FeatureTaskGenerator 流程不破坏（引擎独立）。"""
        product = PRODUCT.ProductIntent(
            name="测试产品",
            problem="测试问题",
            user="测试用户",
            core_features=["登录", "注册"],
        )
        tree = PIPELINE.FeatureTaskGenerator.from_product(product)
        assert tree.get("count", 0) >= 1
        assert all("id" in t for t in tree.get("tasks", []))

    def test_task_tree_still_works(self, tmp_path):
        tree = PIPELINE.TaskTree.from_engineering({"modules": ["auth"]})
        assert len(tree.get("tasks", [])) == 4  # db/api/frontend/test


class TestComplexSemanticsInheritance:
    def test_refactor_task_children_honest_unverified(self, tmp_path):
        """重构/迁移等复杂语义必须传递到子任务——不伪造原子性（§5.12.6③ 铁律）。

        回归: "重构用户模块" 的 goal 在 feature 层曾被 "实现功能: 用户管理"
        覆盖 → 子任务误判 verified。修复后子任务继承 "重构" hint → unverified。
        """
        eng = _engine(tmp_path)
        r = eng.decompose(
            {"id": "root", "name": "重构用户模块", "goal": "重构用户模块",
             "requirement": "重构用户模块的数据库层和后端接口"},
            product={"core_features": ["用户管理"]},
            capabilities=STRONG_CAPS,
        )
        assert len(r.leaves) >= 1
        # 含"重构"的子任务必须是 unverified 诚实标注（不是 ≤10min 原子）
        for leaf in r.leaves:
            assert leaf["verified"] is False, f"{leaf['id']} 不应伪造原子性"
            assert leaf["unverified"] is True
            # 语义已传递: goal 含"重构"
            assert "重构" in leaf["goal"]
            # est 记录真实估计（>10 说明判定为超时）
            assert leaf["est_minutes"] > 10
