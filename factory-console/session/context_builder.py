"""factory-console/session/context_builder.py — ContextBuilder (S10-062 批次 A)。

LLM Planning 基础设施 (GAP G3, 设计 §2): 把项目资产 (PRD.md /
engineering.json / execution_state.json / execution_plan.json /
workspace_context.json / validation_result.json / gap_analysis.json /
replanning_decisions.json / team_execution_state.json / project.json) 组装为
AutonomousPlanningContext — LLM Planner 的结构化输入。

AutonomousPlanningContext 结构:
  meta: {slug, built_at, sources, total_tokens, truncated}
  project / product / requirements / engineering / current_plan /
  completed_work / failed_work / validation / artifacts / workspace / team /
  capabilities / previous_decisions / previous_replans
  每字段: {"source": "<来源资产文件名>", "value": <内容>} — 来源可追踪
  (source 恒为定义该字段的规范资产文件名, meta.sources 记录该文件是否真实读到)

组件:
- build(project_dir, slug) — 组装完整上下文 (每字段 source 标识)
- estimate_tokens(text) — token 粗估 (中文 ≈1 char/token, 其他 ≈4 chars/token)
- truncate(context, max_tokens) — token budget 裁剪 (保留关键字段, 贪心按优先级)
- extract_evidence(validation_result, execution_state, workspace) —
  [{source, field, observation}] evidence 列表

失败安全: 任意资产缺失/损坏/非预期结构 → 缺省空字段, 永不抛。

边界 (批次 A 基础设施):
- 纯标准库 (json/re/dataclasses/datetime/pathlib/copy) + 只读引用
  session/roles.ROLES (capabilities 来源), 零新依赖, 不修改任何现有模块
- 只构建上下文, 不调 LLM / 不改 DAG / 不落盘 (落盘由调用方 / PlanningTrace 负责)

设计: docs/sprint10/S10-062-llm-planning-design.md §2
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .roles import ROLES

# ---------------------------------------------------------------- 资产文件名
#: 项目级资产文件名 (projects/<slug>/ — 各来源资产口径)
PRD_FILE_NAME = "PRD.md"
PROJECT_FILE_NAME = "project.json"
ENGINEERING_FILE_NAME = "engineering.json"
EXECUTION_PLAN_FILE_NAME = "execution_plan.json"
EXECUTION_STATE_FILE_NAME = "execution_state.json"
VALIDATION_RESULT_FILE_NAME = "validation_result.json"
WORKSPACE_CONTEXT_FILE_NAME = "workspace_context.json"
GAP_ANALYSIS_FILE_NAME = "gap_analysis.json"
REPLANNING_DECISIONS_FILE_NAME = "replanning_decisions.json"
TEAM_EXECUTION_STATE_FILE_NAME = "team_execution_state.json"

#: 字段 → 规范来源资产 (source 标识, 设计 §2 — 来源可追踪)
FIELD_SOURCES: dict[str, str] = {
    "project": PROJECT_FILE_NAME,
    "product": PRD_FILE_NAME,
    "requirements": PRD_FILE_NAME,
    "engineering": ENGINEERING_FILE_NAME,
    "current_plan": EXECUTION_PLAN_FILE_NAME,
    "completed_work": EXECUTION_STATE_FILE_NAME,
    "failed_work": EXECUTION_STATE_FILE_NAME,
    "validation": VALIDATION_RESULT_FILE_NAME,
    "artifacts": WORKSPACE_CONTEXT_FILE_NAME,
    "workspace": WORKSPACE_CONTEXT_FILE_NAME,
    "team": TEAM_EXECUTION_STATE_FILE_NAME,
    "capabilities": "roles.py",
    "previous_decisions": REPLANNING_DECISIONS_FILE_NAME,
    "previous_replans": GAP_ANALYSIS_FILE_NAME,
}

#: 字段裁剪优先级 (truncate 保留顺序: 高 → 低; 低优先级先被裁剪/丢弃)
FIELD_PRIORITY: tuple[str, ...] = (
    "requirements",
    "engineering",
    "current_plan",
    "product",
    "completed_work",
    "failed_work",
    "validation",
    "project",
    "workspace",
    "team",
    "capabilities",
    "artifacts",
    "previous_decisions",
    "previous_replans",
)

#: 字段空缺省值 (truncate 丢弃字段后的占位 — 结构保持, 下游可解析)
EMPTY_VALUES: dict[str, Any] = {
    "project": {"name": "", "slug": ""},
    "product": {"name": "", "platform": "", "summary": "", "requirements": []},
    "requirements": [],
    "engineering": {},
    "current_plan": [],
    "completed_work": [],
    "failed_work": [],
    "validation": {},
    "artifacts": [],
    "workspace": {},
    "team": {},
    "capabilities": {},
    "previous_decisions": [],
    "previous_replans": [],
}


def _now_iso() -> str:
    """UTC 当前时间 ISO 格式 (上下文构建时间戳)。"""
    return datetime.now(timezone.utc).isoformat()


class ContextBuilder:
    """AutonomousPlanningContext 构建器 (设计 §2)。

    build(project_dir, slug) — 从项目资产组装完整上下文, 每字段带 source
    来源标识 + meta (slug/built_at/sources/total_tokens/truncated)。
    estimate_tokens(text) — token 粗估 (中文 ≈1 char/token, 其他 ≈4
    chars/token, 向上取整)。truncate(context, max_tokens) — token budget
    裁剪 (贪心按 FIELD_PRIORITY 保留关键字段, 低优先级字段先被丢弃/截断)。
    extract_evidence(validation_result, execution_state, workspace) —
    evidence 提取 [{source, field, observation}]。

    失败安全: 缺失/损坏资产 → 缺省空字段, 永不抛。
    """

    #: 全部上下文字段名 (验收口径)
    CONTEXT_FIELDS: tuple[str, ...] = (
        "project", "product", "requirements", "engineering", "current_plan",
        "completed_work", "failed_work", "validation", "artifacts",
        "workspace", "team", "capabilities", "previous_decisions",
        "previous_replans",
    )

    # ------------------------------------------------------------ build

    def build(
        self, project_dir: Any, slug: Optional[str] = None
    ) -> dict[str, Any]:
        """组装 AutonomousPlanningContext (设计 §2 全字段 + source 标识)。

        project_dir: 项目目录 (projects/<slug>/ — 资产读取根);
        slug: 项目标识 (缺省取目录名)。

        每字段 {"source": <规范资产文件名>, "value": <内容>}; meta.sources
        记录每个资产文件是否真实读到 (缺失/损坏 → False + 缺省空值, 不抛)。
        """
        try:
            root = Path(project_dir)
        except TypeError:  # noqa: BLE001 — 失败安全: 非路径输入 → str 化
            root = Path(str(project_dir))
        slug = str(slug or root.name)
        sources: dict[str, bool] = {}

        def read_json(name: str, default: Any) -> Any:
            """读取 JSON 资产 (缺失/损坏/非 JSON → default, 失败安全)。"""
            path = root / name
            try:
                if not path.is_file():
                    sources[name] = False
                    return default
                data = json.loads(path.read_text(encoding="utf-8"))
                sources[name] = True
                return data
            except Exception:  # noqa: BLE001 — 失败安全: 损坏 → 缺省
                sources[name] = False
                return default

        # ---- project (project.json)
        pj = read_json(PROJECT_FILE_NAME, {})
        pj = pj if isinstance(pj, dict) else {}
        project = {
            "name": str(pj.get("name") or slug),
            "slug": str(pj.get("slug") or slug),
        }

        # ---- product / requirements (PRD.md)
        prd_text = self._read_text(root, PRD_FILE_NAME, sources)
        product = self._parse_prd(prd_text, slug)
        requirements = [str(r) for r in (product.get("requirements") or [])]

        # ---- engineering (engineering.json)
        eng_raw = read_json(ENGINEERING_FILE_NAME, {})
        engineering = self._normalize_engineering(eng_raw)

        # ---- current_plan (execution_plan.json)
        plan_raw = read_json(EXECUTION_PLAN_FILE_NAME, {})
        current_plan = self._tasks_list(plan_raw)

        # ---- completed_work / failed_work (execution_state.json)
        state_raw = read_json(EXECUTION_STATE_FILE_NAME, {})
        state = state_raw if isinstance(state_raw, dict) else {}
        tasks = self._tasks_list(state.get("tasks"))
        completed_work = [
            t for t in tasks if str(t.get("status") or "") == "completed"
        ]
        failed_work = [
            t for t in tasks if str(t.get("status") or "") == "failed"
        ]

        # ---- validation (validation_result.json)
        val_raw = read_json(VALIDATION_RESULT_FILE_NAME, {})
        validation = self._normalize_validation(val_raw)

        # ---- workspace / artifacts (workspace_context.json)
        ws_raw = read_json(WORKSPACE_CONTEXT_FILE_NAME, {})
        workspace = ws_raw if isinstance(ws_raw, dict) else {}
        artifacts = [
            str(a) for a in (workspace.get("artifacts") or [])
            if not isinstance(a, dict)
        ]

        # ---- team (team_execution_state.json)
        team_raw = read_json(TEAM_EXECUTION_STATE_FILE_NAME, {})
        team = self._normalize_team(team_raw)

        # ---- capabilities (roles.py — 静态规格, 恒可读)
        capabilities = self._capabilities()

        # ---- previous_decisions / previous_replans
        decisions_raw = read_json(REPLANNING_DECISIONS_FILE_NAME, [])
        previous_decisions = [
            dict(d) for d in (decisions_raw if isinstance(decisions_raw, list)
                              else []) if isinstance(d, dict)
        ]
        replans_raw = read_json(GAP_ANALYSIS_FILE_NAME, [])
        previous_replans = [
            dict(d) for d in (replans_raw if isinstance(replans_raw, list)
                              else []) if isinstance(d, dict)
        ]

        values: dict[str, Any] = {
            "project": project,
            "product": product,
            "requirements": requirements,
            "engineering": engineering,
            "current_plan": current_plan,
            "completed_work": completed_work,
            "failed_work": failed_work,
            "validation": validation,
            "artifacts": artifacts,
            "workspace": workspace,
            "team": team,
            "capabilities": capabilities,
            "previous_decisions": previous_decisions,
            "previous_replans": previous_replans,
        }
        context: dict[str, Any] = {
            field: {"source": FIELD_SOURCES[field], "value": values[field]}
            for field in FIELD_SOURCES
        }
        context["meta"] = {
            "slug": slug,
            "built_at": _now_iso(),
            "sources": dict(sources),
            "total_tokens": 0,
            "truncated": False,
        }
        # total_tokens 口径: 含 meta 的完整上下文大小 (置 0 再测 — 自洽)
        context["meta"]["total_tokens"] = self._measure(context)
        return context

    # ------------------------------------------------------------ token 估算

    @staticmethod
    def estimate_tokens(text: Any) -> int:
        """token 粗估 (设计 §2): 中文 ≈1 char/token, 其他 ≈4 chars/token。

        确定性规则, 无外部依赖: CJK 字符 (含全角) 每字 1 token; 其余字符
        每 4 字符 1 token (向上取整)。None/空 → 0。
        """
        s = str(text or "")
        if not s:
            return 0
        cjk = sum(
            1 for ch in s
            if "\u4e00" <= ch <= "\u9fff"
            or "\u3000" <= ch <= "\u303f"
            or "\uff00" <= ch <= "\uffef"
        )
        other = len(s) - cjk
        return cjk + (other + 3) // 4

    # ------------------------------------------------------------ budget 裁剪

    def truncate(
        self, context: Any, max_tokens: Optional[int] = None
    ) -> dict[str, Any]:
        """token budget 裁剪 (设计 §2): 超限 → 保留关键字段。

        规则 (确定性): ① 非 dict → {}; ② max_tokens None/<=0 → 原样拷贝
        (不裁剪); ③ 深拷贝后按 FIELD_PRIORITY (高→低) 精确记账 — 从最低
        优先级开始丢弃字段 (置空缺省值, 结构保持), 直到大小 ≤ budget 或仅剩
        1 个字段; ④ 仍超限 → 对剩余最高优先级字段按剩余预算截断 (_fit,
        单调收缩); ⑤ meta 重算 {total_tokens, truncated}。

        保证: budget ≥ 最小结构开销 (meta + 空字段结构) 时, 结果
        total_tokens ≤ budget; budget 小于最小开销时返回最小上下文
        (无法更小)。不修改输入 context (返回新 dict); 永不抛。
        """
        if not isinstance(context, dict):
            return {}
        if max_tokens is None or int(max_tokens) <= 0:
            return self._with_meta(deepcopy(context), truncated=False)
        budget = int(max_tokens)
        result = deepcopy(context)
        result.pop("meta", None)
        fields = [f for f in FIELD_PRIORITY if f in result]
        if not fields:
            return self._with_meta(result, truncated=False)

        def empty_field(f: str) -> dict[str, Any]:
            return {
                "source": FIELD_SOURCES.get(f, ""),
                "value": deepcopy(EMPTY_VALUES.get(f, "")),
            }

        if self._measure(result) <= budget:
            return self._with_meta(deepcopy(context), truncated=False)

        # 从最低优先级开始丢弃字段 (保留 ≥1 个), 每步真实测量 — 精确
        while len(fields) > 1:
            f = fields.pop()
            result[f] = empty_field(f)
            if self._measure(result) <= budget:
                return self._with_meta(result, truncated=True)

        # 仅剩最高优先级字段仍超限 → 按剩余预算截断 (整体 ≤ budget)
        f = fields[0]
        probe = deepcopy(result)
        probe[f] = empty_field(f)
        rest = self._measure(probe)
        field_budget = max(1, budget - rest)
        if self._size_tokens({f: result[f]}) > field_budget:
            result[f] = self._fit(result[f], field_budget)
        return self._with_meta(result, truncated=True)

    # ------------------------------------------------------------ evidence

    def extract_evidence(
        self,
        validation_result: Any = None,
        execution_state: Any = None,
        workspace: Any = None,
    ) -> list[dict[str, Any]]:
        """evidence 提取 (设计 §2): [{source, field, observation}]。

        来源: validation_result.json (success/tests/errors) +
        execution_state.json (completed/failed tasks/replan_count) +
        workspace_context.json (completed_tasks/artifacts/files)。
        非 dict 输入 → 空列表 (失败安全); observation 有长度上限。
        """
        out: list[dict[str, Any]] = []
        val = validation_result if isinstance(validation_result, dict) else {}
        if "success" in val:
            out.append({
                "source": VALIDATION_RESULT_FILE_NAME,
                "field": "success",
                "observation": f"validation.success={bool(val.get('success'))}",
            })
        if any(
            val.get(k) is not None
            for k in ("tests_total", "tests_passed", "tests_failed")
        ):
            out.append({
                "source": VALIDATION_RESULT_FILE_NAME,
                "field": "tests",
                "observation": (
                    f"tests: {int(val.get('tests_passed') or 0)} passed / "
                    f"{int(val.get('tests_failed') or 0)} failed "
                    f"(total {int(val.get('tests_total') or 0)})"
                ),
            })
        errors = val.get("errors") or []
        if isinstance(errors, list):
            for e in errors[:5]:
                out.append({
                    "source": VALIDATION_RESULT_FILE_NAME,
                    "field": "errors",
                    "observation": f"validation.error: {str(e)[:200]}",
                })

        state = execution_state if isinstance(execution_state, dict) else {}
        tasks = self._tasks_list(state.get("tasks"))
        completed = [
            t for t in tasks if str(t.get("status") or "") == "completed"
        ]
        failed = [t for t in tasks if str(t.get("status") or "") == "failed"]
        if completed:
            ids = ", ".join(
                str(t.get("id") or t.get("name") or "") for t in completed[:5]
            )
            out.append({
                "source": EXECUTION_STATE_FILE_NAME,
                "field": "completed_work",
                "observation": f"completed tasks: {len(completed)} ({ids})",
            })
        if failed:
            ids = ", ".join(
                str(t.get("id") or t.get("name") or "") for t in failed[:5]
            )
            out.append({
                "source": EXECUTION_STATE_FILE_NAME,
                "field": "failed_work",
                "observation": f"failed tasks: {len(failed)} ({ids})",
            })
        if "replan_count" in state:
            out.append({
                "source": EXECUTION_STATE_FILE_NAME,
                "field": "replan_count",
                "observation": f"replan_count={int(state.get('replan_count') or 0)}",
            })

        ws = workspace if isinstance(workspace, dict) else {}
        for key, label in (
            ("completed_tasks", "workspace completed_tasks"),
            ("artifacts", "artifacts"),
            ("files", "workspace files"),
        ):
            items = ws.get(key)
            if isinstance(items, list) and items:
                out.append({
                    "source": WORKSPACE_CONTEXT_FILE_NAME,
                    "field": key,
                    "observation": f"{label}: {len(items)}",
                })
        return out

    # ------------------------------------------------------------ 内部

    @staticmethod
    def _read_text(root: Path, name: str, sources: dict[str, bool]) -> str:
        """读取文本资产 (PRD.md; 缺失/损坏 → "", 失败安全)。"""
        try:
            path = root / name
            if path.is_file():
                sources[name] = True
                return path.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001 — 失败安全
            pass
        sources[name] = False
        return ""

    @classmethod
    def _parse_prd(cls, text: str, slug: str) -> dict[str, Any]:
        """PRD.md 轻量解析: name (# 一级标题) / platform (平台: xxx) /
        summary (首个正文段落) / requirements (bullet 行)。失败安全。"""
        lines = [ln.strip() for ln in str(text or "").splitlines()]
        name = str(slug or "")
        for ln in lines:
            if ln.startswith("# ") and ln[2:].strip():
                name = ln[2:].strip()
                break
        platform = ""
        for ln in lines:
            m = re.match(r"^\s*平台\s*[:：]\s*(\S+)", ln)
            if m:
                platform = m.group(1).strip().lower()
                break
        summary = ""
        for ln in lines:
            if (
                ln and not ln.startswith("#") and not ln.startswith(("-", "*"))
                and not re.match(r"^\d+[.、]", ln)
            ):
                summary = ln[:200]
                break
        reqs = [
            ln.lstrip("-*•").strip()
            for ln in lines if ln.startswith(("-", "*", "•"))
        ]
        reqs = [r for r in reqs if r]
        return {
            "name": name,
            "platform": platform,
            "summary": summary,
            "requirements": reqs,
        }

    @classmethod
    def _normalize_engineering(cls, raw: Any) -> dict[str, Any]:
        """engineering.json → 规范 dict (非 dict → 规范空 dict, 失败安全)。"""
        if not isinstance(raw, dict):
            raw = {}
        return {
            "name": str(raw.get("name") or ""),
            "platform": str(raw.get("platform") or ""),
            "architecture": raw.get("architecture") or "",
            "modules": raw.get("modules") or [],
            "technical_tasks": raw.get("technical_tasks") or [],
        }

    @classmethod
    def _normalize_validation(cls, raw: Any) -> dict[str, Any]:
        """validation_result.json → 规范 dict (非 dict → 规范空 dict)。"""
        if not isinstance(raw, dict):
            raw = {}
        return {
            "success": bool(raw.get("success")),
            "tests_total": int(raw.get("tests_total") or 0),
            "tests_passed": int(raw.get("tests_passed") or 0),
            "tests_failed": int(raw.get("tests_failed") or 0),
            "errors": [str(e) for e in (raw.get("errors") or [])],
        }

    @classmethod
    def _normalize_team(cls, raw: Any) -> dict[str, Any]:
        """team_execution_state.json → 规范 dict (非 dict → 规范空 dict)。"""
        if not isinstance(raw, dict):
            raw = {}
        return {
            "team": str(raw.get("team") or ""),
            "status": str(raw.get("status") or ""),
            "plan_version": int(raw.get("plan_version") or 1),
            "tasks_count": len(cls._tasks_list(raw.get("tasks"))),
        }

    @classmethod
    def _capabilities(cls) -> dict[str, Any]:
        """capabilities (roles.py 静态规格 — 恒可读, 来源标识 roles.py)。"""
        roles = [str(r) for r in ROLES.keys()]
        caps = sorted({
            str(c) for spec in ROLES.values()
            for c in (spec.get("capabilities") or [])
        })
        return {"roles": roles, "capabilities": caps}

    @staticmethod
    def _tasks_list(raw: Any) -> list[dict[str, Any]]:
        """任意任务容器 → 任务 dict 列表 (dict{id: task} / list / {tasks: [...]})。

        非 dict 元素丢弃 (失败安全)。"""
        if isinstance(raw, dict) and "tasks" in raw:
            raw = raw["tasks"]
        if isinstance(raw, dict):
            return [dict(v) for v in raw.values() if isinstance(v, dict)]
        if isinstance(raw, list):
            return [dict(t) for t in raw if isinstance(t, dict)]
        return []

    @classmethod
    def _measure(cls, ctx: dict[str, Any]) -> int:
        """上下文大小 (meta.total_tokens 口径): 含 meta 的完整序列化估计,
        但把 meta.total_tokens 置 0 再测 — 避免自引用, build/truncate 全局一致。"""
        probe = deepcopy(ctx)
        meta = dict(probe.get("meta") or {})
        meta["total_tokens"] = 0
        probe["meta"] = meta
        return cls._size_tokens(probe)

    @classmethod
    def _size_tokens(cls, obj: Any) -> int:
        """对象序列化后的 token 粗估 (meta.total_tokens 口径)。"""
        try:
            return cls.estimate_tokens(
                json.dumps(obj, ensure_ascii=False, default=str)
            )
        except Exception:  # noqa: BLE001 — 失败安全
            return 0

    @classmethod
    def _fit(cls, value: Any, budget: int) -> Any:
        """把字段值单调收缩至 estimate_tokens ≤ budget (结构保留)。

        循环: 按字符预算裁剪 (初始 budget*3 chars, 每轮 ×0.7), 直到
        estimate ≤ budget 或字符预算 ≤ 1。确定性, 永不抛。
        """
        if cls._size_tokens(value) <= budget:
            return value
        chars = max(1, int(budget) * 3)
        for _ in range(40):
            candidate = cls._trim_chars(value, chars)
            if cls._size_tokens(candidate) <= budget:
                return candidate
            chars = max(1, int(chars * 0.7))
        return cls._trim_chars(value, 1)

    @classmethod
    def _trim_chars(cls, value: Any, chars: int) -> Any:
        """按字符数裁剪 (str → 前缀; list → 前缀项; dict → 每值均分; 其余原样)。"""
        if isinstance(value, str):
            return value[:max(0, chars)]
        if isinstance(value, list):
            out: list[Any] = []
            used = 0
            for item in value:
                if used >= chars:
                    break
                trimmed = cls._trim_chars(item, chars - used)
                out.append(trimmed)
                used += len(str(trimmed))
            return out
        if isinstance(value, dict):
            share = max(1, chars // max(1, len(value)))
            return {
                str(k): cls._trim_chars(v, share) for k, v in value.items()
            }
        return value

    @classmethod
    def _with_meta(cls, ctx: dict[str, Any], truncated: bool) -> dict[str, Any]:
        """meta 重算 (total_tokens 反映裁剪后实际大小; truncated 标志)。"""
        meta = dict(ctx.get("meta") or {})
        meta["total_tokens"] = cls._measure(ctx)
        meta["truncated"] = bool(truncated)
        ctx["meta"] = meta
        return ctx
