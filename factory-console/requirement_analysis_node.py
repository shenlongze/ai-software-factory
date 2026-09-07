"""Requirement Analysis Node — executor (Node Loop 试点)。

NodeRun 输入: project_id + requirement 上下文 (canonical REQ 或会话描述)。
Loop: LLM 逐维度分析 → findings (结构) → 需决策 → request_decision (WAIT)
     → 用户答复 → resume → 收敛 verify → COMPLETED → REQ truth 写。

本 executor 为 execute_node_run executor_fn 契约:
    execute(input) → {ok, output, error, verification, ...}
在每次 attempt 内完成"一个分析回合": 读 checkpoint → 下一维度 →
产出 findings → 若发现决策点: 注册 decision (由外层转 WAITING) →
否则更新 checkpoint → 返回回合结果 (未收敛 → INCONCLUSIVE)。
"""
from __future__ import annotations

import json
from typing import Any

#: 分析维度清单 (产品需求完整性; 以项目真实场景为准 — 飞机大战/Web 通用)
ANALYSIS_DIMENSIONS = [
    "范围与目标",        # 产品定位/MVP 边界
    "功能与流程",        # 核心玩法/页面流/状态
    "交互与操作",        # 输入方式/反馈/灵敏度
    "边界与异常",        # 空态/失败/边界值
    "非功能",            # 浏览器/分辨率/性能/存储
    "体验与内容",        # 音效/视觉/文案
    "验收与依赖",        # 验收标准/约束/依赖
]

FINDING_TYPES = ("gap", "ambiguity", "contradiction", "missing_constraint", "suggestion")
FINDING_STATUS = ("open", "resolved", "accepted")

ANALYSIS_PROMPT = """你是需求分析节点。当前项目: {project}
原始输入: {input_snippet}
已有事实 (REQ/会话上下文): {truth_snippet}
已完成维度: {completed}
未决 open_questions: {open_questions}
已确认决策: {decisions}

本轮任务: 分析维度「{dimension}」(尚未覆盖)。
对维度逐项审查当前已知需求, 找出:
- gap: 该维度下缺失但关键的内容
- ambiguity: 表述歧义需澄清 (如"或"字/主观词)
- contradiction: 与已有内容冲突
- missing_constraint: 缺关键约束
- suggestion: 建议 (默认值/体验改进 — 非用户确认不可入 Truth)

输出 JSON (仅 JSON):
{{"findings": [{{"dimension": "...", "type": "...", "severity": high|medium|low,
   "question": "面向用户的具体问题(如有)", "detail": "说明",
   "needs_decision": true|false,
   "decision_options": ["..."], "recommendation": "..."}}],
  "summary": "本维度一句话结论",
  "next_dimension_ready": true|false}}
规则: ① 用户未说的具体数值/机制只能作 suggestion/open_question, 绝不写成已确定;
② 需要用户拍板的决策点 → needs_decision=true (options+推荐);
③ 无新发现 → findings=[] (维度已覆盖); ④ 只输出 JSON。"""


def build_analysis_context(run: dict[str, Any], *, truth_snippet: str = "") -> dict[str, Any]:
    cp = run.get("checkpoint") or {}
    return {
        "project": str((run.get("input") or {}).get("project_id") or ""),
        "input_snippet": str((run.get("input") or {}).get("request") or "")[:1500],
        "truth_snippet": truth_snippet[:2000],
        "completed": cp.get("completed_dimensions") or [],
        "open_questions": cp.get("open_questions") or [],
        "decisions": [d for d in (run.get("decisions") or []) if d.get("status") == "RESOLVED"],
    }


def next_dimension(cp: dict[str, Any]) -> str | None:
    done = set(cp.get("completed_dimensions") or [])
    return next((d for d in ANALYSIS_DIMENSIONS if d not in done), None)


def parse_findings(text: str) -> dict[str, Any]:
    """executor LLM 输出 → 结构化 findings (容忍代码块/尾注)。"""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1]
        t = t.rsplit("```", 1)[0]
    s = t.find("{")
    e = t.rfind("}")
    if s >= 0 and e > s:
        t = t[s:e + 1]
    try:
        return json.loads(t)
    except Exception:  # noqa: BLE001
        return {"findings": [], "summary": str(text)[:500],
                "next_dimension_ready": False}


# ------------------------------------------------------------------ Round executor (结构化分析回合)

