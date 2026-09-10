"""factory-console/task_decomposition.py — Multi-level Task Tree 域 (S1 第 7 刀, canonical)。

把 approved PRD → **递归**多级任务树 (深度由复杂度决定, 不写死) 的 canonical 域。

S1-7 升级 (第 7 刀):
- LLM 递归主导: 每节点判"是否原子" (atomic=false → subtasks 继续拆; true → 收叶)。
  深度不写死 (护栏 MAX_DEPTH=8 / MAX_NODES=100)。
- 组织原则 (内建于提示词 + 校验器, 非口号):
  A. 业务内聚: 一个业务能力/规则/状态机收同一子树, 非叶=业务切片(scope), 叶=单一可验证行为。
  B. 数据所有权: 实体有唯一 owner 子树; 叶声明动哪些实体+op (read/write/migrate);
     两叶写同一实体/文件 → depends_on 串行化; 一叶 write 被另一叶 read → read depends_on write。
- 校验器 (LLM 不可靠, 代码兜底):
  · 叶级 expected_files 所有权唯一; 跨叶重复声明 → 自动按树序串行化 depends_on;
    若成环 → 拒绝该分支 + degraded=True 诚实标注。
  · 全树成环检测 (复用 session/decomposer 的 cycle 拒绝语义)。
- 模板兜底路径 (无 LLM) 行为不变 (Project→Domain→Leaf 3 层); 测试 8 个既有测试全绿。

边界 (AI Factory OS 收敛原则 / CT 断层 F2):
- 每叶 = 最小可执行工作单元; 执行语义由 production_run 图 + node_runtime 承担 (零改动)。
- 数据落盘 <root>/task_trees/{plan_id}.json; 叶带 change_type + expected_files + depends_on
  供 NO_OP/完成态判定。
"""
from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

#: 树节点 kind 白名单 (递归解析按深度取: 0=project, 1+=domain/module/capability/task)
NODE_KINDS = ("project", "domain", "module", "capability", "task")
#: 叶任务 change_type 白名单
CHANGE_TYPES = ("NEW_FILE", "MODIFY")
#: 模板功能域
_TEMPLATE_DOMAINS = ("setup", "feature", "constraint", "decision", "verify", "delivery")

#: S1-7 递归护栏 (可配)
MAX_DEPTH = 8       # 递归最大深度 (超限 → 强制收叶 + degraded)
MAX_NODES = 100     # 全树最大节点数 (超限 → 截断 + degraded)

_lock = threading.RLock()


# ------------------------------------------------------------------ 存储


def _tree_dir(root: str | Path) -> Path:
    return Path(root) / "task_trees"


