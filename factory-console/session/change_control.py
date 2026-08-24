"""factory-console/session/change_control.py — 需求变更回流 ChangeControl (S10-111 M3-6)。

propose → impact → approve → PRD v2 → replan: 执行中 "加导出" → PRD.md 追加
变更记录 v2 + 新任务合并 tasks.json + plan.json (复用 M3a DecomposeEngine 拆解,
动态 DAG 已有)。

设计: docs/sprint10/S10-111-m3-finish-plan.md §2
- ChangeProposal: {id, project_slug, request, reason, status, created_at}
- ImpactAnalysis: {proposal_id, affected_prd_sections, affected_tasks,
  affected_dependencies, note} — 关键词匹配 (确定性, 手算可枚举; 过度波及收敛)
- ChangeController:
  - propose(slug, request): 解析变更内容+理由 (规则优先, llm_fn 可选补充)
  - impact(proposal): 读 PRD.md + tasks.json + plan.json → 波及章节/任务/依赖
  - apply(proposal, approved): y → PRD v2 + changelog + DecomposeEngine 拆变更
    新任务合并 tasks.json + plan.json (+ execution_plan.json 生效);
    n → 不写不建, status=rejected

边界:
- 纯标准库 (json/re/dataclasses/uuid), 零新依赖
- 只动本项目 PRD/tasks/plan (不做执行重放/回滚, 不做并行线程化)
- DecomposeEngine/CriticalPathEngine/TaskScheduler/DecompositionEvaluator 内部
  逐字节不改 (仅构造参数 evaluate_after=False 复用)
- 无 LLM → 确定性解析/拆解真实生效 (不 stub/fake)
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

#: 变更状态
STATUS_PROPOSED = "proposed"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"

#: PRD 变更记录版本标记 (PRD.md 尾部追加, 文件尾标记 v2)
CHANGE_HEADING = "# 变更记录 v2"

#: 变更前缀动作词 (propose 解析: "加导出功能" → request="导出")
_ACTION_VERBS: tuple[str, ...] = (
    "加一个", "加一项", "加个", "新增", "增加", "添加", "加",
    "实现", "支持", "引入", "提供",
)
#: 变更后缀通用名词 (收敛 request: "导出功能" → "导出")
_TRAILING_NOUNS: tuple[str, ...] = ("功能", "模块", "能力", "特性", "机制")

#: 影响分析关键词忽略词 (过度波及收敛 — 纯通用词不参与匹配)
_STOPWORDS: frozenset[str] = frozenset(
    {"功能", "模块", "能力", "系统", "页面", "实现", "支持", "相关", "全部", "核心"}
)

#: 影响分析波及上限 (过度波及收敛 — 手算可枚举, 防全表命中)
MAX_AFFECTED = 5


def _now_iso() -> str:
    """UTC ISO 时间戳 (proposal/approval 审计)。"""
    return datetime.now(timezone.utc).isoformat()


def parse_change_request(text: str) -> str:
    """变更内容解析 (确定性, 规则优先): 去动作词/后缀通用名词 → 核心请求。

    "加导出功能" → "导出"; "新增数据统计" → "数据统计"; "加个暗色模式" → "暗色模式";
    "支持 Excel 导出" → "Excel 导出"。无动作词 → 原文 (不猜)。
    """
    raw = str(text or "").strip()
    if not raw:
        return ""
    request = raw
    for verb in _ACTION_VERBS:
        if request.startswith(verb) and len(request) > len(verb):
            request = request[len(verb):].strip()
            break
    for noun in _TRAILING_NOUNS:
        if request.endswith(noun) and len(request) > len(noun):
            request = request[: -len(noun)].strip()
            break
    return request or raw


def parse_change_reason(text: str) -> str:
    """变更理由解析 (确定性): "因为/为了/方便" 后文本; 缺省 "新增需求"。

    "加导出功能, 方便用户备份数据" → "方便用户备份数据"。
    """
    raw = str(text or "").strip()
    for marker in ("因为", "为了", "方便", "以便", "目的是"):
        idx = raw.find(marker)
        if idx >= 0:
            return raw[idx:].strip(" ，,。;；")
    return "新增需求"


def extract_keywords(request: str) -> list[str]:
    """请求 → 影响分析关键词 (去停用词, 中文 2-gram 兜底, 去重保序)。

    "导出" → ["导出"]; "数据统计" → ["数据统计", "数据", "统计"]。
    确定性 — 手算可对照。
    """
    text = str(request or "").strip()
    if not text:
        return []
    words: list[str] = []
    # ASCII 词元 (≥2 字符)
    words.extend(w.lower() for w in re.findall(r"[a-zA-Z0-9_]{2,}", text))
    # 中文: 整体 + 2-gram (≥2 字)
    for chunk in re.findall(r"[\u4e00-\u9fff]+", text):
        if len(chunk) >= 2:
            words.append(chunk)
        if len(chunk) >= 4:
            words.extend(chunk[i:i + 2] for i in range(len(chunk) - 1))
    seen: set[str] = set()
    result: list[str] = []
    for w in words:
        if w in _STOPWORDS or w in seen:
            continue
        seen.add(w)
        result.append(w)
    return result or ([text.lower()] if text else [])


def _read_json_safe(path: Path) -> dict[str, Any]:
    """读 JSON (缺失/损坏 → {}, 失败安全 — 影响分析不因单文件损坏中断)。"""
    try:
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 — 失败安全
        pass
    return {}


def _read_text_safe(path: Path) -> str:
    """读文本 (缺失/损坏 → "", 失败安全)。"""
    try:
        return path.read_text(encoding="utf-8") if path.is_file() else ""
    except Exception:  # noqa: BLE001 — 失败安全
        return ""


def _write_text(path: Path, text: str) -> None:
    """落盘文本 (真实生效 — 审批门/变更回流不允许 stub)。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, data: dict[str, Any]) -> None:
    """落盘 JSON (真实生效)。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


@dataclass
class ChangeProposal:
    """需求变更提案 (S10-111 M3-6 §2.1)。"""

    id: str
    project_slug: str
    request: str
    reason: str
    status: str = STATUS_PROPOSED
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_slug": self.project_slug,
            "request": self.request,
            "reason": self.reason,
            "status": self.status,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChangeProposal":
        data = data or {}
        return cls(
            id=str(data.get("id") or ""),
            project_slug=str(data.get("project_slug") or ""),
            request=str(data.get("request") or ""),
            reason=str(data.get("reason") or ""),
            status=str(data.get("status") or STATUS_PROPOSED),
            created_at=str(data.get("created_at") or ""),
        )


@dataclass
class ImpactAnalysis:
    """影响分析 (S10-111 M3-6 §2.1): 波及 PRD 章节/任务/依赖 (可枚举, 收敛)。"""

    proposal_id: str
    affected_prd_sections: list[str] = field(default_factory=list)
    affected_tasks: list[str] = field(default_factory=list)
    affected_dependencies: list[str] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "affected_prd_sections": list(self.affected_prd_sections),
            "affected_tasks": list(self.affected_tasks),
            "affected_dependencies": list(self.affected_dependencies),
            "note": self.note,
        }


class ChangeController:
    """需求变更控制器: propose → impact → apply (真实落盘生效)。"""

    def __init__(
        self,
        workspace: Any,
        *,
        llm_fn: Optional[Callable[[str, str], str]] = None,
    ) -> None:
        self.workspace = Path(workspace)
        #: LLM 补充注入点 (规则优先 — 仅当规则解析不足以提供 request/reason 时补充)
        self.llm_fn = llm_fn

    # ------------------------------------------------------------ 路径

    def _project_dir(self, slug: str) -> Path:
        return self.workspace / "projects" / str(slug or "")

    def _proposals_file(self, slug: str) -> Path:
        return self._project_dir(slug) / "change_control.json"

    def _prd_file(self, slug: str) -> Path:
        return self._project_dir(slug) / "PRD.md"

    def _tasks_file(self, slug: str) -> Path:
        return self._project_dir(slug) / "tasks.json"

    def _plan_file(self, slug: str) -> Path:
        return self._project_dir(slug) / "plan.json"

    def _execution_plan_file(self, slug: str) -> Path:
        return self._project_dir(slug) / "execution_plan.json"

    # ------------------------------------------------------------ 提案持久化

    def _load_proposals(self, slug: str) -> list[dict[str, Any]]:
        """change_control.json 提案列表 (缺失/损坏 → [], 失败安全)。"""
        data = _read_json_safe(self._proposals_file(slug))
        raw = data.get("proposals")
        if isinstance(raw, list):
            return [p for p in raw if isinstance(p, dict)]
        return []

    def _save_proposals(self, slug: str, proposals: list[dict[str, Any]]) -> None:
        """提案落盘 (真实生效 — 审计/追溯面)。"""
        _write_json(
            self._proposals_file(slug), {"proposals": proposals, "count": len(proposals)}
        )

    def _update_proposal_status(
        self, proposal: ChangeProposal, status: str
    ) -> ChangeProposal:
        """提案状态回写 (approved/rejected 落盘)。"""
        proposal.status = status
        proposals = self._load_proposals(proposal.project_slug)
        for item in proposals:
            if item.get("id") == proposal.id:
                item["status"] = status
                break
        self._save_proposals(proposal.project_slug, proposals)
        return proposal

    # ------------------------------------------------------------ propose

    def propose(self, slug: str, request: str) -> ChangeProposal:
        """propose: 解析变更内容+理由 (规则优先, LLM 可选补充) → ChangeProposal。

        确定性: "加导出功能" → request="导出", reason="新增需求"; 落盘
        change_control.json (status=proposed)。请求为空 → ValueError。
        """
        slug = str(slug or "").strip()
        request_text = str(request or "").strip()
        if not slug:
            raise ValueError("变更提案失败: 项目 slug 为空")
        if not request_text:
            raise ValueError("变更提案失败: 变更请求不能为空")
        if not self._project_dir(slug).is_dir():
            raise ValueError(f"变更提案失败: 项目不存在: {slug}")
        parsed = parse_change_request(request_text)
        reason = parse_change_reason(request_text)
        # LLM 补充 (规则优先 — 仅规则未产出具体 request 时补充, 不覆盖规则结果)
        if self.llm_fn is not None:
            try:
                text = str(self.llm_fn(request_text, "change_control") or "").strip()
                if text:
                    llm_parsed = parse_change_request(text) or text
                    if not parsed or parsed == request_text:
                        parsed = llm_parsed
                    if reason == "新增需求":
                        llm_reason = parse_change_reason(text)
                        if llm_reason != "新增需求":
                            reason = llm_reason
            except Exception:  # noqa: BLE001 — LLM 失败 → 确定性结果 (规则优先)
                pass
        proposal = ChangeProposal(
            id=f"chg-{re.sub(r'[^a-z0-9]+', '-', slug.lower()).strip('-') or 'proj'}-{uuid.uuid4().hex[:8]}",
            project_slug=slug,
            request=parsed or request_text,
            reason=reason,
            status=STATUS_PROPOSED,
            created_at=_now_iso(),
        )
        proposals = self._load_proposals(slug)
        proposals.append(proposal.to_dict())
        self._save_proposals(slug, proposals)
        return proposal

    # ------------------------------------------------------------ impact

    def impact(self, proposal: ChangeProposal) -> ImpactAnalysis:
        """impact: 读 PRD.md + tasks.json + plan.json, 关键词匹配波及面。

        确定性, 手算可枚举: 变更关键词命中 PRD 章节正文 / 任务名(含 feature/
        epic) → 波及项; 依赖边 (plan.json edges / dependencies.json) 涉及波及
        任务 → 波及依赖。过度波及收敛: 每类最多 MAX_AFFECTED 条 + note 标注。
        """
        slug = proposal.project_slug
        pdir = self._project_dir(slug)
        keywords = extract_keywords(proposal.request)
        sections: list[str] = []
        tasks: list[str] = []
        deps: list[str] = []

        # ① PRD 章节: 按 "## " 切节, 命中关键词正文 → 章节名
        prd_text = _read_text_safe(self._prd_file(slug))
        for heading, body in self._split_md_sections(prd_text):
            if keywords and any(k in body for k in keywords):
                sections.append(heading)

        # ② 任务: tasks.json (扁平 tasks) + plan.json (tasks) — 名称/feature/epic 命中
        task_names: dict[str, str] = {}
        tasks_data = _read_json_safe(self._tasks_file(slug))
        for t in tasks_data.get("tasks") or []:
            if isinstance(t, dict):
                tid = str(t.get("id") or "")
                if tid:
                    task_names.setdefault(tid, str(t.get("name") or tid))
        plan_data = _read_json_safe(self._plan_file(slug))
        for t in plan_data.get("tasks") or []:
            if isinstance(t, dict):
                tid = str(t.get("id") or "")
                if tid:
                    task_names.setdefault(tid, str(t.get("name") or tid))
        affected_ids: list[str] = []
        tasks_data = _read_json_safe(self._tasks_file(slug))
        by_id: dict[str, dict[str, Any]] = {}
        for t in tasks_data.get("tasks") or []:
            if isinstance(t, dict) and t.get("id"):
                by_id[str(t["id"])] = t
        for tid, tname in task_names.items():
            # feature/epic 归属一并参与匹配 (波及判定更全)
            haystack = tname
            t = by_id.get(tid) or {}
            if t:
                haystack = " ".join(
                    str(t.get(k) or "") for k in ("name", "feature", "epic")
                )
            if keywords and any(k in haystack for k in keywords):
                tasks.append(f"{tid} ({tname})")
                affected_ids.append(tid)

        # ③ 依赖: plan.json edges + dependencies.json 涉及波及任务
        affected_id_set = set(affected_ids)
        edges: list[tuple[str, str, str]] = []
        for e in plan_data.get("edges") or []:
            if isinstance(e, dict):
                edges.append(
                    (str(e.get("from") or e.get("from_task") or ""),
                     str(e.get("to") or e.get("to_task") or ""), "plan")
                )
        deps_data = _read_json_safe(pdir / "dependencies.json")
        for e in deps_data.get("edges") or deps_data.get("dependencies") or []:
            if isinstance(e, dict):
                edges.append(
                    (str(e.get("from") or e.get("from_task") or ""),
                     str(e.get("to") or e.get("to_task") or ""), "deps")
                )
        for a, b, source in edges:
            if affected_id_set and (a in affected_id_set or b in affected_id_set):
                deps.append(f"{a}→{b} ({source})")

        # 收敛: 每类上限 MAX_AFFECTED
        note_parts: list[str] = []
        if len(sections) > MAX_AFFECTED:
            sections = sections[:MAX_AFFECTED]
            note_parts.append("PRD 章节已收敛")
        if len(tasks) > MAX_AFFECTED:
            tasks = tasks[:MAX_AFFECTED]
            note_parts.append("任务已收敛")
        if len(deps) > MAX_AFFECTED:
            deps = deps[:MAX_AFFECTED]
            note_parts.append("依赖已收敛")
        note = "; ".join(note_parts)
        if not any((sections, tasks, deps)):
            note = "未匹配到直接波及项 — 变更将作为新增功能落地"
        return ImpactAnalysis(
            proposal_id=proposal.id,
            affected_prd_sections=sections,
            affected_tasks=tasks,
            affected_dependencies=deps,
            note=note,
        )

    @staticmethod
    def _split_md_sections(text: str) -> list[tuple[str, str]]:
        """markdown 按 "## " 二级标题切节 → [(标题, 正文)] (确定性)。"""
        sections: list[tuple[str, str]] = []
        current = ""
        body: list[str] = []
        for line in (text or "").splitlines():
            if line.startswith("## "):
                if current:
                    sections.append((current, "\n".join(body)))
                current = line[3:].strip()
                body = []
            else:
                body.append(line)
        if current:
            sections.append((current, "\n".join(body)))
        return sections

    # ------------------------------------------------------------ apply

    def apply(self, proposal: ChangeProposal, approved: bool) -> dict[str, Any]:
        """apply: y → PRD v2 + 变更日志 + DecomposeEngine 拆变更 → 新任务合并
        tasks.json + plan.json (+ execution_plan.json 生效); n → 不写不建。

        真实落盘生效 (禁止 stub): approved=True 且任何落盘失败 → 抛异常由调用方
        明确报错; approved=False → 只回写 status=rejected。
        """
        slug = proposal.project_slug
        if not approved:
            self._update_proposal_status(proposal, STATUS_REJECTED)
            return {
                "status": STATUS_REJECTED,
                "applied": False,
                "proposal_id": proposal.id,
                "message": "已拒绝, 未变更",
                "prd_version": None,
                "new_tasks": [],
            }
        # ① PRD 升版 v2 + 变更日志
        impact = self.impact(proposal)
        changelog = self._append_prd_v2(proposal, impact)
        # ② DecomposeEngine 拆变更 → 原子叶子 (M3a 复用, evaluate_after=False 确定性)
        leaves = self._decompose_change(proposal)
        # ③ 新任务合并 tasks.json + plan.json + execution_plan.json
        task_summary = self._merge_tasks(slug, proposal, leaves)
        plan_summary = self._merge_plan(slug, proposal, leaves)
        self._merge_execution_plan(slug, proposal, leaves)
        self._update_proposal_status(proposal, STATUS_APPROVED)
        return {
            "status": STATUS_APPROVED,
            "applied": True,
            "proposal_id": proposal.id,
            "message": f"变更已批准并落地: {proposal.request} (PRD v2 + {len(leaves)} 新任务)",
            "prd_version": 2,
            "changelog": changelog,
            "new_tasks": [str(l.get("id") or "") for l in leaves],
            "tasks_json_updated": bool(task_summary),
            "plan_json_updated": bool(plan_summary),
            "affected_tasks": impact.affected_tasks,
        }

    def _append_prd_v2(
        self, proposal: ChangeProposal, impact: ImpactAnalysis
    ) -> str:
        """PRD.md 追加 '# 变更记录 v2: {request}' + 变更日志条目 (文件尾标记 v2)。"""
        prd_path = self._prd_file(proposal.project_slug)
        existing = _read_text_safe(prd_path)
        if not existing.strip():
            # PRD 缺失 → 建基础 PRD 头 (真实落盘, 变更记录仍可追溯)
            existing = f"# {proposal.project_slug} — 产品需求文档 (PRD)\n"
        sections = "\n".join(
            f"- {s}" for s in impact.affected_prd_sections
        ) or "- (未匹配到直接章节, 变更作为新增功能)"
        tasks = "\n".join(f"- {t}" for t in impact.affected_tasks) or "- (新增任务)"
        entry = (
            f"{CHANGE_HEADING}: {proposal.request}\n\n"
            f"## 变更日志\n"
            f"- 时间: {_now_iso()}\n"
            f"- 提案: {proposal.id}\n"
            f"- 请求: {proposal.request}\n"
            f"- 理由: {proposal.reason}\n"
            f"- 状态: 已批准 (v2)\n"
            f"- 影响 PRD 章节:\n{sections}\n"
            f"- 影响任务:\n{tasks}\n"
        )
        updated = existing.rstrip() + "\n\n" + entry
        _write_text(prd_path, updated)
        return entry

    def _decompose_change(self, proposal: ChangeProposal) -> list[dict[str, Any]]:
        """复用 M3a DecomposeEngine 拆变更 → 原子叶子 (确定性, evaluate_after=False)。

        产品字段读 product.json (供确定性 feature 拆分); 拆解失败 → 单功能任务
        兜底 (真实任务, 非占位 — 变更回流必须产生可执行任务)。
        """
        from .decomposer import DecomposeEngine

        product = _read_json_safe(
            self._project_dir(proposal.project_slug) / "product.json"
        )
        root_task = {
            "id": proposal.id,
            "name": f"实现变更: {proposal.request}",
            "goal": f"实现需求变更: {proposal.request}",
            "requirement": f"需求变更 ({proposal.reason}): {proposal.request}",
            "agent_type": "backend",
        }
        eng = DecomposeEngine(
            workspace=self.workspace,
            project_id=proposal.project_slug,
            evaluate_after=False,  # 变更拆解走确定性路径 (M3d 评估后置, 不阻塞)
        )
        result = eng.decompose(root_task, product=product)
        leaves = [dict(l) for l in (result.leaves or [])]
        if not leaves:
            leaves = [
                {
                    "id": f"task-chg-{proposal.id}-core",
                    "name": f"实现 {proposal.request}",
                    "goal": f"实现需求变更: {proposal.request}",
                    "agent_type": "backend",
                    "verify_cmd": "pytest",
                    "est_minutes": 8,
                    "verified": False,
                    "unverified": True,
                }
            ]
        return leaves

    def _merge_tasks(
        self, slug: str, proposal: ChangeProposal, leaves: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """新任务合并 tasks.json (epics + 扁平 tasks, FeatureTaskGenerator 结构兼容)。"""
        tasks_path = self._tasks_file(slug)
        tasks_data = _read_json_safe(tasks_path)
        if not tasks_data:
            tasks_data = {"epics": [], "tasks": [], "count": 0}
        epics = list(tasks_data.get("epics") or [])
        flat = list(tasks_data.get("tasks") or [])
        existing_ids = {str(t.get("id") or "") for t in flat}
        epic_name = f"变更: {proposal.request}"
        epic_id = f"epic-chg-{proposal.id}"
        feature_tasks: list[dict[str, str]] = []
        for idx, leaf in enumerate(leaves):
            task_id = str(leaf.get("id") or f"task-chg-{proposal.id}-{idx}")
            if task_id in existing_ids:
                task_id = f"{task_id}-{uuid.uuid4().hex[:4]}"
            name = str(leaf.get("name") or f"实现 {proposal.request}")
            agent_type = str(leaf.get("agent_type") or "backend")
            flat.append(
                {
                    "id": task_id,
                    "name": name,
                    "epic": epic_name,
                    "epic_id": epic_id,
                    "feature": proposal.request,
                    "agent_type": agent_type,
                    "priority": "P0",
                }
            )
            feature_tasks.append(
                {"id": task_id, "name": name, "agent_type": agent_type, "priority": "P0"}
            )
            existing_ids.add(task_id)
        epics.append(
            {"id": epic_id, "name": epic_name, "features": [{"name": proposal.request, "tasks": feature_tasks}]}
        )
        tasks_data["epics"] = epics
        tasks_data["tasks"] = flat
        tasks_data["count"] = len(flat)
        _write_json(tasks_path, tasks_data)
        return {"epics": len(epics), "tasks": len(flat), "added": len(leaves)}

    def _merge_plan(
        self, slug: str, proposal: ChangeProposal, leaves: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """新任务合并 plan.json (动态 DAG 已有 — 追加 tasks, 无依赖边 → 就绪可调度)。

        plan.json 缺失 → 创建 (真实落盘; TaskScheduler 可直接消费)。
        """
        plan_path = self._plan_file(slug)
        plan_data = _read_json_safe(plan_path)
        if not plan_data:
            plan_data = {"project_id": slug, "tasks": [], "edges": [], "critical_path": [], "order": []}
        plan_tasks = list(plan_data.get("tasks") or [])
        existing_ids = {str(t.get("id") or "") for t in plan_tasks}
        added: list[str] = []
        for idx, leaf in enumerate(leaves):
            task_id = str(leaf.get("id") or f"task-chg-{proposal.id}-{idx}")
            if task_id in existing_ids:
                task_id = f"{task_id}-{uuid.uuid4().hex[:4]}"
            plan_tasks.append(
                {
                    "id": task_id,
                    "name": str(leaf.get("name") or f"实现 {proposal.request}"),
                    "goal": str(leaf.get("goal") or ""),
                    "agent_type": str(leaf.get("agent_type") or "backend"),
                    "verify_cmd": str(leaf.get("verify_cmd") or ""),
                    "est_minutes": int(leaf.get("est_minutes") or 8),
                    "verified": bool(leaf.get("verified", False)),
                    "unverified": bool(leaf.get("unverified", True)),
                    "critical": False,
                    "feature": proposal.request,
                    "source": "change_control",
                }
            )
            existing_ids.add(task_id)
            added.append(task_id)
        plan_data["tasks"] = plan_tasks
        plan_data["project_id"] = slug
        if "count" in plan_data:
            plan_data["count"] = len(plan_tasks)
        # 追加任务无依赖边 → 保持原 edges/order (TaskScheduler 按新 tasks 重算轮次)
        _write_json(plan_path, plan_data)
        return {"tasks": len(plan_tasks), "added": added}

    def _merge_execution_plan(
        self, slug: str, proposal: ChangeProposal, leaves: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """新任务合并 execution_plan.json (solo 执行路径生效 — 变更回流真实可执行)。"""
        plan_path = self._execution_plan_file(slug)
        plan_data = _read_json_safe(plan_path)
        if not plan_data:
            plan_data = {"tasks": [], "count": 0}
        tasks = list(plan_data.get("tasks") or [])
        existing_ids = {str(t.get("id") or "") for t in tasks}
        for idx, leaf in enumerate(leaves):
            task_id = str(leaf.get("id") or f"task-chg-{proposal.id}-{idx}")
            if task_id in existing_ids:
                task_id = f"{task_id}-{uuid.uuid4().hex[:4]}"
            agent_type = str(leaf.get("agent_type") or "backend")
            tasks.append(
                {
                    "id": task_id,
                    "name": str(leaf.get("name") or f"实现 {proposal.request}"),
                    "agent_type": agent_type,
                    "agent": "backend-1",
                    "feature": proposal.request,
                    "epic": f"变更: {proposal.request}",
                    "priority": "P0",
                    "reason": f"需求变更 (S10-111 M3-6): {proposal.request}",
                }
            )
            existing_ids.add(task_id)
        plan_data["tasks"] = tasks
        plan_data["count"] = len(tasks)
        _write_json(plan_path, plan_data)
        return {"tasks": len(tasks), "added": len(leaves)}

    # ------------------------------------------------------------ 查询

    def list_proposals(self, slug: str) -> list[ChangeProposal]:
        """项目全部提案 (审计/展示, 只读)。"""
        return [ChangeProposal.from_dict(p) for p in self._load_proposals(slug)]


__all__ = [
    "STATUS_PROPOSED",
    "STATUS_APPROVED",
    "STATUS_REJECTED",
    "CHANGE_HEADING",
    "parse_change_request",
    "parse_change_reason",
    "extract_keywords",
    "ChangeProposal",
    "ImpactAnalysis",
    "ChangeController",
]
