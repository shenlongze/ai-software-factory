"""factory-console/external_executor/router.py — M5 路由层 (设计文档 §9)。

Founder 2026-08-27: "专业的人做专业的事, 成本最优, 效果最佳" → 路由决策:
① 任务分类: 任务文本 → 工作类型 (write-code/review/test/product/security/ux/docs/arch…)
② 能力匹配: 候选 agent/skill 的 role/capabilities 匹配工作类型
③ 历史加权: score = w1*首次通过 + w2*验证通过 − w3*成本 − w4*耗时 (默认 4/3/2/1, 可配置)
④ 成本分级: 任务难度 → cost_tier 匹配 (简单任务不派 high tier)
⑤ 用户显式: 用户指定 agent → 直接采用 (仍 probe)
⑥ 兜底: 无匹配 → 系统默认 + 诚实标注「未匹配专业能力, 已降级」

反馈学习: 委派 → 验证/回修回写 EXS → 路由下次读 EXS 效果分自动更新。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .schema import ExternalExecutorAdapter

#: 默认路由权重 (Founder 确认: 4/3/2/1)
DEFAULT_WEIGHTS = {"first_pass": 4.0, "verify_pass": 3.0, "cost": 2.0, "duration": 1.0}

#: 任务关键词 → 工作类型 (顺序即优先级)
_WORK_TYPE_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("arch", ("架构", "architecture", "系统设计", "重构架构")),
    ("security", ("安全", "security", "渗透", "隐私", "权限", "漏洞")),
    ("review", ("审查", "review", "检查", "评审", "审计", "质量把关", "复盘")),
    ("design", ("设计", "ux", "界面", "原型", "样式", "交互", "视觉")),
    ("test", ("测试", "test", "单测", "回归", "用例", "冒烟")),
    ("product", ("产品", "需求", "prd", "策略", "方向", "方案", "商业模式")),
    ("writer", ("文档", "readme", "说明", "教程", "文档撰写")),
    ("backend", ("后端", "api", "接口", "服务端", "数据库")),
    ("frontend", ("前端", "页面", "react", "vue", "ui")),
    ("developer", ("开发", "实现", "写", "修复", "重构", "功能", "优化", "完善", "bug", "修")),
]

#: 工作类型 → 候选角色 (能力匹配; 多个角色按顺序)
_ROLE_BY_WORK: dict[str, tuple[str, ...]] = {
    "arch": ("architect",),
    "security": ("security",),
    "review": ("reviewer", "architect"),
    "design": ("designer", "frontend"),
    "test": ("tester", "qa"),
    "product": ("product", "researcher"),
    "writer": ("writer",),
    "backend": ("backend", "developer"),
    "frontend": ("frontend", "developer"),
    "developer": ("developer", "backend", "frontend"),
}


def classify_task(task: str) -> str:
    """任务文本 → 工作类型 (未命中 → 'developer' 兜底, 诚实标注降级)。"""
    low = str(task or "").lower()
    for work, keys in _WORK_TYPE_RULES:
        for k in keys:
            if k in low:
                return work
    return "developer"


def _load_records(data_dir: str | Path) -> list[dict[str, Any]]:
    try:
        d = json.loads((Path(data_dir) / "exec" / "execution_records.json").read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except Exception:  # noqa: BLE001
        return []


def _history_stats(data_dir: str | Path, candidate_key: str) -> dict[str, float | int | None]:
    """候选 (executor 或 executor.host_agent) 的历史 EXS 效果分。"""
    rs = [r for r in _load_records(data_dir) if str(r.get("agent") or "") == candidate_key]
    if not rs:
        return {"runs": 0, "first_pass_rate": None, "verify_pass_rate": None,
                "avg_cost": None, "avg_duration": None}
    first_known = [r for r in rs if r.get("first_pass") is not None]
    first_pass = sum(1 for r in first_known if r.get("first_pass") is True)
    verified = [r for r in rs if (r.get("verify") or {}).get("result") in ("pass", "fail")]
    verify_pass = sum(1 for r in verified if (r.get("verify") or {}).get("result") == "pass")
    costs = [float(r["cost_usd"]) for r in rs if r.get("cost_usd") is not None]
    durations = [int(r.get("duration_ms") or 0) for r in rs if r.get("duration_ms")]
    return {
        "runs": len(rs),
        "first_pass_rate": round(first_pass / len(first_known), 3) if first_known else None,
        "verify_pass_rate": round(verify_pass / len(verified), 3) if verified else None,
        "avg_cost": round(sum(costs) / len(costs), 4) if costs else None,
        "avg_duration": int(sum(durations) / len(durations)) if durations else None,
    }


def score_candidate(
    candidate: dict[str, Any],
    work_type: str,
    data_dir: str | Path,
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """单个候选评分: 历史加权 (4/3/2/1)。无历史 → 能力匹配分 (诚实标注)。"""
    w = weights or DEFAULT_WEIGHTS
    key = str(candidate.get("key") or "")
    role = str(candidate.get("role") or "")
    cost_tier = str(candidate.get("cost_tier") or "medium")
    # 能力匹配 (硬门槛): 角色命中工作类型 → 1.0; 否则 0.0 (不参与路由, 防历史分压过专业匹配)
    want_roles = _ROLE_BY_WORK.get(work_type, ())
    cap_hit = 1.0 if (want_roles and role in want_roles) else 0.0
    kind = str(candidate.get("kind") or "agent")
    kind_priority = {"agent": 0, "executor": 1, "internal": 2}.get(kind, 1)
    hs = _history_stats(data_dir, key)
    if hs["runs"] > 0:
        fp = hs["first_pass_rate"] if hs["first_pass_rate"] is not None else 0.5
        vp = hs["verify_pass_rate"] if hs["verify_pass_rate"] is not None else 0.5
        cost_norm = min(1.0, (hs["avg_cost"] or 0.0) / 1.0)      # $1 封顶归一
        dur_norm = min(1.0, (hs["avg_duration"] or 0) / 600000)  # 10 分钟封顶归一
        score = (cap_hit * (w["first_pass"] * fp + w["verify_pass"] * vp)
                 - w["cost"] * cost_norm - w["duration"] * dur_norm)
        return {"key": key, "role": role, "cost_tier": cost_tier, "work_type": work_type,
                "score": round(score, 4), "capability_hit": cap_hit, "history": hs,
                "kind": kind, "kind_priority": kind_priority,
                "basis": "history+capability"}
    return {"key": key, "role": role, "cost_tier": cost_tier, "work_type": work_type,
            "score": round(cap_hit, 4), "capability_hit": cap_hit, "history": hs,
            "kind": kind, "kind_priority": kind_priority,
            "basis": "capability-only (无历史, 诚实)"}


_ROLE_NORM: dict[str, str] = {
    # 英文
    "tester": "tester", "qa": "tester", "test": "tester",
    "backend": "backend", "backend-developer": "backend",
    "frontend": "frontend", "frontend-developer": "frontend",
    "developer": "developer", "engineer": "developer",
    "architect": "architect", "architecture": "architect",
    "security": "security", "security-examiner": "security",
    "product": "product", "product-manager": "product", "pm": "product",
    "designer": "designer", "ux": "designer",
    "writer": "writer", "reviewer": "reviewer",
    # 中文
    "测试工程师": "tester", "测试": "tester", "质量": "qa",
    "后端开发": "backend", "后端": "backend",
    "前端开发": "frontend", "前端": "frontend",
    "开发工程师": "developer", "开发": "developer",
    "架构师": "architect", "架构": "architect",
    "安全": "security",
    "产品经理": "product", "产品": "product",
    "设计师": "designer", "设计": "designer",
}


def normalize_role(role: str) -> str:
    """角色归一 (中英文 → 标准 role; 未命中 → 原样)。"""
    r = str(role or "").strip().lower()
    if r in _ROLE_NORM:
        return _ROLE_NORM[r]
    for k, v in _ROLE_NORM.items():
        if k in r:
            return v
    return str(role or "assistant").strip() or "assistant"


def build_candidates(
    adapters: list[ExternalExecutorAdapter],
    agents: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """候选池: 导入的外部 agent (带 source, 角色=推导) + 内部员工 (无 source, 角色=注册 role)
    + 适配器自身 (capabilities.roles)。内部员工兜底 — 外部无专业匹配时仍能选对。"""
    cands: list[dict[str, Any]] = []
    for a in adapters:
        for role in (a.capabilities.roles or []):
            cands.append({"key": a.id, "name": a.name, "role": role, "cost_tier": a.capabilities.cost_tier,
                          "kind": "executor"})
    for ag in agents:
        aid = str(ag.get("id") or "")
        if not aid:
            continue
        source = str(ag.get("source") or "")
        role = normalize_role(str(ag.get("role") or "assistant"))
        cands.append({"key": aid, "name": str(ag.get("name") or aid), "role": role,
                      "cost_tier": str(ag.get("cost_tier") or "medium"),
                      "kind": "agent" if source else "internal",
                      "host": ag.get("host")})
    # 去重 (同 key 保留第一个)
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for c in cands:
        if c["key"] in seen:
            continue
        seen.add(c["key"])
        out.append(c)
    return out


def route(
    task: str,
    adapters: list[ExternalExecutorAdapter],
    imported_agents: list[dict[str, Any]],
    data_dir: str | Path,
    *,
    explicit_agent: str = "",
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """路由决策: 返回 {pick, work_type, reason, alternatives, basis}。

    ⑤ 用户显式优先 (仍 probe 由调用方执行); ② 能力匹配 → ③ 历史加权排序;
    ⑥ 无候选 → 兜底 (诚实标注降级)。"""
    work_type = classify_task(task)
    candidates = build_candidates(adapters, imported_agents)
    if explicit_agent:
        hit = next((c for c in candidates if c["key"] == explicit_agent), None)
        return {
            "pick": explicit_agent,
            "pick_kind": str((hit or {}).get("kind") or "agent"),
            "work_type": work_type,
            "reason": f"用户显式指定 ({hit['role'] if hit else '未在候选池'})",
            "explicit": True, "basis": "user-explicit",
            "alternatives": [c["key"] for c in candidates[:8]],
        }
    if not candidates:
        return {"pick": None, "pick_kind": None, "work_type": work_type,
                "reason": "无候选 (未导入任何外部能力)",
                "explicit": False, "basis": "fallback-no-candidates", "alternatives": []}
    scored = [score_candidate(c, work_type, data_dir, weights) for c in candidates]
    # ② 能力匹配硬门槛: 有命中角色 → 只在命中的候选中选 (专业的人做专业的事)
    matching = [s for s in scored if s["capability_hit"] >= 1.0]
    degraded = False
    pool = matching if matching else scored
    if not matching:
        degraded = True  # ⑥ 兜底: 无专业匹配 → 全候选降级选 (诚实标注)
    pool_sorted = sorted(pool, key=lambda x: (x["score"], -x["kind_priority"]), reverse=True)
    best = pool_sorted[0]
    # ④ 成本分级提示: 简单任务 (developer 兜底) 建议 low/medium, 复杂任务 (arch/security) 建议 medium/high
    tier_advice = "low|medium" if work_type in ("developer", "writer", "design") else "medium|high"
    reason = f"能力匹配({best['role']}) + 历史效果分 {best['score']}"
    if degraded:
        reason += " (未匹配专业能力, 已降级)"
    return {
        "pick": best["key"], "pick_kind": str(best.get("kind") or "agent"),
        "work_type": work_type, "reason": reason,
        "explicit": False, "basis": best["basis"], "degraded": degraded,
        "tier_advice": tier_advice,
        "alternatives": [s["key"] for s in pool_sorted[:8]],
        "detail": pool_sorted[:8],
    }
