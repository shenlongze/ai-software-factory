"""src/legacy/factory-console/canonical_golden_path.py — Canonical Conversation Application Orchestrator.

R0 P0 (2026-09-08): 让 CLI (随后 API/WebUI) 通过同一个 Application Orchestrator
进入 Conversation Application → Product Understanding → Golden Path → Production Runtime。

边界 (本模块是 Orchestrator, 不是新业务域):
- 复用 conversation_app / golden_path / product_truth / production_runtime;
  不复制 Conversation / Product Understanding / PRD / Plan / Task / Execution /
  Artifact / Verification 任何 Domain (不建第二套 Truth)。
- Lifecycle Gate 由 golden_path (approved PRD / approved Plan) 强制; 本层只做
  自然语言 → 既有生命周期命令的保守映射。Intent ≠ Lifecycle: 未达 Gate 的命令
  被 Domain 拒绝并如实反馈, 绝不绕过、绝不自动批准/自动执行。
- 产品语义理解走 ProductUnderstandingService (生产 LLM / 测试 deterministic);
  本层不建立 keyword/regex 业务理解, 仅识别少量显式生命周期短语。
"""
from __future__ import annotations

import re
import json
from pathlib import Path
from typing import Any, Callable

from factory_console import golden_path as gp
from factory_console.conversation_app import (
    ConversationApplicationService,
    ProductUnderstandingService,
)
from factory_console.product_understanding import get_conversation

# 生命周期命令 (Application 层自然语言映射 → 既有 golden_path 命令)。
# 保守整句匹配 (去空白/标点/礼貌引导词), 不做贪婪子串业务判断。
_LIFECYCLE_PHRASES: dict[str, tuple[str, ...]] = {
    "generate_prd": (
        "整理成prd", "生成prd", "写prd", "出prd", "整理prd", "整理成产品需求",
        "生成产品需求", "生成prd文档", "整理成prd文档", "生成产品需求文档",
    ),
    "approve_prd": (
        "就按这个做", "按这个做", "就按这个方案做", "可以按这个做", "确认prd",
        "确认方案", "prd没问题", "prd可以",
    ),
    "generate_plan": (
        "生成计划", "制定计划", "做计划", "出计划", "生成开发计划",
        "制定开发计划", "生成执行计划", "整理成开发计划",
    ),
    "approve_plan": (
        "确认计划", "计划没问题", "按计划做", "可以开始计划", "确认开发计划",
        "按开发计划做",
    ),
    "execute": (
        "开始做", "开始实现", "开始开发", "开始执行", "动手做", "就做吧",
        "开始做吧", "执行吧", "开始",
    ),
    "status": ("状态", "到哪了", "现在什么阶段", "进展如何", "当前状态", "现在到哪了"),
}

_STRIP_LEAD = re.compile(r"^(请|帮我|麻烦你|麻烦|可以帮我|请帮我|帮我一下|你帮我)+")
_STRIP_CHARS = re.compile(
    r"[\s，。；、,.!！?？:：;；\"'“”‘’\-_/\\|~～()（）【】\[\]]")


def _norm(text: str) -> str:
    t = _STRIP_LEAD.sub("", str(text or "").strip())
    return _STRIP_CHARS.sub("", t).lower()


def detect_lifecycle(text: str) -> str | None:
    """识别显式生命周期短语 → 命令名; 非生命周期自然语言 → None (进理解管道)。"""
    n = _norm(text)
    if not n:
        return None
    for action, phrases in _LIFECYCLE_PHRASES.items():
        if n in phrases:
            return action
    return None