def _tree_file(root: str | Path, plan_id: str) -> Path:
    return _tree_dir(root) / f"{plan_id}.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_task_tree(root: str | Path, plan_id: str,
                   tree: dict[str, Any]) -> dict[str, Any]:
    """原子写 <root>/task_trees/{plan_id}.json。"""
    p = _tree_file(root, plan_id)
    with _lock:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(tree, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        os.replace(tmp, p)
    return tree


def load_task_tree(root: str | Path, plan_id: str) -> dict[str, Any] | None:
    """读树; 不存在 → None (不抛)。"""
    p = _tree_file(root, plan_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


# ------------------------------------------------------------------ 结构


def _new_node(tree_id: str, *, kind: str, title: str, parent_id: str = "",
              prd_ref: str = "", change_type: str = "",
              expected_files: list[str] | None = None,
              depends_on: list[str] | None = None,
              scope: str = "") -> dict[str, Any]:
    node = {
        "id": f"{tree_id}-{kind[:1]}-{uuid.uuid4().hex[:8]}",
        "kind": kind,
        "title": str(title)[:200],
        "parent_id": parent_id,
        "prd_ref": prd_ref,
        "change_type": change_type if change_type in CHANGE_TYPES else "",
        "expected_files": list(expected_files or []),
        "depends_on": list(depends_on or []),
        "scope": str(scope)[:500],
        "business_rule": "",
        "data_entities": [],
        "verify_hint": "",
    }
    return node


# ------------------------------------------------------------------ 确定性模板 (S1-7 行为不变)


def _template_decompose(prd: dict[str, Any]) -> dict[str, Any]:
    """确定性多级模板: Project → 功能/交付域 → 叶 (每功能条款一叶)。

    空功能条款 → 从 goal 兜底 ≥1 叶 (诚实, 不产空树)。S1-7: 模板路径行为不变。
    """
    tree_id = uuid.uuid4().hex[:6]
    content = prd.get("content", {}) or {}
    if not isinstance(content, dict):
        content = {}
    overview = content.get("overview", {}) or {}
    goal = str(overview.get("problem") or overview.get("name")
               or prd.get("goal") or "构建目标产品")[:120]
    title = str(overview.get("name") or goal)[:120]

    nodes: list[dict[str, Any]] = []
    leaves: list[str] = []

    project = _new_node(tree_id, kind="project", title=title or goal,
                        prd_ref=prd.get("id", ""), scope="project")
    nodes.append(project)

    feats = content.get("functional_requirements", []) or []
    if feats:
        fdom = _new_node(tree_id, kind="domain", title="功能实现",
                         parent_id=project["id"], prd_ref=prd.get("id", ""),
                         scope="functional")
        nodes.append(fdom)
        for i, raw in enumerate(feats):
            text = re.sub(r"^实现功能:\s*", "", str(raw)).strip() or f"功能 {i + 1}"
            leaf = _new_node(tree_id, kind="task", title=f"实现功能: {text}",
                             parent_id=fdom["id"], prd_ref=prd.get("id", ""),
                             change_type="NEW_FILE", expected_files=[],
                             depends_on=[], scope="feature")
            nodes.append(leaf)
            leaves.append(leaf["id"])
    else:
        fdom = _new_node(tree_id, kind="domain", title="交付",
                         parent_id=project["id"], prd_ref=prd.get("id", ""),
                         scope="delivery")
        nodes.append(fdom)
        leaf = _new_node(tree_id, kind="task", title=f"实现: {goal}",
                         parent_id=fdom["id"], prd_ref=prd.get("id", ""),
                         change_type="NEW_FILE", expected_files=[], scope="goal-fallback")
        nodes.append(leaf)
        leaves.append(leaf["id"])

    # 验证交付域 (depends_on 全部功能叶)
    vdom = _new_node(tree_id, kind="domain", title="验证与交付",
                     parent_id=project["id"], prd_ref=prd.get("id", ""), scope="verify")
    nodes.append(vdom)
    vleaf = _new_node(tree_id, kind="task", title="验证与交付",
                      parent_id=vdom["id"], prd_ref=prd.get("id", ""),
                      change_type="MODIFY", expected_files=[], depends_on=list(leaves),
                      scope="verify")
    nodes.append(vleaf)
    leaves.append(vleaf["id"])

    edges = [{"from": n["parent_id"], "to": n["id"]} for n in nodes
             if n.get("parent_id")]
    return {
        "plan_id": prd.get("plan_id", ""), "prd_id": prd.get("id", ""),
        "goal": goal, "tree_id": tree_id, "nodes": nodes, "leaves": leaves,
        "edges": edges,
        "critical_path": [n["id"] for n in nodes if n["kind"] == "task"],
        "parallel_groups": [], "degraded": False, "decomposer": "template",
        "created_at": _now_iso(),
    }


# ------------------------------------------------------------------ S1-7: 递归 LLM 提示词

_RECURSIVE_PROMPT = """你是 AI Factory OS 的任务分解器。把产品**递归**拆成多级任务树，深度由复杂度决定，直到每个叶都是"原子任务"。

# 递归规则
- 每个节点 = 一个内聚业务切片 (scope 写清业务规则)。判断 atomic：
  · atomic=false → 必须给 subtasks 继续拆 (给出业务切分理由 scope)
  · atomic=true → 收为叶。叶必须满足：
      (1) 单 Agent 可完成
      (2) 单文件或极小文件集 (expected_files ≤3)
      (3) 有明确可验证方式 (verify_hint: 命令或测试)
      (4) 描述含: 做什么(业务行为 business_rule) + 动什么数据(data_entities: entity+read/write/migrate) + 怎么验(verify_hint)

# 两条不可撕裂的正交维度
A. 业务逻辑内聚: 一个业务能力/规则/状态机 = 完整链路, 必须收在同一子树。例: 下单→支付→订单状态流转 必须同属"订单"子树, 禁止拆到无关分支。
B. 数据所有权: 每个数据实体有唯一 owner 子树 (创建→读→改→删→迁移→UI 绑定收同子树)。叶声明 data_entities+ops; 写同一实体/文件的叶之间必须串行 (天然按树序, 你无需声明 depends_on, 校验器会自动加)。

# 输出 JSON (递归同构, 只输出 JSON)
{"name":"顶层切片","scope":"...","atomic":false,
 "subtasks":[{"name":"...","scope":"业务切片","atomic":false,
   "subtasks":[{"name":"叶任务","atomic":true,"atomic_reason":"单文件可验证",
     "business_rule":"做什么业务行为","data_entities":[{"entity":"实体/表/文件","ops":["write"]}],
     "change_type":"NEW_FILE|MODIFY","expected_files":["..."],"verify_hint":"如何验证"}]}]}

禁止: 不输出 JSON 以外文本; atomic=false 的节点不给 subtasks; 撕裂业务链路; 两叶并行写同一文件。"""


def _build_recursive_prompt(prd: dict[str, Any]) -> str:
    content = prd.get("content", {}) or {}
    overview = content.get("overview", {}) if isinstance(content, dict) else {}
    goal = str(overview.get("problem") or prd.get("goal") or "")[:300]
    feats = (content.get("functional_requirements", [])
             if isinstance(content, dict) else []) or []
    return (
        _RECURSIVE_PROMPT
        + f"\n\n产品: {goal}\n功能需求: {feats}\n"
    )


# ------------------------------------------------------------------ S1-7: 递归解析 + 校验器


def _kind_for_depth(depth: int) -> str:
    """按深度取 kind (0=project, 1..n-1=中间层, 叶=task)。"""
    if depth == 0:
        return "project"
    if depth >= len(NODE_KINDS) - 1:
        return "capability"  # 4+ 层中间节点
    return NODE_KINDS[depth]


def _normalize_entities(raw: Any) -> list[dict[str, Any]]:
    """data_entities 规范化: [{entity, ops:[read|write|migrate]}]。"""
    if not isinstance(raw, list):
        return []
    out = []
    for e in raw:
        if not isinstance(e, dict):
            continue
        ops = [str(o) for o in (e.get("ops") or [])]
        ops = [o for o in ops if o in ("read", "write", "migrate")]
        if e.get("entity"):
            out.append({"entity": str(e["entity"])[:120], "ops": ops or ["write"]})
    return out


def _serialize_file_deps(nodes: list[dict[str, Any]],
                         leaves: list[str]) -> tuple[list[dict[str, Any]], bool]:
    """校验器 (数据所有权): 跨叶同文件写 → 串行 depends_on; 成环 → 拒绝 (degraded)。

    规则: 叶 A 与叶 B 声明写同一 expected_file:
      · 同子树 (祖先后代) 已天然串行 (树序) → 不加
      · 否则按树序: 前序叶 depends_on 后序叶? 不 — 写冲突应"后写依赖先写完成":
        后出现的叶 depends_on 先出现的叶 (串行化, 防并行写冲突)
    若注入的 depends_on 与该串行边成环 → 该叶标 degraded (拒绝分支, 不静默放行)。
    """
    file_owner: dict[str, str] = {}   # file -> 首个写它的叶
    degraded = False
    for leaf_id in leaves:
        node = next(n for n in nodes if n["id"] == leaf_id)
        for f in node.get("expected_files", []):
            f = str(f)
            if f in file_owner and file_owner[f] != leaf_id:
                prev = file_owner[f]
                # 后写叶 depends_on 先写叶 (串行)
                if prev not in node["depends_on"]:
                    node["depends_on"] = list(node["depends_on"]) + [prev]
                # 成环检测: 若 prev 已依赖 leaf (直接或传递) → 环
                if _would_cycle(nodes, prev, leaf_id):
                    degraded = True
                    node["depends_on"] = [d for d in node["depends_on"] if d != prev]
                    node["_rejected_cycle"] = f"write-conflict-cycle:{f}"
            else:
                file_owner[f] = leaf_id
    return nodes, degraded


def _would_cycle(nodes: list[dict[str, Any]], start: str,
                 target: str) -> bool:
    """start 是否传递依赖 target (加 target→start 边会成环)?"""
    by_id = {n["id"]: n for n in nodes}
    stack = list(by_id.get(start, {}).get("depends_on", []))
    seen = set()
    while stack:
        cur = stack.pop()
        if cur == target:
            return True
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(by_id.get(cur, {}).get("depends_on", []))
    return False


def _parse_llm_tree_recursive(raw: str | None,
                              prd: dict[str, Any]) -> dict[str, Any] | None:
    """解析 LLM 递归 JSON → 多级树 (深度优先, kind 按深度); 非法 → None。"""
    if not raw:
        return None
    try:
        m = re.search(r"\{", raw, re.S)
        if not m:
            return None
        # 括号配平提取 (LLM 偶发 JSON 后夹带解释 → 只取首个配平对象, 非贪婪到末尾)
        start = m.start()
        depth = 0
        in_str = False
        esc = False
        end = len(raw)
        for i in range(start, len(raw)):
            ch = raw[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if depth != 0:
            # LLM 输出截断 (未配平) → 尝试解析最大配平前缀 (部分树 + degraded)
            data = _try_partial_json(raw[start:end])
            if data is None:
                return None
            truncated = True
        else:
            data = json.loads(raw[start:end])
            truncated = False
        # 兼容旧平铺格式 (S1-2: {domains:[{title,tasks:[...]}]}) → 递归同构
        if "root" not in data and isinstance(data.get("domains"), list):
            data = {"root": {
                "name": str((data.get("name"))
                            or "构建目标产品"),
                "atomic": False,
                "subtasks": [
                    {"name": str(d.get("title") or "域"), "atomic": False,
                     "subtasks": [
                         dict(t) for t in (d.get("tasks") or [])
                     ]}
                    for d in data["domains"]
                ],
            }}
        tree_id = uuid.uuid4().hex[:6]
        content = prd.get("content", {}) or {}
        overview = content.get("overview", {}) if isinstance(content, dict) else {}
        goal = str(overview.get("problem") or prd.get("goal")
                   or "构建目标产品")[:120]
        nodes: list[dict[str, Any]] = []
        leaves: list[str] = []
        warnings: list[str] = []
        degraded = False
        counter = {"n": 0}

        def _walk(node_spec: dict[str, Any], parent_id: str,
                  depth: int) -> str | None:
            """返回节点 id; 超限/非法 → None (截断)。"""
            if counter["n"] >= MAX_NODES:
                warnings.append(f"MAX_NODES={MAX_NODES} 超限截断")
                return None
            if depth > MAX_DEPTH:
                # 超深 → 强制收叶 + 记录 (调用方见 warnings + degraded 诚实)
                warnings.append(f"MAX_DEPTH={MAX_DEPTH} 超深强制收叶: "
                                f"{str(node_spec.get('name') or '')[:40]}")
                kind = "task"
                title = str(node_spec.get("name") or "任务")[:200]
                leaf = _new_node(tree_id, kind=kind, title=title,
                                 parent_id=parent_id, prd_ref=prd.get("id", ""),
                                 change_type=_norm_ct(node_spec.get("change_type")),
                                 expected_files=[str(x) for x in
                                                 (node_spec.get("expected_files") or [])][:3],
                                 scope=str(node_spec.get("scope")
                                           or node_spec.get("business_rule") or "")[:500])
                leaf["business_rule"] = str(node_spec.get("business_rule") or "")[:500]
                leaf["data_entities"] = _normalize_entities(
                    node_spec.get("data_entities"))
                leaf["verify_hint"] = str(node_spec.get("verify_hint") or "")[:200]
                nodes.append(leaf)
                leaves.append(leaf["id"])
                counter["n"] += 1
                return leaf["id"]

            atomic = bool(node_spec.get("atomic"))
            subtasks = node_spec.get("subtasks")
            # 兼容: 无 atomic/subtasks 的 task-like dict (含 title/change_type) → 视为叶
            looks_like_flat_task = (
                "atomic" not in node_spec
                and "subtasks" not in node_spec
                and (node_spec.get("title") or node_spec.get("change_type"))
            )
            if looks_like_flat_task:
                atomic = True
            kind = _kind_for_depth(depth) if not atomic else "task"
            title = str(node_spec.get("name") or node_spec.get("title")
                        or "节点")[:200]
            node = _new_node(tree_id, kind=kind, title=title,
                             parent_id=parent_id, prd_ref=prd.get("id", ""),
                             scope=str(node_spec.get("scope")
                                       or node_spec.get("business_rule") or "")[:500])
            if atomic:
                # 叶: 带业务/数据/验证
                node["business_rule"] = str(node_spec.get("business_rule") or "")[:500]
                node["data_entities"] = _normalize_entities(
                    node_spec.get("data_entities"))
                node["verify_hint"] = str(node_spec.get("verify_hint") or "")[:200]
                node["change_type"] = _norm_ct(node_spec.get("change_type"))
                node["expected_files"] = [
                    str(x) for x in (node_spec.get("expected_files") or [])][:3]
            nodes.append(node)
            counter["n"] += 1

            if atomic:
                leaves.append(node["id"])
                return node["id"]

            if not isinstance(subtasks, list) or not subtasks:
                # atomic=false 但无 subtasks → 强制收叶 + warning (不静默)
                node["kind"] = "task"
                node["business_rule"] = str(node_spec.get("business_rule")
                                            or "")[:500]
                node["data_entities"] = _normalize_entities(
                    node_spec.get("data_entities"))
                node["verify_hint"] = str(node_spec.get("verify_hint")
                                          or "由实现者定义验证")[:200]
                node["change_type"] = _norm_ct(node_spec.get("change_type"))
                node["expected_files"] = [
                    str(x) for x in (node_spec.get("expected_files") or [])][:3]
                warnings.append(f"atomic=false 无 subtasks → 强制收叶: {title[:40]}")
                leaves.append(node["id"])
                return node["id"]

            for st in subtasks:
                _walk(st, node["id"], depth + 1)
            return node["id"]

        root = data.get("root") or data
        _walk(root if isinstance(root, dict) else {}, "", 0)

        if not leaves:
            return None  # 无叶 → 非法 (兜底模板)

        # LLM 输出截断 → 部分树 + degraded 诚实
        if truncated:
            warnings.append("LLM 输出截断 → 部分解析 (树可能不完整)")
        # 校验器: 数据所有权串行化 + 成环
        nodes, file_degraded = _serialize_file_deps(nodes, leaves)
        degraded = bool(degraded or file_degraded or warnings or truncated)  # 超限/超深/冲突 → 诚实

        edges = [{"from": n["parent_id"], "to": n["id"]} for n in nodes
                 if n.get("parent_id")]
        return {
            "plan_id": prd.get("plan_id", ""), "prd_id": prd.get("id", ""),
            "goal": goal, "tree_id": tree_id, "nodes": nodes, "leaves": leaves,
            "edges": edges,
            "critical_path": [n["id"] for n in nodes if n["kind"] == "task"],
            "parallel_groups": [], "degraded": degraded,
            "warnings": warnings, "created_at": _now_iso(),
        }
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def _norm_ct(raw: Any) -> str:
    s = str(raw or "NEW_FILE")
    return s if s in CHANGE_TYPES else "NEW_FILE"


def _try_partial_json(seg: str) -> dict[str, Any] | None:
    """截断 JSON 的部分解析: 从闭合边界截断 + 补闭合括号 (试错)。

    从每个 '}' 或 ']' 处截断 (保证是完整结构边界), 补闭合剩余括号,
    第一个 json.loads 成功的前缀即最大可恢复部分树。
    """
    # 从末尾找闭合边界 (保证数组/对象已配平处)
    boundaries = [i for i in range(len(seg) - 1, -1, -1)
                  if seg[i] in "}]"]
    for b in boundaries:
        prefix = seg[:b + 1]
        # 计算 prefix 内未闭合括号 (配平)
        stack: list[str] = []
        in_str = False
        esc = False
        for ch in prefix:
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch in "[{":
                stack.append(ch)
            elif ch in "]}":
                if stack:
                    stack.pop()
        if in_str:
            continue  # 尾部在字符串内 → 跳过该边界
        cand = prefix
        for op in reversed(stack):
            cand += "]" if op == "[" else "}"
        try:
            d = json.loads(cand)
            if isinstance(d, dict) and d:
                return d
        except (json.JSONDecodeError, ValueError):
            continue
    return None


# ------------------------------------------------------------------ LLM 注入


def build_llm_decomposer(
    llm_fn: Callable[[str], str | None] | None = None,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """LLM decomposer 工厂: 注入 console_sessions.llm_raw (或测试 llm_fn)。

    失败/非法 → 模板兜底 + degraded=True (诚实降级, 不伪造 LLM 结果)。
    S1-7: 提示词递归同构 + 递归解析 + 业务/数据校验器。
    """
    if llm_fn is None:
        from factory_console.console_sessions import llm_raw as _raw
        llm_fn = _raw

    def _decompose(prd: dict[str, Any]) -> dict[str, Any]:
        prompt = _build_recursive_prompt(prd)
        raw = None
        try:
            raw = llm_fn(prompt)
        except Exception:  # noqa: BLE001
            raw = None
        tree = _parse_llm_tree_recursive(raw, prd)
        if tree is None:
            base = _template_decompose(prd)
            base["degraded"] = True
            base["decomposer"] = "template-after-llm-failure"
            return base
        tree["decomposer"] = "llm"
        tree["degraded"] = bool(tree.get("degraded"))
        return tree

    return _decompose


# 兼容: 旧平铺解析名 (模板路径用)
_parse_llm_tree = _parse_llm_tree_recursive


# ------------------------------------------------------------------ decompose_prd (公开入口)


def decompose_prd(
    prd: dict[str, Any],
    *,
    interpreter: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """PRD → 多级树。interpreter 注入 (LLM) → 模板兜底 (degraded 诚实)。"""
    if interpreter is not None:
        try:
            tree = interpreter(prd)
            if tree and isinstance(tree, dict) and tree.get("nodes"):
                return tree
        except Exception:  # noqa: BLE001 — 任何失败 → 模板兜底
            pass
    tree = _template_decompose(prd)
    tree["degraded"] = bool(interpreter is not None)
    return tree


# ------------------------------------------------------------------ 查询/导出


def tree_leaves(tree: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(n) for n in (tree.get("nodes") or []) if n.get("kind") == "task"]


def _max_depth(nodes: list[dict[str, Any]]) -> int:
    """S1-7: 动态算树深 (遍历 parent 链)。"""
    if not nodes:
        return 0
    by_id = {n["id"]: n for n in nodes}
    depth = 0

    def _d(nid: str) -> int:
        node = by_id.get(nid)
        if not node or not node.get("parent_id"):
            return 1
        return 1 + _d(node["parent_id"])

    for n in nodes:
        depth = max(depth, _d(n["id"]))
    return depth


def tree_summary(tree: dict[str, Any] | None) -> dict[str, Any]:
    if tree is None:
        return {"exists": False}
    leaves = tree_leaves(tree)
    return {
        "exists": True,
        "plan_id": tree.get("plan_id", ""),
        "goal": tree.get("goal", ""),
        "depth": _max_depth(tree.get("nodes", [])),
        "node_count": len(tree.get("nodes", [])),
        "leaf_count": len(leaves),
        "domains": sorted({str(n.get("title"))[:60] for n in tree.get("nodes", [])
                           if n.get("kind") in ("domain", "module", "capability")}),
        "leaves": [
            {"id": n["id"], "title": n["title"], "change_type": n.get("change_type", ""),
             "expected_files": n.get("expected_files", []),
             "depends_on": n.get("depends_on", []),
             "business_rule": n.get("business_rule", ""),
             "data_entities": n.get("data_entities", []),
             "verify_hint": n.get("verify_hint", "")}
            for n in leaves
        ],
        "critical_path": tree.get("critical_path", []),
        "parallel_groups": tree.get("parallel_groups", []),
        "degraded": bool(tree.get("degraded")),
        "decomposer": tree.get("decomposer", ""),
        "warnings": tree.get("warnings", []),
    }


def tree_to_plan(tree: dict[str, Any]) -> tuple[list[dict[str, Any]],
                                                list[str]]:
    """叶摘要 (供 PLAN.tasks) + 拓扑序 (order, 依赖先)。

    拓扑: DFS post-order (depends_on 先于依赖者)。
    """
    leaves = tree_leaves(tree)
    by_id = {n["id"]: n for n in leaves}
    visited: set[str] = set()
    order: list[str] = []

    def _visit(node_id: str) -> None:
        if node_id in visited:
            return
        visited.add(node_id)
        node = by_id.get(node_id)
        for dep in (node or {}).get("depends_on", []):
            if dep in by_id:
                _visit(dep)
        order.append(node_id)

    for n in leaves:
        _visit(n["id"])

    summaries = []
    for lid in order:
        n = by_id[lid]
        summaries.append({
            "id": lid,
            "title": n["title"],
            "kind": n["kind"],
            "change_type": n.get("change_type", ""),
            "expected_files": n.get("expected_files", []),
            "depends_on": n.get("depends_on", []),
            "prd_ref": n.get("prd_ref", ""),
            "business_rule": n.get("business_rule", ""),
            "data_entities": n.get("data_entities", []),
            "verify_hint": n.get("verify_hint", ""),
        })
    return summaries, order


__all__ = [
    "NODE_KINDS", "CHANGE_TYPES",
    "save_task_tree", "load_task_tree",
    "build_llm_decomposer", "decompose_prd",
    "tree_leaves", "tree_summary", "tree_to_plan",
]
