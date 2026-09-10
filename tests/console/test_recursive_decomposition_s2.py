"""S1 第 7 刀 — 递归任务树测试 (LLM 主导 · 业务/数据内聚 · 拆到原子)。

A. 小任务早原子 → 2-3 层, degraded=False。
B. 复合任务 (电商后台) → depth ≥4; 业务不被撕 (下单/支付/订单同"订单"祖先);
   数据强制: 同文件写冲突 → depends_on 串行 / 成环拒绝 degraded。
C. 诚实降级: LLM 失败/非法/超深 → degraded=True 非空。
D. 契约: Plan.tasks == 全部叶 (golden_path e2e 绿)。
E. 回归: test_task_decomposition 8 全绿 (模板路径未动)。
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "factory-core")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


from factory_console import task_decomposition as td  # noqa: E402


def _prd(*, goal: str = "电商后台系统") -> dict:
    return {
        "id": "prd-ecom-1",
        "version": 1,
        "content": {
            "overview": {"name": "电商后台", "problem": goal},
            "functional_requirements": ["商品管理", "订单管理", "用户管理",
                                        "支付对接"],
        },
    }


def _mk_interp(json_out: str):
    def fake_llm(prompt: str) -> str:
        return json_out
    return td.build_llm_decomposer(llm_fn=fake_llm)


# 4+ 层递归 JSON: 电商 → 订单(下单/支付/状态流转 同子树) + 商品 + 用户
_ECOM_4LEVEL = """{"root":{"name":"电商后台","scope":"后台管理系统","atomic":false,
"subtasks":[
 {"name":"订单域","scope":"订单全链路(下单→支付→状态流转)","atomic":false,
  "subtasks":[
   {"name":"订单核心","atomic":false,
    "subtasks":[
     {"name":"下单创建订单","atomic":true,"business_rule":"用户下单生成订单,扣库存",
      "data_entities":[{"entity":"orders","ops":["write"]},{"entity":"stock","ops":["write"]}],
      "change_type":"NEW_FILE","expected_files":["order.js"],"verify_hint":"单测下单接口"},
     {"name":"支付对接","atomic":true,"business_rule":"订单支付,回调更新状态",
      "data_entities":[{"entity":"orders","ops":["write"]},{"entity":"payments","ops":["write"]}],
      "change_type":"NEW_FILE","expected_files":["pay.js"],"verify_hint":"支付回调单测"},
     {"name":"订单状态流转","atomic":true,"business_rule":"待支付→已支付→已发货状态机",
      "data_entities":[{"entity":"orders","ops":["write"]}],
      "change_type":"MODIFY","expected_files":["order.js"],"verify_hint":"状态机单测"}
    ]}]},
 {"name":"商品域","scope":"商品CRUD","atomic":false,
  "subtasks":[
   {"name":"商品维护","atomic":true,"business_rule":"商品增删改查",
    "data_entities":[{"entity":"products","ops":["write"]}],
    "change_type":"NEW_FILE","expected_files":["product.js"],"verify_hint":"CRUD 单测"}
  ]},
 {"name":"用户域","scope":"用户管理","atomic":false,
  "subtasks":[
   {"name":"用户维护","atomic":true,"business_rule":"用户增删改查",
    "data_entities":[{"entity":"users","ops":["write"]}],
    "change_type":"NEW_FILE","expected_files":["user.js"],"verify_hint":"CRUD 单测"}
  ]}
]}}"""


class TestSmallTaskEarlyAtomic:
    def test_timer_2_3_levels(self) -> None:
        """A: 小任务 (番茄钟) → LLM 判原子早 → 浅树。"""
        out = """{"root":{"name":"番茄钟","atomic":false,"subtasks":[
          {"name":"倒计时UI","atomic":true,
           "business_rule":"显示倒计时,到0停止",
           "data_entities":[{"entity":"timer.js","ops":["write"]}],
           "change_type":"NEW_FILE","expected_files":["timer.js"],
           "verify_hint":"打开页面看到倒计时"},
          {"name":"提示音","atomic":true,
           "business_rule":"到0播放提示音",
           "data_entities":[{"entity":"timer.js","ops":["write"]}],
           "change_type":"NEW_FILE","expected_files":["sound.js"],
           "verify_hint":"到0听到声音"}]}}"""
        tree = td.decompose_prd(_prd(goal="番茄钟网页"), interpreter=_mk_interp(out))
        s = td.tree_summary(tree)
        assert not s["degraded"]
        assert s["depth"] in (2, 3), s  # project→(domain?)→leaf — 原子早则浅
        leaves = td.tree_leaves(tree)
        assert all(leaf["verify_hint"] for leaf in leaves)  # 叶原子带验证


class TestCompositeBusinessDataCohesion:
    def test_depth_ge_4(self) -> None:
        """B1: 电商复合任务 → 深度 ≥4 (非写死 3)。"""
        tree = td.decompose_prd(_prd(), interpreter=_mk_interp(_ECOM_4LEVEL))
        s = td.tree_summary(tree)
        assert s["depth"] >= 4, s
        assert not s["degraded"], s.get("warnings")

    def test_business_chain_not_torn(self) -> None:
        """B2: 下单/支付/状态流转 同属"订单域"祖先 (业务内聚不被撕)。"""
        tree = td.decompose_prd(_prd(), interpreter=_mk_interp(_ECOM_4LEVEL))
        by_id = {n["id"]: n for n in tree["nodes"]}
        order_domains = [n for n in tree["nodes"]
                         if "订单" in str(n.get("title", "")) and n["kind"] != "task"]
        assert order_domains, "无订单域"
        dom = order_domains[0]
        dom_id = dom["id"]
        # 收集该子树内所有叶
        dom_leaves = []
        for leaf_id in tree["leaves"]:
            node = by_id[leaf_id]
            # 沿 parent 链上溯
            cur = node
            while cur and cur.get("parent_id"):
                cur = by_id.get(cur["parent_id"])
                if cur and cur["id"] == dom_id:
                    dom_leaves.append(node["title"])
                    break
        assert any("下单" in t for t in dom_leaves), dom_leaves
        assert any("支付" in t for t in dom_leaves), dom_leaves
        assert any("状态流转" in t for t in dom_leaves), dom_leaves

    def test_same_file_write_gets_serialized(self) -> None:
        """B3: 两叶并行写同一文件 → 校验器注入 depends_on 串行边。"""
        out = """{"root":{"name":"订单","atomic":false,"subtasks":[
          {"name":"下单","atomic":true,"business_rule":"创建订单",
           "data_entities":[{"entity":"orders","ops":["write"]}],
           "change_type":"NEW_FILE","expected_files":["order.js"],
           "verify_hint":"test"},
          {"name":"支付","atomic":true,"business_rule":"支付订单",
           "data_entities":[{"entity":"orders","ops":["write"]}],
           "change_type":"MODIFY","expected_files":["order.js"],
           "verify_hint":"test"}]}}"""
        tree = td.decompose_prd(_prd(goal="订单"), interpreter=_mk_interp(out))
        leaves = td.tree_leaves(tree)
        # 后叶 (支付) 应 depends_on 先叶 (下单)
        pay = next(leaf for leaf in leaves if "支付" in leaf["title"])
        order = next(leaf for leaf in leaves if "下单" in leaf["title"])
        assert order["id"] in pay["depends_on"], (
            f"同文件写冲突未串行化: pay.depends_on={pay['depends_on']}")
        assert not tree.get("degraded"), "合法串行不应 degraded"


class TestHonestDegrade:
    def test_llm_failure(self) -> None:
        def bad(prompt: str) -> str:
            raise RuntimeError("down")
        interp = td.build_llm_decomposer(llm_fn=bad)
        tree = td.decompose_prd(_prd(), interpreter=interp)
        assert tree["degraded"] is True
        assert len(td.tree_leaves(tree)) >= 1

    def test_invalid_json(self) -> None:
        tree = td.decompose_prd(_prd(), interpreter=_mk_interp("不是JSON"))
        assert tree["degraded"] is True

    def test_no_subtasks_forced_leaf_with_warning(self) -> None:
        """atomic=false 无 subtasks → 强制收叶 + warnings (不静默)。"""
        out = """{"root":{"name":"X","atomic":false,
                "subtasks":[{"name":"空节点","atomic":false}]}}"""
        tree = td.decompose_prd(_prd(), interpreter=_mk_interp(out))
        assert len(td.tree_leaves(tree)) >= 1
        assert tree.get("warnings"), "应记录强制收叶 warning"

    def test_truncated_json_partial_tree_degraded(self) -> None:
        """LLM 输出截断 (数组内元素被切) → 部分树 + degraded (不整棵丢)。"""
        out = ('{"root":{"name":"电商","atomic":false,"subtasks":['
               '{"name":"订单","atomic":false,"subtasks":['
               '{"name":"下单","atomic":true,'
               '"expected_files":["order.js"],"verify_hint":"t"}]}]},'
               '{"name":"支付","atomic":false,"subtasks":[{"name":"支付网关"')
        tree = td.decompose_prd(_prd(), interpreter=_mk_interp(out))
        assert tree["degraded"] is True, "截断应诚实 degraded"
        leaves = td.tree_leaves(tree)
        assert len(leaves) >= 1, "部分树保留已给叶"
        assert any("下单" in leaf["title"] for leaf in leaves)


class TestPlanContract:
    def test_plan_tasks_equals_leaves(self) -> None:
        """D: tree_to_plan summaries == 全部叶 (拓扑序)。"""
        tree = td.decompose_prd(_prd(), interpreter=_mk_interp(_ECOM_4LEVEL))
        summaries, order = td.tree_to_plan(tree)
        leaves = td.tree_leaves(tree)
        assert len(summaries) == len(leaves) == len(order)
        for s in summaries:
            assert s["change_type"] in td.CHANGE_TYPES
            assert "verify_hint" in s  # 叶带验证提示