class CanonicalGoldenPath:
    """Application Orchestrator — 唯一 Canonical Conversation Application 入口。

    CLI/API/WebUI 未来都进入本 Orchestrator (表现层不同, 业务同一 Domain/Runtime)。
    """

    def __init__(self, root: str | Any, *, actor: str = "human",
                 semantic: bool = False,
                 interpreter: Callable[..., Any] | None = None,
                 real_executor: bool = False,
                 decomposer: Callable[..., Any] | None = None) -> None:
        self.root = str(root)
        self.actor = actor
        self.semantic = bool(semantic)
        self.real_executor = bool(real_executor)
        self._decomposer = decomposer
        self.conversations = ConversationApplicationService(self.root)
        self.understanding = ProductUnderstandingService(
            self.root, semantic=semantic, interpreter=interpreter)

    def _resolve_decomposer(self) -> Any:
        """拆解器: 注入优先 → semantic=True 时 LLM → None (模板兜底)。"""
        if self._decomposer is not None:
            return self._decomposer
        if self.semantic:
            from factory_console.task_decomposition import build_llm_decomposer
            return build_llm_decomposer()
        return None

    # ------------------------------------------------------------- 生命周期查询
    def create_conversation(self, *, title: str = "新会话") -> dict[str, Any]:
        return self.conversations.create(title=title, created_by=self.actor)

    def describe(self, conversation_id: str) -> str:
        """当前 Golden Path 阶段 → 用户可见下一步提示 (只读派生, 非 Truth)。"""
        if get_conversation(self.root, conversation_id) is None:
            return "会话不存在"
        try:
            st = gp.path_status(self.root, conversation_id)
        except Exception:  # noqa: BLE001 — 阶段派生失败不阻断 (只读展示)
            return "阶段未知"
        if not st.get("fact_count"):
            return "等待产品想法 — 直接说你想要什么。"
        if not st.get("prds"):
            return "持续理解中 — 可以说「整理成 PRD」生成 PRD。"
        drafts = [p for p in st["prds"] if p.get("status") == "draft"]
        if drafts:
            return "PRD 草稿待你确认 — 审阅后回复「就按这个做」。"
        if not st.get("plans"):
            return "PRD 已确认 — 可以说「生成计划」制定开发计划。"
        pend = [p for p in st["plans"] if p.get("status") == "pending"]
        if pend:
            return "开发计划待你确认 — 回复「确认计划」。"
        return "计划已确认 — 可以说「开始做」进入生产执行。"

    def status(self, conversation_id: str) -> dict[str, Any]:
        st = gp.path_status(self.root, conversation_id)
        statement = self.understanding.understanding_statement(conversation_id)
        return {"stage": self.describe(conversation_id), "path": st,
                "understanding": statement}

    # ------------------------------------------------------------- 单回合入口
    def handle(self, conversation_id: str, text: str, *,
               capability_fn: Callable[[dict[str, Any]], dict[str, Any]]
               | None = None,
               task_id: str = "") -> dict[str, Any]:
        """一个用户回合: 显式生命周期命令 → golden_path; 否则 → 理解管道。

        返回 {kind, reply, action, ...}; kind ∈ chat | lifecycle | gate | status。
        """
        if get_conversation(self.root, conversation_id) is None:
            raise ValueError(f"conversation 不存在: {conversation_id}")
        action = detect_lifecycle(text)
        if action is None:
            res = self.understanding.process_user_message(conversation_id, text)
            # ★ 项目属性: 首次理解成功后把会话绑到项目（幂等，失败不阻断 ✓）
            ensure_project_binding(self.root, conversation_id)
            reply = res.get("reply") or ""
            if res.get("question"):
                reply = f"{reply}\n{res['question']}" if reply else res["question"]
            return {
                "kind": "chat",
                "reply": reply.strip(),
                "action": None,
                "stage": self.describe(conversation_id),
                "understanding_version": res.get("understanding_version"),
                "show_understanding": res.get("show_understanding", False),
            }
        if action == "status":
            st = self.status(conversation_id)
            return {
                "kind": "status",
                "reply": f"{st['understanding']}\n\n当前阶段: {st['stage']}",
                "action": "status",
                "detail": st["path"],
            }
        return self._run_lifecycle(conversation_id, action,
                                   capability_fn=capability_fn, task_id=task_id)

    # ------------------------------------------------------------- 生命周期执行
    def run_lifecycle(self, conversation_id: str, action: str, *,
                     capability_fn: Callable[[dict[str, Any]], dict[str, Any]]
                     | None = None,
                     task_id: str = "") -> dict[str, Any]:
        """公开生命周期入口 (CLI handle 与 API 端点共用同一 Application 逻辑)。

        action ∈ _LIFECYCLE_PHRASES (generate_prd/approve_prd/generate_plan/
        approve_plan/execute/status)。未知 action → ValueError。
        """
        if action not in _LIFECYCLE_PHRASES:
            raise ValueError(
                f"未知生命周期动作: {action} (可用: {sorted(_LIFECYCLE_PHRASES)})")
        if action == "status":
            return self.handle(conversation_id, "状态")
        return self._run_lifecycle(conversation_id, action,
                                   capability_fn=capability_fn, task_id=task_id)

    def _run_lifecycle(self, conversation_id: str, action: str, *,
                       capability_fn: Callable[[dict[str, Any]], dict[str, Any]]
                       | None = None,
                       task_id: str = "") -> dict[str, Any]:
        try:
            if action == "generate_prd":
                obj = gp.generate_prd(self.root, conversation_id, actor=self.actor)
                _md = _write_prd_md(self.root, obj, conversation_id)
                _sum = _prd_summary(obj)
                return {
                    "kind": "lifecycle", "action": action,
                    "reply": (f"已生成 PRD {obj['id']} (v{obj.get('version')})。"
                              + (f"\n📄 可审阅文档: {_md}" if _md else "\n（文档写出失败）")
                              + ("\n" + _sum if _sum else "")
                              + f"\n当前阶段: {self.describe(conversation_id)}"),
                }
            if action == "approve_prd":
                obj = self._approve_current_prd(conversation_id)
                return {
                    "kind": "lifecycle", "action": action,
                    "reply": (f"PRD {obj['id']} (v{obj.get('version')}) 已确认。\n"
                              f"当前阶段: {self.describe(conversation_id)}"),
                    "detail": obj,
                }
            if action == "generate_plan":
                obj = gp.generate_plan(self.root, conversation_id,
                                       actor=self.actor,
                                       decompose=True,
                                       decomposer=self._resolve_decomposer())
                n_tasks = len(obj.get("tasks") or [])
                return {
                    "kind": "lifecycle", "action": action,
                    "reply": (f"已生成开发计划 {obj.get('id')} "
                              f"(tasks={n_tasks})。"
                              # ★ 降级必须可见: LLM 分解 3 次失败会静默回落模板
                              #   （只有 5~6 个通用任务），用户此前完全看不出来 ✗
                              + ("" if not obj.get("degraded") else
                                 "\n⚠ 注意: LLM 任务分解未成功，本计划是【模板降级结果】"
                                 "（只有几个通用任务，未经真实需求分析），"
                                 "建议稍后重试「生成计划」。")
                              + f"\n当前阶段: {self.describe(conversation_id)}"),
                    "detail": obj,
                }
            if action == "approve_plan":
                obj = self._approve_current_plan(conversation_id)
                return {
                    "kind": "lifecycle", "action": action,
                    "reply": (f"开发计划 {obj.get('id')} 已确认。\n"
                              f"当前阶段: {self.describe(conversation_id)}"),
                    "detail": obj,
                }
            if action == "execute":
                res = gp.execute_approved(
                    self.root, conversation_id, actor=self.actor,
                    capability_fn=capability_fn, task_id=task_id,
                    real_executor=self.real_executor)
                executed = res.get("executed") or []
                done = sum(1 for e in executed
                           if (e.get("result") or {}).get("state") == "COMPLETED")
                return {
                    "kind": "lifecycle", "action": action,
                    "reply": f"生产执行: {done}/{len(executed)} tasks COMPLETED。",
                    "detail": res,
                }
        except (gp.GoldenPathError, ValueError) as exc:
            return {
                "kind": "gate", "action": action,
                "reply": f"未执行（Gate 拒绝）: {exc}",
                "error": str(exc),
            }
        raise AssertionError(f"未知 lifecycle action: {action}")  # 防御: 枚举封闭

    def plan_tree(self, conversation_id: str) -> dict[str, Any]:
        """当前会话的任务树视图 (最新 pending 或 approved Plan; 无 → exists=False)。

        C1 (post-cut3): 返回 tree_summary 格式 (exists/leaf_count/domains/degraded),
        供 canonical_shell._plan 直接展示。取"最新计划"而非仅 approved —
        pending (已生成未确认) 也可见, 不改变 Gate/status 语义。
        """
        from factory_console import golden_path as _gp
        st = _gp.path_status(self.root, conversation_id)
        plans = st.get("plans") or []
        if not plans:
            return {"exists": False}
        # 最新计划 (path_status 已按创建序; 取最后一个 — pending 或 approved 均可)
        plan = plans[-1]
        return _gp.plan_tree(self.root, plan["id"])

    def _approve_current_prd(self, conversation_id: str) -> dict[str, Any]:
        st = gp.path_status(self.root, conversation_id)
        drafts = [p for p in st.get("prds", []) if p.get("status") == "draft"]
        if not drafts:
            raise gp.GoldenPathError(
                "当前没有可确认的 PRD 草稿 — 先回复「整理成 PRD」生成 PRD。")
        return gp.approve_prd(self.root, conversation_id, drafts[-1]["id"],
                              actor=self.actor)

    def _approve_current_plan(self, conversation_id: str) -> dict[str, Any]:
        st = gp.path_status(self.root, conversation_id)
        pending = [p for p in st.get("plans", []) if p.get("status") == "pending"]
        if not pending:
            raise gp.GoldenPathError(
                "当前没有待确认的开发计划 — 先回复「生成计划」。")
        return gp.approve_plan(self.root, pending[-1]["id"], actor=self.actor)