def run_round(root, run_id: str, llm_fn, *, truth_snippet: str = "") -> dict[str, Any]:
    """执行一个分析回合: 下一维度 → LLM 分析 → findings 处理。

    返回 {state, need_user(bool), pending_questions[], summary, ...}
    - need_user: 有决策点 → request_decision (WAIT) — 由调用方呈现给用户
    - 无决策点 → checkpoint 推进; 全维度收敛 → 自动 VERIFYING→COMPLETED
    """
    from factory_console import node_runtime as nr
    run = nr.get_node_run(root, run_id)
    if run is None:
        raise nr.NodeError(f"NodeRun 不存在: {run_id}")
    if run.get("state") not in ("RUNNING", "PENDING"):
        raise nr.NodeError(f"状态 {run.get('state')} 不能执行回合")
    if run.get("state") == "PENDING":
        nr.transition_node_run(root, run_id, "RUNNING")
    cp = dict(run.get("checkpoint") or {})
    cp.setdefault("iteration", 0)
    cp.setdefault("completed_dimensions", [])
    cp.setdefault("open_questions", [])
    cp.setdefault("resolved_questions", [])
    dim = next_dimension(cp)
    if dim is None:
        # 全维度覆盖 → 收敛检查: open_questions 未清? (由外层处理) — 全清→COMPLETED
        nr.update_checkpoint(root, run_id, patch=cp)
        return {"state": run.get("state"), "all_dimensions_done": True,
                "summary": "所有维度已覆盖"}
    ctx = build_analysis_context(run, truth_snippet=truth_snippet)
    prompt = ANALYSIS_PROMPT.format(
        project=ctx["project"], input_snippet=ctx["input_snippet"],
        truth_snippet=ctx["truth_snippet"], completed="、".join(ctx["completed"]) or "(无)",
        open_questions="; ".join(ctx["open_questions"]) or "(无)",
        decisions="; ".join(f"{d.get('question')}→{d.get('chosen')}"
                            for d in ctx["decisions"]) or "(无)",
        dimension=dim)
    raw = llm_fn(prompt)
    parsed = parse_findings(raw)
    findings = [f for f in parsed.get("findings", [])
                if isinstance(f, dict) and f.get("type") in FINDING_TYPES]
    cp["completed_dimensions"] = list(dict.fromkeys(cp["completed_dimensions"] + [dim]))
    cp["iteration"] = int(cp.get("iteration") or 0) + 1
    cp["findings"] = cp.get("findings") or []
    need_user = False
    pending = []
    # Phase 2.1-FIX: 先持久化维度进度 (checkpoint 先落盘 — 异常/WAIT 不丢)
    for f in findings:
        f["id"] = f"f-{abs(hash(str(f)) ) % 10**8:08d}"
        f["status"] = "open"
        cp["findings"].append(f)
        if f.get("type") in ("ambiguity", "contradiction", "missing_constraint"):
            q = str(f.get("question") or "").strip()
            if q and q not in cp["open_questions"]:
                cp["open_questions"].append(q)
    nr.update_checkpoint(root, run_id, patch=cp)
    # 决策: 每回合至多注册一个 (首个 needs_decision) — WAIT 后由下回合继续
    for f in findings:
        if f.get("needs_decision"):
            d = nr.request_decision(
                root, run_id, question=str(f.get("question") or f.get("detail") or "决策点"),
                options=f.get("decision_options") or [], finding_refs=[f.get("id")])
            pending.append({"decision_id": d["decision_id"],
                            "question": d["question"], "options": d["options"]})
            need_user = True
            f["decision_ref"] = d["decision_id"]
            break
    if need_user:
        return {"state": "WAITING_FOR_USER", "need_user": True,
                "pending_questions": pending,
                "summary": parsed.get("summary") or f"{dim} 分析发现需用户决策",
                "dimension": dim, "findings_count": len(findings)}
    return {"state": "RUNNING", "need_user": False,
            "summary": parsed.get("summary") or f"{dim} 分析完成",
            "dimension": dim, "findings_count": len(findings),
            "open_questions": cp["open_questions"]}


def finalize_if_done(root, run_id: str) -> dict[str, Any] | None:
    """收敛判定: 全维度覆盖 + 无 open_questions → VERIFYING→COMPLETED。"""
    from factory_console import node_runtime as nr
    run = nr.get_node_run(root, run_id)
    if run is None or run.get("state") not in ("RUNNING",):
        return None
    cp = run.get("checkpoint") or {}
    if (set(cp.get("completed_dimensions") or []) >= set(ANALYSIS_DIMENSIONS)
            and not (cp.get("open_questions") or [])):
        nr.transition_node_run(root, run_id, "VERIFYING", actor="analysis", note="converged")
        nr.transition_node_run(root, run_id, "COMPLETED", actor="analysis", note="requirement analysis complete")
        return nr.get_node_run(root, run_id)
    return None
