#!/usr/bin/env python3
"""用户视图（两个投影）端到端冒烟 —— 功能链路图 / 层级待办清单的**不变式门**。

为什么需要它:
    Founder 实测: "功能链路图 有问题，一直在堆砌，看不懂"。
    根因不是配色也不是字号 —— 旧版把递归拆解产出的 73 个 domain **全拍平**,
    再把关系写成行内文字（"前置: A / B"），关系因此看不见。
    而本仓 pytest 只能收集 examples/demo 的 add/sub（见 scripts/verify.sh 自述）
    ⇒ 视图层零守卫: 把节点拍平、把边丢掉, verify 一条都不会红 ✗
    本脚本把那次实测的判据固化成机器门（设计原文 §6 + 交付后的实测）。

覆盖（每条对应一次真实血案或设计原文）:
    ① 节点范围: 有嵌套（domain→domain）时只出【顶层模块】（parent_id 不是 domain 的）
    ② 不丢信息: 顶层数 + 子树里的 domain 数 == 全部 domain 数（折叠 ≠ 删除）
    ③ 关系可见: 有依赖 ⇒ 必须给 edges（渲染方要拿去画线）; ★ 用 id, 不用名字
    ④ 边自洽:   端点在图内 · 无自环 · ★ 无倒流（前置层 ≤ 后续层, 否则箭头朝上）
    ⑤ 批次覆盖: 全部顶层模块各出现且仅一次
    ⑥ 有环不崩: 互相依赖 ⇒ 整批一层（不阻塞 · 不静默丢）
    ⑦ 指向子模块的依赖 ⇒ 落 external_deps（不静默丢, 渲染方提示"展开看"）
    ⑧ 两投影同源: todo / flow 同一 plan_id, 且链路图的模块在清单里都点得到
    ⑨ 退化保护: 空节点树不崩; 单模块树仍给 1 个模块（不退化成空视图）

用法: python scripts/smoke_user_view.py [--root DIR]
       不带 --root ⇒ tempdir 造真树文件走真实读取路径（不碰真实数据 ✓）
       带 --root   ⇒ 额外把该数据根下的真树全扫一遍（诊断用, 不进 verify.sh）
退出码: 0=通过 / 1=失败（任何一条不成立即红 —— 它是 verify.sh 的门）
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ai_factory_os.services.work import decomposition as D  # noqa: E402
from ai_factory_os.services.work import user_view as UV  # noqa: E402


def _node(nid: str, kind: str, parent: str, title: str,
          deps: tuple[str, ...] = ()) -> dict:
    return {
        "id": nid, "kind": kind, "parent_id": parent, "title": title,
        "display_name": "", "depends_on": list(deps), "status": "todo",
        "expected_files": [], "acceptance": "", "required_capabilities": [],
    }


def _tree(plan_id: str, nodes: list[dict]) -> dict:
    return {"plan_id": plan_id, "project_id": "P1", "status": "candidate",
            "created_at": "2026-09-20T00:00:00", "nodes": nodes}


def _write(root: Path, tree: dict) -> None:
    """落成真实树文件（projects/<P>/tasks/PLAN-*.json）—— 走真实读取路径。"""
    d = root / "projects" / tree["project_id"] / "tasks"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{tree['plan_id']}.json").write_text(
        json.dumps(tree, ensure_ascii=False, indent=1), encoding="utf-8")


def _must_load(root: Path, plan_id: str, project_id: str) -> dict:
    """读一棵【必须存在】的树 —— 读不到是脚本自己的错, 响亮失败不静默。"""
    got = D.load_tree(root, plan_id, project_id)
    if got is None:
        raise SystemExit(f"✗ 读不到刚写的树: {plan_id}（fixture 或读取路径坏了）")
    return got


def _flow_invariants(flow: dict, tree: dict) -> list[str]:
    """flow 投影的通用不变式 —— 返回违规描述列表（空 = 全过）。"""
    bad: list[str] = []
    root = flow.get("root") or []
    ids = {m["id"] for m in root}
    lvl = {m["id"]: m.get("level") for m in root}
    dom_ids = {str(n.get("id")) for n in tree["nodes"] if n.get("kind") == "domain"}

    if flow.get("modules") != len(root):
        bad.append("modules 与 root 数不符")
    if root and (0 in set(lvl.values()) or None in set(lvl.values())):
        bad.append("有模块没分到批次")

    # ② 不丢信息: 折叠 ≠ 删除 —— ★ 必须【递归】数（子模块下面还有孙模块; 实测真树 13+56+4=73）
    def _desc(m: dict) -> int:
        return sum(1 + _desc(c) for c in (m.get("children") or []))
    kids_total = sum(_desc(m) for m in root)
    if len(root) + kids_total != len(dom_ids):
        bad.append(f"模块+子模块(递归 {len(root)}+{kids_total}) != 全部 domain ({len(dom_ids)}) 信息丢了")
    for m in root:
        if m.get("kids") != len(m.get("children") or []):
            bad.append("kids 计数与 children 不符")

    # ① 顶层定义: 每个 top 的 parent 都不该是 domain
    for m in root:
        if m["id"] in {str(k) for k in (m.get("children") or [])}:
            bad.append("父子成环")

    # ④ 边自洽
    for e in flow.get("edges") or []:
        if e["from"] not in ids or e["to"] not in ids:
            bad.append(f"边端点不在图内: {e}")
        elif e["from"] == e["to"]:
            bad.append("自环边")
        elif lvl.get(e["from"], 10**6) > lvl.get(e["to"], -1):
            bad.append(f"边倒流（箭头朝上）: {e}")

    # ⑤ 批次覆盖: 各出现且仅一次
    flat = [m["id"] for b in flow.get("batches") or [] for m in b["nodes"]]
    if sorted(flat) != sorted(ids):
        bad.append("批次未覆盖全部顶层模块（或重复）")
    return bad


def _check(root: Path, plan_id: str, tree: dict, results: list) -> None:
    """一棵树的全部断言 —— 结果追加进 results（name, ok, got）。"""
    flow = UV.build_flow(tree)
    todo = UV.build_todo(tree)
    bad = _flow_invariants(flow, tree)

    # ③ 关系可见: 顶层之间存在依赖 ⇒ 必须给 edges（用 id）
    tops = {m["id"] for m in flow["root"]}
    want = sum(1 for n in tree["nodes"]
               if str(n.get("id")) in tops and n.get("depends_on"))
    if want and not flow.get("edges"):
        bad.append("有依赖却没有任何 edges（关系被藏起来了）")

    # ⑦ 指向子模块的依赖必须单列, 不静默丢
    external = flow.get("external_deps") or []
    outside_want = sum(1 for n in tree["nodes"] if str(n.get("id")) in tops
                       for d in (n.get("depends_on") or []) if str(d) not in tops)
    if len(external) != outside_want:
        bad.append(f"external_deps 数不符: {len(external)} != {outside_want}")

    # ⑧ 两投影同源 + 对得上（设计 §4.2 ②）
    if todo.get("plan_id") != flow.get("plan_id"):
        bad.append("两个投影的 plan_id 不一致（不同源）")
    names = {ln.get("name") for ln in todo.get("lines") or []}
    for m in flow["root"]:
        if m["name"] not in names:
            bad.append(f"链路图的模块在清单里点不到: {m['name']}")
    # ★ 跨视图联动的【键】: 两个投影必须共享同一批模块 id
    #   （界面上点链路图的模块要能定位到清单那一块 —— 靠的就是这个 id; 缺了就只能靠名字猜）
    todo_ids = {str(ln.get("id") or "") for ln in todo.get("lines") or []}
    miss_id = [m["id"] for m in flow["root"] if m["id"] not in todo_ids]
    if miss_id:
        bad.append(f"链路图的模块 id 不在清单里（界面无法联动）: {miss_id[:3]}")
    results.append((f"{plan_id} 不变式", not bad, "；".join(sorted(set(bad)))))

    # 无环树: 边必须是严格向下（同层边只在有环时才允许）
    if not D.detect_cycles(tree["nodes"]):
        same = sum(1 for e in flow.get("edges") or []
                   if {m["id"]: m["level"] for m in flow["root"]}[e["from"]]
                   == {m["id"]: m["level"] for m in flow["root"]}[e["to"]])
        results.append((f"{plan_id} 无环 ⇒ 边严格向下", same == 0, f"同层边 {same} 条"))


def _fixtures() -> list[tuple[str, dict]]:
    """造树: 覆盖 嵌套 / 依赖 / 指向子模块 / 环 / 单模块 / 空。"""
    nest = _tree("PLAN-nest", [
        _node("p", "project", "", "电商系统"),
        _node("d1", "domain", "p", "模块 1: scaffold"),
        _node("d2", "domain", "p", "模块 2: database", deps=("d1",)),
        _node("d3", "domain", "p", "模块 3: product", deps=("d1", "d2")),
        _node("d3a", "domain", "d3", "建商品表"),
        _node("d3b", "domain", "d3", "商品接口", deps=("d3a",)),
        _node("d3b1", "domain", "d3b", "接口签名与分页"),   # ★ 孙模块（三层）
        _node("d4", "domain", "p", "模块 4: order", deps=("d3a",)),
        _node("t1", "task", "d3a", "写 schema"),
    ])
    cyc = _tree("PLAN-cycle", [
        _node("p", "project", "", "环"),
        _node("a", "domain", "p", "模块 A", deps=("b",)),
        _node("b", "domain", "p", "模块 B", deps=("a",)),
    ])
    single = _tree("PLAN-single", [
        _node("p", "project", "", "单模块"),
        _node("only", "domain", "p", "唯一模块"),
    ])
    empty = _tree("PLAN-empty", [_node("p", "project", "", "空")])
    return [("嵌套树", nest), ("有环树", cyc), ("单模块树", single), ("空树", empty)]


def _write_schema(root: Path) -> Path:
    """造一个真实数据模型文件（带外键）—— 数据流判据用它当"真实来源"。"""
    proj = root / "projects" / "P1"
    (proj / "server").mkdir(parents=True, exist_ok=True)
    (proj / "server" / "schema.prisma").write_text(
        "model User { id Int @id }\n"
        "model Order { id Int @id\n  user User @relation(fields: [userId], references: [id])\n  userId Int }\n"
        "model Payment { id Int @id\n  order Order @relation(fields: [orderId], references: [id])\n  orderId Int }\n",
        encoding="utf-8")
    return proj


def _check_dataflow(root: Path) -> list[str]:
    """★ 数据流程图（投影 C）的判据 —— 返回违规描述（空 = 全过）。

    只验一件事: **图上每条线都必须有真实来源**（DDL / 产线声明）。
    文案匹配只许作【线索】, 且必须如实报覆盖率与未覆盖模块 —— 不许把线索当事实。
    """
    from ai_factory_os.services.work import data_flow as DF

    bad: list[str] = []
    proj = _write_schema(root)
    tree = _tree("PLAN-df", [
        _node("p", "project", "", "数据流"),
        _node("m1", "domain", "p", "模块一"),                       # 有声明
        _node("m2", "domain", "p", "模块二"),                       # 只有文案线索
        _node("m3", "domain", "p", "模块三"),                       # 没有任何线索
    ])
    tree["nodes"][1]["data_entities"] = [{"name": "Order", "access": "write"}]
    tree["nodes"][2]["scope"] = "实现 Payment 对账与退款的写库逻辑"

    d = DF.build_data_flow(tree, proj)
    names = {e["name"] for e in d["entities"]}
    # ① 真实来源: 实体/关系统统来自 DDL
    if names != {"User", "Order", "Payment"}:
        bad.append(f"实体抽取不对: {sorted(names)}")
    if len(d["relations"]) != 2:
        bad.append(f"外键条数不对: {len(d['relations'])}")
    # ② 声明优先于线索
    m1 = [k for k in d["module_links"] if k["module_id"] == "m1"]
    if not all(k["kind"] == "declared" for k in m1) or not m1:
        bad.append("有声明的模块未走 declared")
    # ③ 线索只作线索 + 名字必须在真实清单里（不许编）
    m2 = [k for k in d["module_links"] if k["module_id"] == "m2"]
    if not m2 or not all(k["kind"] == "evidence" for k in m2):
        bad.append("文案提到的实体未标为 evidence")
    invented = [k["entity"] for k in d["module_links"] if k["entity"] not in names]
    if invented:
        bad.append(f"出现了清单外的实体（编的）: {invented}")
    # ④ 全部顶层模块都要给（缺线的也要画出来）
    if {m["id"] for m in d["modules"]} != {"m1", "m2", "m3"}:
        bad.append("modules 未覆盖全部顶层模块")
    # ⑤ 覆盖率与未覆盖清单如实
    if d["coverage"]["missing"] != ["模块三"] or d["coverage"]["with_entity"] != 2:
        bad.append(f"覆盖率/缺口不对: {d['coverage']}")
    # ⑥ 没有 DDL 且没有声明 ⇒ 明说没有, 不编图
    bare = _tree("PLAN-bare", [_node("p", "project", "", "裸"),
                               _node("x", "domain", "p", "模块X")])
    d2 = DF.build_data_flow(bare, root / "projects" / "P_none")
    if d2["available"] or d2["entities"]:
        bad.append("无 DDL 无声明时仍给出了实体（编的）")
    # ⑦ 无 DDL 但有声明 ⇒ 实体来自【声明】, 不许因为实体列里没有它就把线静默丢掉
    d3 = DF.build_data_flow(tree, root / "projects" / "P_none")
    if [e["name"] for e in d3["entities"]] != ["Order"] or d3["entities"][0]["from"] != "declared":
        bad.append(f"无 DDL 时声明实体未进实体清单（线会被静默丢）: {d3['entities']}")
    if not any(k["kind"] == "declared" for k in d3["module_links"]):
        bad.append("无 DDL 时声明线丢了")
    return bad


def _check_declare(root: Path) -> list[str]:
    """产线声明（投影 C 的数据来源）: 落盘 ⇒ 视图必须变 declared; 空声明 ⇒ 清字段不留空壳。

    ★ 这条链断了就会出现"声明了但图没变"（同族: 写了没效果）—— 必须机器守。
    """
    from ai_factory_os.services.work import data_flow as DF
    from ai_factory_os.services.work import decomposition as D

    bad: list[str] = []
    _write_schema(root)                     # 独立可跑（pytest 里各自一份 tmp）
    tree = _tree("PLAN-dec", [_node("p", "project", "", "声明"),
                              _node("m1", "domain", "p", "模块一"),
                              _node("m2", "domain", "p", "模块二")])
    _write(root, tree)                      # 声明是"读-改-写" ⇒ 必须走真实存储
    D.declare_node_entities(root, "PLAN-dec", node_id="m1",
                            entities=[{"name": "Order", "access": "write"}], project_id="P1")
    t2 = _must_load(root, "PLAN-dec", "P1")
    if not next(n for n in t2["nodes"] if n["id"] == "m1").get("data_entities"):
        bad.append("声明没落盘")
    if t2.get("status") != "candidate":
        bad.append("声明后没回到候选态")
    d = DF.build_data_flow(t2, root / "projects" / "P1")
    if d["declared_count"] != 1 or not any(k["kind"] == "declared" for k in d["module_links"]):
        bad.append("声明没让视图变 declared（写了没效果）")
    D.declare_node_entities(root, "PLAN-dec", node_id="m1", entities=[], project_id="P1")
    t3 = _must_load(root, "PLAN-dec", "P1")
    if "data_entities" in next(n for n in t3["nodes"] if n["id"] == "m1"):
        bad.append("空声明没清掉字段（留了空壳）")
    # LLM 输出里的清单外名字必须被丢弃（不许写进树）
    from ai_factory_os.services.work.declare import _parse, parse_entity_spec
    kept, dropped = _parse('[{"name":"Order"},{"name":"编的"}]', {"Order", "User"})
    if [e["name"] for e in kept] != ["Order"] or dropped != 1:
        bad.append(f"清单外名字未被丢弃: kept={kept} dropped={dropped}")
    # 手动改（--set）: 写对了能解析; 名字不在真实清单里【必须当场报错】(人写的不能静默吞)
    if parse_entity_spec(["Order:write", "User"], {"Order", "User"}) != [
            {"name": "Order", "access": "write"}, {"name": "User", "access": "both"}]:
        bad.append("手动声明解析不对（Order:write / User ⇒ both）")
    for spec, why in ([["编的:read"], "清单外的实体名"], [["Order:删"], "非法 access"],
                      [[]], "空输入"):
        try:
            parse_entity_spec(spec if isinstance(spec, list) else [], {"Order", "User"})
            bad.append(f"手动声明该报错却通过了: {why}")
        except ValueError:
            pass
    return bad


def _check_mermaid(flow: dict, dataflow: dict) -> list[str]:
    """CLI 的 mermaid 输出必须【结构自洽】—— 否则贴进渲染器就是一堆报错（设计 §4.3）。"""
    import re

    from apps.cli.main import _dataflow_mermaid, _flow_mermaid

    bad: list[str] = []
    for label, src in (("flow", _flow_mermaid(flow)), ("dataflow", _dataflow_mermaid(dataflow))):
        body = "\n".join(ln for ln in src.splitlines() if ln.strip())
        head = body.splitlines()[0].strip() if body else ""
        if head not in ("flowchart TB", "flowchart LR"):
            bad.append(f"{label} 首行不是 flowchart: {head!r}")
        sub = len(re.findall(r"^\s*subgraph ", body, re.M))
        end = len(re.findall(r"^\s*end$", body, re.M))
        if sub != end:
            bad.append(f"{label} subgraph/end 不平衡: {sub}/{end}")
        defined = set(re.findall(r"^\s*([A-Z]\d+)[\[(]", body, re.M))
        used = set(re.findall(r"^\s*([A-Z]\d+)\s*(?:-->|==>|-\.)", body, re.M))
        if used - defined:
            bad.append(f"{label} 悬空引用: {sorted(used - defined)}")
        if not defined:
            bad.append(f"{label} 一个节点都没定义")
    return bad


def _check_linkage_wiring() -> list[str]:
    """页面层的联动【接线】必须齐全 —— 少一处, 联动就静默失效（就是当初的 bug 类型）。

    ★ 这是【结构检查】, 不是行为检查: 真正的联动已由浏览器 DOM 断言验过（点一处三张图都亮）;
      这里只保证接线不被误删 / 不被重构吃掉。行为验证需要浏览器, 不进 verify.sh。
    """
    page_file = _REPO_ROOT / "apps" / "api" / "index.html"
    if not page_file.is_file():
        return [f"找不到页面文件: {page_file}"]
    page = page_file.read_text(encoding="utf-8")
    probes = [
        ('data-id="${esc(l.id)}"', "待办清单行没挂 data-id ⇒ 联动没有键"),
        ("data-depth=", "待办清单行没挂 data-depth ⇒ 算不出子树范围"),
        ("let SELECTED = null", "没有页面级共享选中状态"),
        ("function paintFlow(id)", "功能链路图缺『按 id 上色』函数"),
        ("function paintDf(id)", "数据流程图缺『按 id 上色』函数"),
        ("function paintTodo(id)", "待办清单缺『按 id 定位』函数"),
        ("function selectModule(id)", "没有共享的选中入口"),
        ("#todo .row[data-kind=\"domain\"]", "待办清单的模块行没接点击"),
        ("keydown", "没有 Esc 取消选中"),
    ]
    return [why for probe, why in probes if probe not in page]


def _pytest_root(tmp: Path) -> Path:
    """pytest 用: 把 fixture 树 + 数据模型落进 tmp_path（与冒烟共用同一批 fixture）。"""
    for _, tree in _fixtures():
        _write(tmp, tree)
    _write_schema(tmp)
    return tmp


# ── pytest 兼容层 ────────────────────────────────────────────────────
# 本仓 pytest 只收集 examples/demo 的 add/sub（见 verify.sh 自述）⇒ 视图层此前【pytest 覆盖不到】。
# 下面四个用例复用冒烟里的同一批检查（不另写一套判据）：`pytest scripts/smoke_user_view.py -q`
# 也能验证功能链路图 / 数据流程图 / 产线声明 / mermaid —— 两个入口（verify.sh 与 pytest）同源。
def test_flow_projection_invariants(tmp_path: Path) -> None:
    """功能链路图: 顶层范围 · 不丢信息 · 关系可见 · 边不自洽 · 批次覆盖 · 环 · 退化。"""
    from ai_factory_os.services.work import user_view as UV

    root = _pytest_root(tmp_path)
    for label, tree in _fixtures():
        got = _must_load(root, tree["plan_id"], tree["project_id"])
        assert _flow_invariants(UV.build_flow(got), got) == [], f"{label} 不变式被破坏"


def test_dataflow_sources_are_real(tmp_path: Path) -> None:
    """数据流程图: 实体/关系来自 DDL · 声明优先 · 线索不当事实 · 不许编 · 缺口如实。"""
    assert _check_dataflow(_pytest_root(tmp_path)) == []


def test_declare_reaches_view(tmp_path: Path) -> None:
    """产线声明: 落盘 ⇒ 视图变 declared · 空声明清字段 · 清单外名字丢弃。"""
    assert _check_declare(_pytest_root(tmp_path)) == []


def test_mermaid_is_wellformed(tmp_path: Path) -> None:
    """CLI mermaid: 首行 flowchart · subgraph/end 平衡 · 无悬空引用 · 非空。"""
    from ai_factory_os.services.work import data_flow as DF
    from ai_factory_os.services.work import user_view as UV

    root = _pytest_root(tmp_path)
    nest = _must_load(root, "PLAN-nest", "P1")
    assert _check_mermaid(UV.build_flow(nest), DF.build_data_flow(nest, root / "projects" / "P1")) == []


def test_linkage_wiring_present(tmp_path: Path) -> None:
    """跨视图联动的接线必须齐全（键/共享选中/三张图的定位函数/点击/Esc）。"""
    assert _check_linkage_wiring() == []


def main() -> int:
    ap = argparse.ArgumentParser(description="用户视图端到端冒烟（不变式门）")
    ap.add_argument("--root", default="", help="额外扫描的真实数据根（诊断用）")
    args = ap.parse_args()

    results: list[tuple[str, bool, str]] = []
    with tempfile.TemporaryDirectory(prefix="smoke-user-view-") as tmp:
        root = Path(tmp)
        for label, tree in _fixtures():
            _write(root, tree)
            got = _must_load(root, tree["plan_id"], tree["project_id"])
            results.append((f"{label} 读回", True, ""))
            _check(root, tree["plan_id"], got, results)

        # ① 顶层范围（这条直接对应"堆砌"血案: 拍平就必须红）
        nest = _must_load(root, "PLAN-nest", "P1")
        f = UV.build_flow(nest)
        results.append(("嵌套树 ⇒ 只出顶层(不拍平)", f["modules"] == 4,
                        f"modules={f['modules']}（应 4, 拍平会是 6）"))
        results.append(("嵌套树 ⇒ 子模块折叠可见", sum(m["kids"] for m in f["root"]) == 2,
                        f"子模块 {sum(m['kids'] for m in f['root'])} 个"))
        results.append(("嵌套树 ⇒ 关系条数", len(f["edges"]) == 3, f"edges={len(f['edges'])}"))
        results.append(("嵌套树 ⇒ 跨层边指向子模块", len(f["external_deps"]) == 1,
                        f"external={f['external_deps']}"))
        # ⑥ 有环不崩且不丢
        cyc_tree = _must_load(root, "PLAN-cycle", "P1")
        cyc = UV.build_flow(cyc_tree)
        results.append(("有环树 ⇒ 不崩且不丢",
                        cyc["modules"] == 2 and not _flow_invariants(cyc, cyc_tree),
                        f"modules={cyc['modules']} 批次={len(cyc['batches'])}"))
        # ⑨ 退化保护
        emp = UV.build_flow(_must_load(root, "PLAN-empty", "P1"))
        results.append(("空树 ⇒ 不崩、空图", emp["modules"] == 0 and emp["root"] == [],
                        f"modules={emp['modules']}"))
        one = UV.build_flow(_must_load(root, "PLAN-single", "P1"))
        results.append(("单模块 ⇒ 仍给 1 个", one["modules"] == 1, f"modules={one['modules']}"))
        # ⑦ 数据流程图（投影 C）: 每条线都要有真实来源
        df_bad = _check_dataflow(root)
        results.append(("数据流程图 判据(真实来源/不编)", not df_bad, "；".join(df_bad)))
        # ⑧ CLI 的 mermaid 输出（设计 §4.3）: 结构必须自洽
        from ai_factory_os.services.work import data_flow as _DF
        m_bad = _check_mermaid(UV.build_flow(nest), _DF.build_data_flow(nest, root / "projects" / "P1"))
        results.append(("CLI mermaid 结构自洽", not m_bad, "；".join(m_bad)))
        # ⑨ 产线声明 → 视图（写了必须有效果; 空声明不留空壳）
        dec_bad = _check_declare(root)
        results.append(("声明落盘⇒视图变实线", not dec_bad, "；".join(dec_bad)))
        # ⑩ 页面联动【接线】齐全（结构检查 —— 少一处联动会静默失效）
        lk_bad = _check_linkage_wiring()
        results.append(("页面联动接线齐全", not lk_bad, "；".join(lk_bad)))

    if args.root:
        rroot = Path(args.root).expanduser()
        trees = D.list_trees(rroot)
        print(f"   额外扫描真数据根 {rroot}: {len(trees)} 棵树")
        for t in trees:
            pid = str(t.get("plan_id") or "")
            got = D.load_tree(rroot, pid, str(t.get("project_id") or ""))
            if got:
                _check(rroot, pid, got, results)

    print("── 用户视图冒烟（功能链路图 / 层级待办清单 · 不变式门）")
    for name, ok, got in results:
        print(f"   [{'PASS' if ok else 'FAIL'}] {name}" + (f"   ← {got}" if got else ""))
    ok_n = sum(1 for _, v, _ in results if v)
    print(f"   {ok_n}/{len(results)} 通过")
    return 0 if ok_n == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