__all__ = ["CanonicalGoldenPath", "detect_lifecycle"]


# ---------------------------------------------------------------- PRD 可审阅文档
# 治理缺口（Founder 指出）: 会话让人"审阅后回复「就按这个做」"，
# 却【不给任何可审阅的内容】✗ —— PRD 只是 product_truth 里一条 JSON 实体。
# 要人审，就得给人看 ✓（对标 github/spec-kit 的 spec.md）。
_PRD_LABELS = {
    "functional_requirements": "功能需求",
    "non_functional_requirements": "非功能需求",
    "constraints": "约束",
    "out_of_scope": "不做的事",
    "acceptance_criteria": "验收标准",
    "risks": "风险",
}


def _render_prd_md(prd: dict[str, Any]) -> str:
    """PRD 实体 → 可审阅的 markdown 文档。"""
    c = prd.get("content") or {}
    if not isinstance(c, dict):
        c = {}
    ov = c.get("overview") if isinstance(c.get("overview"), dict) else {}
    title = str(c.get("name") or ov.get("name") or prd.get("goal") or "产品需求文档")
    out = [f"# {title}",
           "",
           f"> PRD {prd.get('id', '')} (v{prd.get('version', 1)})"
           f" · 由 AI Factory OS 需求分析生成 · 待你审阅确认",
           ""]
    if ov:
        out += ["## 概述", ""]
        for k, v in ov.items():
            if v:
                out.append(f"- **{k}**: {v}")
        out.append("")

    def _bullets(v: Any) -> list[str]:
        if isinstance(v, list):
            return [f"- {x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)}"
                    for x in v]
        if isinstance(v, dict):
            return [f"- **{k}**: {x}" for k, x in v.items()]
        return [f"- {v}"]

    for key, label in _PRD_LABELS.items():
        v = c.get(key)
        if v:
            out += [f"## {label}", ""] + _bullets(v) + [""]
    # 其余未列出的键也渲染（不漏信息 ✓）
    for k, v in c.items():
        if k in _PRD_LABELS or k == "overview" or not v:
            continue
        out += [f"## {k}", ""] + _bullets(v) + [""]
    out += ["---", "", "_请审阅以上内容。确认无误回复「就按这个做」；"
            "需要修改请直接说明哪里不对。_", ""]
    return "\n".join(out)


