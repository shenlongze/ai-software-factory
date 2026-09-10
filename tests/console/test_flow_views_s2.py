"""S1 第 9 刀 — Flow Views 视图层测试 (验收 A-L)。

tmp fixture 真走 canonical 链: 理解→PRD→approve→递归树(decomposer 注入,
4+ 层 + data_entities/depends_on)→approve→注入执行(fake capability)→
再对 build_flow_for 各格式渲染断言。

A md / B todo / C mindmap / D flow / E gantt / F dataflow /
G sequence+state+dag / H echarts graph+sankey / I html / J project view /
K API/CLI 同源 / L 诚实 (无验证→UNKNOWN; degraded→warning; 缺失→灰块)。
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "factory-core")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from factory_console import flow_views as fv  # noqa: E402
from factory_console import task_decomposition as td  # noqa: E402
from factory_console.api.flow import flow_route  # noqa: E402
from factory_console.canonical_golden_path import CanonicalGoldenPath  # noqa: E402

# 4+ 层递归 JSON (电商; 含 data_entities + 同文件写 → depends_on 注入)
_ECOM_DEEP = """{"root":{"name":"电商后台","scope":"后台系统","atomic":false,
"subtasks":[
 {"name":"订单域","scope":"订单全链路","atomic":false,
  "subtasks":[
   {"name":"订单核心","atomic":false,
    "subtasks":[
     {"name":"下单创建订单","atomic":true,
      "business_rule":"用户下单生成订单,扣库存",
      "data_entities":[{"entity":"orders","ops":["write"]},{"entity":"stock","ops":["write"]}],
      "change_type":"NEW_FILE","expected_files":["order.js"],"verify_hint":"单测下单"},
     {"name":"订单状态流转","atomic":true,
      "business_rule":"待支付→已支付状态机",
      "data_entities":[{"entity":"orders","ops":["write"]}],
      "change_type":"MODIFY","expected_files":["order.js"],"verify_hint":"状态机单测"}
    ]},
   {"name":"支付","atomic":true,
    "business_rule":"订单支付回调",
    "data_entities":[{"entity":"payments","ops":["write"]}],
    "change_type":"NEW_FILE","expected_files":["pay.js"],"verify_hint":"支付单测"}
  ]},
 {"name":"商品域","atomic":false,
  "subtasks":[
   {"name":"商品维护","atomic":true,"business_rule":"商品增删改查",
    "data_entities":[{"entity":"products","ops":["write"]}],
    "change_type":"NEW_FILE","expected_files":["product.js"],"verify_hint":"CRUD单测"}
  ]}
]}}"""


def _mk_decomposer(json_out: str):
    def fake_llm(prompt: str) -> str:
        return json_out
    return td.build_llm_decomposer(llm_fn=fake_llm)


def _fake_capability(input_data: dict[str, Any]) -> dict[str, Any]:
    task = (input_data or {}).get("task") or {}
    return {
        "ok": True,
        "output": {"task_id": task.get("id"), "title": task.get("title"),
                   "result": "ok"},
        "summary": f"fake executed: {task.get('title')}",
        "metadata": {"source": "test_flow_views_s2"},
    }


def _run_full_path(tmp_path: Path, *, attach_project: bool = False
                   ) -> tuple[str, str, CanonicalGoldenPath]:
    """真走 canonical 链; 返回 (root, conversation_id, orch)。"""
    orch = CanonicalGoldenPath(tmp_path, semantic=False,
                               decomposer=_mk_decomposer(_ECOM_DEEP))
    cid = orch.create_conversation(title="电商后台")["id"]
    orch.handle(cid, "我要做一个电商后台系统，支持订单、商品、支付")
    assert orch.handle(cid, "整理成 PRD")["kind"] == "lifecycle"
    assert orch.handle(cid, "就按这个做")["kind"] == "lifecycle"
    assert orch.handle(cid, "生成计划")["kind"] == "lifecycle"
    assert orch.handle(cid, "确认计划")["kind"] == "lifecycle"
    res = orch.handle(cid, "开始做", capability_fn=_fake_capability)
    assert res["kind"] == "lifecycle"
    pid = ""
    if attach_project:
        from factory_console import project_agile as pa
        from factory_console import project_os as po
        proj = po.create_project(tmp_path, title="电商后台系统")
        pid = proj["id"]
        pa.attach_project(tmp_path, cid, pid)
        st = orch.status(cid)["path"]
        prd_id = st["prds"][0]["id"]
        pa.add_prd_to_backlog(tmp_path, pid, prd_id, cid)
        sp = pa.create_sprint(tmp_path, pid, title="S1")
        pa.start_sprint(tmp_path, pid, sp["sprint_id"])
    return str(tmp_path), cid, orch


class TestAMdStages:
    def test_9_stages_and_truth(self, tmp_path: Path) -> None:
        root, cid, _ = _run_full_path(tmp_path)
        v = fv.build_conv_flow(root, cid)
        assert v["exists"]
        assert len(v["stage_list"]) == 9
        states = {it["key"]: it["state"] for it in v["stage_list"]}
        # 走过的阶段 = 有/非灰; 架构选择域无 Truth → 灰块
        assert states["idea"] == "有"
        assert states["task_tree"] == "有"
        assert states["execution"] == "有"
        assert states["architecture"] == "未实现"
        # 无验证证据 → UNKNOWN (fake capability 无 verification)
        assert states["verification"] == "UNKNOWN"
        md = fv.render_view(v, "md")
        for key, label in fv.CONV_STAGES:
            assert label in md, f"阶段 {key} 标签缺失: {label}"
        assert "未实现" in md and "UNKNOWN" in md


class TestBTodo:
    def test_checkbox_count_and_state(self, tmp_path: Path) -> None:
        root, cid, _ = _run_full_path(tmp_path)
        v = fv.build_conv_flow(root, cid)
        leaves = (v.get("tree") or {}).get("leaves", [])
        assert leaves, "树应有叶"
        todo = fv.render_view(v, "todo")
        assert todo.count("- [x]") == len(leaves)  # 全部 COMPLETED
        assert "- [ ]" not in todo.replace("- [x]", "")


class TestCMindmap:
    def test_deep_nesting_matches_tree(self, tmp_path: Path) -> None:
        root, cid, _ = _run_full_path(tmp_path)
        v = fv.build_conv_flow(root, cid)
        assert (v.get("tree") or {}).get("depth", 0) >= 4
        mm = fv.render_view(v, "mermaid:mindmap")
        assert mm.startswith("mindmap")
        # 深度不限: 最深叶 title 出现 (电商树含 4+ 层)
        for leaf in (v["tree"] or {}).get("leaves", []):
            assert leaf["title"] in mm


class TestDFlow:
    def test_grey_architecture_node(self, tmp_path: Path) -> None:
        root, cid, _ = _run_full_path(tmp_path)
        v = fv.build_conv_flow(root, cid)
        flow = fv.render_view(v, "mermaid:flow")
        assert flow.startswith("flowchart")
        assert ":::grey" in flow  # 灰块节点明示
        assert "架构选择" in flow and "未实现" in flow


class TestEGantt:
    def test_only_real_timestamps(self, tmp_path: Path) -> None:
        root, cid, _ = _run_full_path(tmp_path)
        v = fv.build_conv_flow(root, cid)
        runs = v.get("node_runs") or []
        assert runs, "执行后应有 node_runs"
        # 全部真实执行 (fake capability) 应有 started/completed
        real = [r for r in runs if r.get("started_at") and r.get("completed_at")]
        assert real, "node_runs 缺真实时间戳"
        g = fv.render_view(v, "mermaid:gantt")
        assert g.startswith("gantt")
        # 每个真实时间戳叶的 node_id 出现在甘特; 无编造日期 (剥离时区后比对)
        for r in real:
            assert fv._ts_gantt(r["node_id"]) or r["node_id"]  # noqa: SLF001
            assert r["node_id"] in g
            assert fv._ts_gantt(r["started_at"]) in g  # noqa: SLF001


class TestFDataflow:
    def test_edges_from_data_entities(self, tmp_path: Path) -> None:
        root, cid, _ = _run_full_path(tmp_path)
        v = fv.build_conv_flow(root, cid)
        df = fv.render_view(v, "mermaid:dataflow")
        assert df.startswith("flowchart")
        # 树带 data_entities (orders/payments/products)
        assert "orders" in df and "payments" in df and "products" in df
        assert "--" in df


class TestGSequenceStateDag:
    def test_legal_text_truth_consistent(self, tmp_path: Path) -> None:
        root, cid, _ = _run_full_path(tmp_path)
        v = fv.build_conv_flow(root, cid)
        seq = fv.render_view(v, "mermaid:sequence")
        assert seq.startswith("sequenceDiagram")
        st = fv.render_view(v, "mermaid:state")
        assert st.startswith("stateDiagram-v2")
        # 状态迁移以代码常量为准
        for s in fv.SPRINT_STATES:
            assert s in st
        for s in fv.NODE_RUN_STATES[:4]:
            assert s in st
        dag = fv.render_view(v, "mermaid:dag")
        assert dag.startswith("flowchart")


class TestHEcharts:
    def test_graph_and_sankey_json(self, tmp_path: Path) -> None:
        import json
        root, cid, _ = _run_full_path(tmp_path)
        v = fv.build_conv_flow(root, cid)
        g = json.loads(fv.render_view(v, "echarts:graph"))
        assert g["series"][0]["type"] == "graph"
        assert g["series"][0]["data"]
        s = json.loads(fv.render_view(v, "echarts:sankey"))
        assert s["series"][0]["type"] == "sankey"
        assert s["series"][0]["data"]


class TestIHtml:
    def test_single_file_with_table_and_cdn_note(self, tmp_path: Path) -> None:
        root, cid, _ = _run_full_path(tmp_path)
        v = fv.build_conv_flow(root, cid)
        h = fv.render_view(v, "html")
        assert h.startswith("<!DOCTYPE html>")
        assert "CDN" in h and "离线" in h  # CDN 注记 + 离线降级说明
        assert "| 阶段 |" in h  # 内嵌表格 (离线可读)


class TestJProjectView:
    def test_backlog_sprint_consistent_with_agile_json(
            self, tmp_path: Path) -> None:
        import json
        from factory_console import project_agile as pa
        root, cid, _ = _run_full_path(tmp_path, attach_project=True)
        st = CanonicalGoldenPath(root, semantic=False).status(cid)["path"]
        prd_id = st["prds"][0]["id"]
        pid = pa.get_project_by_conversation(root, cid)["project_id"]
        # 反查 project_agile.json 真值
        raw = json.loads(
            (Path(root) / "project_agile" / f"{pid}.json").read_text("utf-8"))
        v = fv.build_project_view(root, pid)
        assert v["exists"]
        assert v["title"]  # 有真实标题
        # backlog 全量一致
        assert len(v["backlog"]) == len(raw["backlog"])
        assert v["backlog_count"] == len(raw["backlog"])
        # 迷你流: 至少一条含 prd_id + conversation 反查 title
        flows = [b for b in v["backlog_flow"] if b.get("prd_id") == prd_id]
        assert flows and flows[0]["conversation_id"] == cid
        # sprint 卡: 统计一致
        sp = v["sprints"][0]
        raw_sp = raw["sprints"][0]
        assert sp["sprint_id"] == raw_sp["sprint_id"]
        assert sp["stats"] == raw_sp["stats"]
        # md project 渲染含 backlog/sprint/PRD
        md = fv.render_view(v, "md")
        assert "## Backlog" in md and "## Sprints" in md
        assert prd_id in md


class TestKApiCliSameSource:
    def test_api_route_matches_build_flow(self, tmp_path: Path) -> None:
        root, cid, _ = _run_full_path(tmp_path)
        r1 = flow_route("conversation", cid, format="md", root=root)
        r2 = fv.build_flow_for(root, "conversation", cid, "md")
        assert r1["ok"] and r2["ok"]
        assert r1["content"] == r2["content"]
        # kind 短写
        r3 = flow_route("conversation", cid, format="gantt", kind="mermaid",
                        root=root)
        assert r3["ok"] and r3["format"] == "mermaid:gantt"
        # 未知 scope/format 失败安全
        assert not flow_route("bogus", cid, root=root)["ok"]
        assert not flow_route("conversation", cid, format="nope",
                              root=root)["ok"]


class TestLHonest:
    def test_missing_conv_grey(self, tmp_path: Path) -> None:
        root, _, _ = _run_full_path(tmp_path)
        v = fv.build_conv_flow(root, "conv-nope")
        assert not v["exists"]
        assert "(不存在)" in fv.render_view(v, "md")

    def test_arch_grey_and_verification_unknown(self, tmp_path: Path) -> None:
        root, cid, _ = _run_full_path(tmp_path)
        v = fv.build_conv_flow(root, cid)
        miss = v.get("honest", {}).get("missing", [])
        assert "architecture" in miss       # 架构选择域未建 → 灰块
        assert "verification" in miss       # 无验证证据 → UNKNOWN