def _write_prd_md(root: str | Path, prd: dict[str, Any],
                  conversation_id: str = "") -> str:
    """把 PRD 写进【项目目录】projects/<P-id>/docs/，返回路径。

    为什么（Founder: 产出文档都应该有归宿 ✓）:
      此前所有 PRD 平铺在 ~/.factory/prd/ ✗ —— 没有"项目"这一层归属，
      换个会话就找不到同一个项目的东西 ✗。
    回落: 未能确定项目 → 写回旧的 <root>/prd/（行为不变，不阻断 ✓）。
    """
    try:
        project_id = (ensure_project_binding(root, conversation_id)
                      if conversation_id else "")
        d = (Path(root) / "projects" / project_id / "docs") if project_id \
            else (Path(root) / "prd")
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"{prd.get('id', 'PRD')}.md"
        f.write_text(_render_prd_md(prd), encoding="utf-8")
        return str(f)
    except Exception:  # noqa: BLE001
        return ""


def _prd_summary(prd: dict[str, Any], limit: int = 5) -> str:
    """给会话回复用的简短摘要（正文在文件里，这里只给要点 ✓）。"""
    c = prd.get("content") or {}
    c = c if isinstance(c, dict) else {}
    ov = c.get("overview") if isinstance(c.get("overview"), dict) else {}
    bits = []
    if ov.get("problem"):
        bits.append(f"  目标: {str(ov['problem'])[:70]}")
    fr = c.get("functional_requirements")
    if isinstance(fr, list) and fr:
        bits.append(f"  功能需求 {len(fr)} 条:")
        for x in fr[:limit]:
            bits.append(f"    · {str(x)[:66]}")
        if len(fr) > limit:
            bits.append(f"    … 另有 {len(fr) - limit} 条（见文档）")
    return "\n".join(bits)


# ------------------------------------------------------------------ 项目归属
def ensure_project_binding(root: str | Path, conversation_id: str) -> str:
    """把会话绑到项目（幂等）: 有 project_id 直接返回；无则按理解出的目标建项目并回写。

    为什么（Founder 指出）: 会话/需求/文档/沙箱都该有【项目属性】✓，
    此前会话记录里连 project_id 字段都没有 ✗ → 换个会话就找不到同一个项目的东西。
    失败安全: 任何异常只打 stderr，不阻断会话主链 ✓。
    """
    try:
        from factory_console import product_understanding as pu

        # ★ 必须用 _load_conv（原始记录含 understanding）；
        #   get_conversation 是过滤后的公开视图，不含 facts ✗（我第一版踩过）
        conv = pu._load_conv(root, conversation_id)
        if not conv:
            return ""
        pid = str(conv.get("project_id") or "")
        if pid:
            return pid
        und = conv.get("understanding") or {}
        facts = und.get("facts") if isinstance(und, dict) else {}
        seq = list(facts.values()) if isinstance(facts, dict) else list(facts or [])
        goal = ""
        for f in seq:
            if isinstance(f, dict) and str(f.get("type", "")).upper() in ("IDEA", "REQUIREMENT"):
                goal = str(f.get("content") or "").strip()[:80]
                if goal:
                    break
        if not goal:
            return ""                       # 还没理解出目标 → 下次再说 ✓
        # ★ 不走 po.create_project(source_conv_id=…) —— 它内部 extract_requirement
        #   会把 conv 当【实体】查 ✗，而会话存在 conversations/ 不在实体库
        #   → NOT_FOUND: entity conv-xxx ✗（实测踩到）。这里直接用实体 API ✓
        from factory_console.unified_contract import create_entity, store_entity
        proj = create_entity("project", created_by="system", parent_id="")
        proj["title"] = goal
        proj["source_conversation_id"] = conversation_id
        proj["status"] = "ACTIVE"
        store_entity(root, proj)
        doc = pu._load_conv(root, conversation_id) or {}
        doc["project_id"] = str(proj.get("id") or "")
        pu._save_conv(root, conversation_id, doc)
        return str(doc["project_id"])
    except Exception as exc:  # noqa: BLE001 — 失败不阻断会话 ✓ 但必须可见
        import sys as _s
        print(f"[project] 会话→项目绑定失败: {exc}", file=_s.stderr)
        return ""
