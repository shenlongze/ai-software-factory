"""factory-console/session/decomposer.py — 递归原子拆解引擎 (M3a, S10-090)。

把复合任务递归拆解到**原子叶子任务**（单 Agent / 单文件单工具 / 可验证 /
≤10min）——"拆到不能拆" = 直接提高执行成功率（§3.7.4: "一步一个坑"根因
= 任务粒度太粗，Agent 一次做不完 → 失败）。

- 原子判定四条件（§3.7.3）: 确定性优先 + LLM 注入点辅助（llm_fn 可选）
- 拆分单向推进 _split_mode: root → features → technical → final（防同层
  反复拆死循环）；final 层仍不原子 → unverified 诚实标注（能力边界，不伪造）
- 递归深度上限 _max_depth=5 + 任务数上限 _max_tasks=64（防爆炸）
- 递归前 cycle_detect 成环拒绝 → DECOMPOSE_CYCLE_REJECTED 审计事件
- 失败安全铁律: LLM 失败/无 LLM → 确定性拆分非空 + atomic(unverified)
  诚实标注；任何异常 → 返回部分结果 + 明确 error
- 输出: DecomposeResult {leaves, tree, state, error} + 落盘
  projects/<slug>/decomposition.json（可追溯）
- 审计: DECOMPOSE_STARTED / DECOMPOSE_ATOMIC / DECOMPOSE_SPLIT /
  DECOMPOSE_CYCLE_REJECTED / DECOMPOSE_COMPLETED（AuditEmitter）

设计: docs/sprint10/S10-090-m3a-atomic-decomposition-plan.md
边界:
- 纯标准库（json/pathlib/dataclasses/re），零新依赖
- 不做 M3-2 关键路径 / M3-3 并行调度 / M3-4 动态分配 / 质量评估
- 非叶子节点编排 Loop 仅接口/事件占位（委派执行在 M3b+）
- 向后兼容: 旧 TaskTree/FeatureTaskGenerator 流程不破坏（引擎独立，可开关）
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

#: 递归深度上限（可配置覆盖）
DEFAULT_MAX_DEPTH = 5
#: 递归任务总数上限（防爆炸）
DEFAULT_MAX_TASKS = 64

#: 语言 → 验证命令模板（原子判定条件③：可验证）
LANG_VERIFY_CMD: dict[str, str] = {
    "py": "pytest {file}",
    "js": "npm test -- {file}",
    "ts": "npm test -- {file}",
    "tsx": "npm test -- {file}",
    "jsx": "npm test -- {file}",
    "go": "go test {file}",
    "rs": "cargo test {file}",
    "dart": "flutter test {file}",
    "java": "mvn test -Dtest={file}",
    "kt": "gradle test --tests {file}",
    "rb": "ruby -c {file}",
    "sh": "bash -n {file}",
    "sql": "sqlfluff lint {file}",
    "md": "markdownlint {file}",
    "json": "python -m json.tool {file}",
    "yaml": "python -c \"import yaml,sys;yaml.safe_load(open('{file}'))\"",
    "yml": "python -c \"import yaml,sys;yaml.safe_load(open('{file}'))\"",
    "toml": "python -c \"import tomllib;tomllib.load(open('{file}','rb'))\"",
    "html": "html5validator {file}",
    "css": "stylelint {file}",
    "vue": "npm test -- {file}",
}

#: 复合关键词（启发式 → 估计工作量 > 10min → 非原子）
COMPLEX_KEYWORDS = (
    "重构", "大规模", "复杂", "整套", "全部", "全面", "架构",
    "迁移", "重写", "性能优化", "分布式", "微服务", "模块化",
)
#: 简单关键词（启发式 → 估计工作量 ≤ 10min）
SIMPLE_KEYWORDS = ("修复", "简单", "小", "调整", "补充", "修改", "改", "加", "删")

#: 文件名/路径提取（原子判定条件②：单文件）
_FILE_RE = re.compile(
    r"[\w./\\-]+\.(?:py|js|ts|tsx|jsx|go|rs|dart|java|kt|rb|php|c|h|cpp|hpp|cs|sh|sql|md|json|yaml|yml|toml|html|css|scss|vue)",
    re.IGNORECASE,
)

#: 确定性拆分的技术层（对齐 TaskTree 语义）: (id, 名称, agent_type, 目标文件模板)
BASE_TECHNICAL_TASKS: tuple[tuple[str, str, str], ...] = (
    ("db", "数据库", "database"),
    ("api", "后端接口", "backend"),
    ("frontend", "前端页面", "frontend"),
    ("test", "测试", "qa"),
)


def _slugify(text: str) -> str:
    """文本 → 文件 slug（中文/空格 → 下划线小写，保留字母数字）。"""
    slug = re.sub(r"[^a-zA-Z0-9_\-]+", "_", str(text)).strip("_").lower()
    return slug or "task"


@dataclass
class DecomposeResult:
    """拆解结果: 原子叶子 + 层级树 + 状态（落盘用）。"""

    leaves: list[dict[str, Any]] = field(default_factory=list)
    tree: list[dict[str, Any]] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "leaves": self.leaves,
            "tree": self.tree,
            "state": self.state,
            "error": self.error,
        }


class DecomposeEngine:
    """递归原子拆解引擎（S10-090 M3a）。

    decompose(task, *, product, capabilities, llm_fn) → DecomposeResult
    - task: 复合任务 dict（{id, name, goal, requirement, agent_type?, files?}）
    - product: 产品 dict（core_features/modules 供确定性拆分）
    - capabilities: {agent_type: 候选数} 能力表（M3-4 前可缺省）
    - llm_fn: 可选 LLM 辅助（拆分/判定注入点）; None → 全确定性路径

    拆分单向推进（防死循环）:
      _split_mode "root"   → features 或 需求分段 → 子任务标 "features"
      _split_mode "features" → 技术层（带目标文件）→ 子任务标 "final"
      _split_mode "final"   → 不再拆; 仍不原子 → unverified 诚实标注
    """

    def __init__(
        self,
        workspace: Optional[Any] = None,
        project_id: str = "",
        *,
        max_depth: int = DEFAULT_MAX_DEPTH,
        max_tasks: int = DEFAULT_MAX_TASKS,
        audit: Optional[Any] = None,
        evaluator: Optional[Any] = None,
        evaluate_after: bool = True,
    ) -> None:
        self.workspace = Path(workspace) if workspace is not None else None
        self.project_id = str(project_id or "")
        self.max_depth = max(int(max_depth or DEFAULT_MAX_DEPTH), 1)
        self.max_tasks = max(int(max_tasks or DEFAULT_MAX_TASKS), 1)
        self._audit = audit  # 显式注入（测试隔离）; None → 运行时懒装配
        # M3d: 拆解质量评估器（可注入; 默认 None → 后置评估时懒装配默认实例 = 默认开）
        self._evaluator = evaluator
        self._evaluate_after = bool(evaluate_after)
        self._reset()

    # ------------------------------------------------------------ 状态

    def _reset(self) -> None:
        self._leaves: list[dict[str, Any]] = []
        self._tree: list[dict[str, Any]] = []
        self._seen: set[str] = set()
        self._events: list[str] = []
        self._error: Optional[str] = None
        self._evaluation: Optional[Any] = None  # M3d EvalResult（后置评估）

    def _new_id(self, prefix: str = "task") -> str:
        return f"{prefix}-{uuid.uuid4().hex[:8]}"

    # ------------------------------------------------------------ 审计

    def _emit(self, event_type: str, task_id: str = "", **fields: Any) -> None:
        """发射审计事件（失败安全: 审计故障不中断拆解）。"""
        self._events.append(event_type)
        try:
            if self._audit is not None:
                self._audit.emit(event_type, project_id=self.project_id, task_id=task_id, **fields)
                return
            if self.workspace is not None:
                from ..audit.audit_emitter import AuditEmitter

                AuditEmitter(workspace=self.workspace).emit(
                    event_type, project_id=self.project_id, task_id=task_id, **fields
                )
        except Exception:  # noqa: BLE001 — 失败安全铁律
            pass

    # ------------------------------------------------------------ 四条件判定

    @staticmethod
    def extract_files(task: dict[str, Any]) -> list[str]:
        """从任务目标中提取文件路径（条件②单文件的输入，含显式 target_file）。"""
        files: list[str] = []
        explicit = task.get("target_file") or task.get("files")
        if isinstance(explicit, str) and explicit.strip():
            files.append(explicit.strip())
        elif isinstance(explicit, (list, tuple)):
            files.extend(str(f) for f in explicit if str(f).strip())
        text = " ".join(
            str(task.get(k) or "")
            for k in ("goal", "requirement", "name", "target", "description")
        )
        for m in _FILE_RE.findall(text):
            if m not in files:
                files.append(m)
        return files

    def _single_agent_ok(
        self, task: dict[str, Any], capabilities: Optional[dict[str, Any]]
    ) -> tuple[bool, str]:
        """条件① 单 Agent 可执行: 所需 agent_type 候选数 == 1。

        capabilities 缺省/无该类型 → 不阻塞（分配是 M3-4）; 候选 >1 → 复合。
        """
        agent_type = str(task.get("agent_type") or "").strip()
        if not agent_type:
            return False, "未指定 agent_type（需拆分到单一角色）"
        if not capabilities:
            return True, agent_type
        cands = capabilities.get(agent_type)
        if cands is None:
            return True, agent_type
        if isinstance(cands, (list, set, tuple)):
            n = len(cands)
        else:
            n = int(cands)
        if n != 1:
            return False, f"agent_type={agent_type} 候选数={n}（>1 需进一步拆分）"
        return True, agent_type

    def _single_file_ok(self, task: dict[str, Any]) -> tuple[bool, str, list[str]]:
        """条件② 单工具·单文件: 目标明确指向 1 个文件。"""
        files = self.extract_files(task)
        if not files:
            return False, "未明确目标文件（需拆分到单文件）", files
        if len(files) > 1:
            return False, f"涉及 {len(files)} 个文件（需拆分到单文件）", files
        return True, files[0], files

    def _verify_cmd_ok(
        self, files: list[str], explicit: Optional[str] = None
    ) -> tuple[bool, str]:
        """条件③ 可验证: 存在验证命令（语言 → 验证映射 + 显式覆盖）。"""
        if explicit:
            return True, explicit
        if not files:
            return False, "无目标文件 → 无验证命令"
        ext = Path(str(files[0])).suffix.lstrip(".").lower()
        tmpl = LANG_VERIFY_CMD.get(ext)
        if not tmpl:
            return False, f"语言 {ext or '未知'} 无内置验证命令"
        return True, tmpl.format(file=files[0])

    def _est_ok(self, task: dict[str, Any]) -> tuple[bool, int]:
        """条件④ ≤10 分钟: 启发式估计（关键词 + 目标文本长度）。"""
        text = " ".join(str(task.get(k) or "") for k in ("goal", "requirement", "name"))
        if any(k in text for k in COMPLEX_KEYWORDS):
            est = 20
        elif any(k in text for k in SIMPLE_KEYWORDS):
            est = 5
        else:
            est = min(30, max(3, len(text) // 40))
        return est <= 10, est

    def is_atomic(
        self,
        task: dict[str, Any],
        capabilities: Optional[dict[str, Any]] = None,
    ) -> tuple[bool, list[str]]:
        """四条件原子判定（确定性优先）: 全过 = 原子; 任一不过 = 复合。"""
        reasons: list[str] = []
        ok1, r1 = self._single_agent_ok(task, capabilities)
        if not ok1:
            reasons.append(r1)
        ok2, r2, files = self._single_file_ok(task)
        if not ok2:
            reasons.append(r2)
        ok3, r3 = self._verify_cmd_ok(files, explicit=task.get("verify_cmd"))
        if not ok3:
            reasons.append(r3)
        ok4, est = self._est_ok(task)
        if not ok4:
            reasons.append(f"估计 {est}min > 10min")
        return (not reasons), reasons

    # ------------------------------------------------------------ 确定性拆分

    @staticmethod
    def _complex_hint(task: dict[str, Any]) -> str:
        """继承父任务的复杂度语义（如"重构"）→ 子任务不丢失，防伪造原子性。

        "重构用户模块" 若子任务 goal 变成 "实现功能: 用户管理"，复杂度语义
        丢失 → 子任务被误判原子。加 hint 后 → "重构: 用户管理" → est>10 →
        final 层 unverified 诚实标注。
        """
        text = " ".join(
            str(task.get(k) or "") for k in ("goal", "requirement", "name")
        )
        for kw in COMPLEX_KEYWORDS:
            if kw in text:
                return f"{kw}: "
        return ""

    def _split_by_features(
        self, task: dict[str, Any], product: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """拆分① (root 层): 按产品 core_features 切（每个 feature 一个子任务）。"""
        features = product.get("core_features") or product.get("features") or []
        children: list[dict[str, Any]] = []
        for i, feat in enumerate(features):
            name = str(feat.get("name") if isinstance(feat, dict) else feat or "")
            if not name:
                continue
            children.append(
                {
                    "id": f"{task.get('id')}-f{i}",
                    "name": name,
                    "goal": f"{self._complex_hint(task)}实现功能: {name}",
                    "requirement": f"{self._complex_hint(task)}{name} 功能（含数据/接口/页面/测试）",
                    "agent_type": task.get("agent_type") or "",
                    "parent": task.get("id"),
                }
            )
        return children

    def _split_by_sentences(
        self, task: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """拆分② (root 层兜底): 按需求分段切（每段一个子任务）。"""
        text = str(task.get("requirement") or task.get("goal") or task.get("name") or "")
        parts = [p.strip() for p in re.split(r"[。；;，,\n]", text) if p.strip()]
        if len(parts) < 2:
            return []
        children = []
        for i, part in enumerate(parts):
            children.append(
                {
                    "id": f"{task.get('id')}-s{i}",
                    "name": part[:40],
                    "goal": f"{self._complex_hint(task)}{part}",
                    "requirement": f"{self._complex_hint(task)}{part}",
                    "agent_type": task.get("agent_type") or "",
                    "parent": task.get("id"),
                }
            )
        return children

    @staticmethod
    def _target_file(agent_type: str, slug: str, tid: str) -> str:
        """技术层任务的目标文件（确定性: 按 agent_type/层生成，供原子判定②）。"""
        if tid == "db":
            return f"db/schema_{slug}.sql"
        if tid == "api":
            return f"backend/{slug}_api.py"
        if tid == "frontend":
            return f"frontend/{slug}_page.js"
        return f"tests/test_{slug}.py"

    def _split_by_technical_layers(
        self, task: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """拆分③ (features 层): 按技术层切，每个任务带目标文件 → 可原子化。"""
        # slug 优先取 id 后缀（feature 序号, 中文名可区分）; 否则 name 清洗
        tid_suffix = str(task.get("id") or "").rsplit("-", 1)[-1]
        slug = str(task.get("slug") or "")
        if not slug:
            slug = tid_suffix if tid_suffix and tid_suffix != "root" else _slugify(
                str(task.get("name") or task.get("goal") or "task"))
        children: list[dict[str, Any]] = []
        for tid, tname, agent_type in BASE_TECHNICAL_TASKS:
            fname = self._target_file(agent_type, slug, tid)
            ext = Path(fname).suffix.lstrip(".").lower()
            children.append(
                {
                    "id": f"{task.get('id')}-{tid}",
                    "name": f"{tname}: {task.get('name', '')}",
                    "goal": f"{tname}: {task.get('goal', '')}",
                    "requirement": f"{tname} 实现，目标文件 {fname}",
                    "agent_type": agent_type,
                    "parent": task.get("id"),
                    "target_file": fname,
                    "verify_cmd": LANG_VERIFY_CMD.get(ext, "").format(file=fname),
                    "_split_mode": "final",
                }
            )
        return children

    def _split(
        self,
        task: dict[str, Any],
        product: Optional[dict[str, Any]],
        llm_fn: Optional[Callable[..., Any]],
    ) -> list[dict[str, Any]]:
        """拆分分发（单向推进，防死循环）:

        - "root"      → features（有）或需求分段；子任务标 _split_mode="features"
        - "features"  → 技术层（带目标文件）；子任务标 _split_mode="final"
        - "final"     → 不再拆（仍不原子 → unverified 诚实标注）
        - LLM 注入: root 层优先 llm_fn（失败/无 → 确定性）
        """
        product = product or {}
        mode = str(task.get("_split_mode") or "root")

        if mode == "root" and llm_fn is not None:
            try:
                raw = llm_fn(task, product)
                children = self._coerce_children(raw, task)
                if children:
                    return children
            except Exception:  # noqa: BLE001 — LLM 失败 → 确定性兜底
                pass

        if mode == "root":
            children = self._split_by_features(task, product)
            if not children:
                children = self._split_by_sentences(task)
            for c in children:
                c.setdefault("_split_mode", "features")
            return children

        if mode == "features":
            return self._split_by_technical_layers(task)

        # "final" / 未知 → 不再拆（调用方转 unverified）
        return []

    @staticmethod
    def _coerce_children(raw: Any, task: dict[str, Any]) -> list[dict[str, Any]]:
        """LLM 返回值归一 → 子任务; 非法 → 空。

        支持两种形态 (S10-095 结构化升级):
          - 简单 list: [{"name", ...}] / [str]（旧形态, 向后兼容）
          - 结构化 dict: {"tasks": [{id,name,requirement,depends_on,verify_cmd,
            est,risks}], "summary": ...}（M3d LLM 深度拆解, 字段透传）
        """
        if isinstance(raw, dict):
            items = raw.get("tasks")
            if not isinstance(items, list):
                return []
        elif isinstance(raw, list):
            items = raw
        else:
            return []
        children: list[dict[str, Any]] = []
        for i, item in enumerate(items):
            if isinstance(item, dict) and item.get("name"):
                child = dict(item)
                child.setdefault("id", f"{task.get('id')}-llm{i}")
                child.setdefault("goal", item.get("name"))
                child.setdefault("requirement", item.get("requirement") or item.get("goal") or item.get("name"))
                child.setdefault("agent_type", task.get("agent_type") or "")
                child.setdefault("parent", task.get("id"))
                child.setdefault("_split_mode", "final")
                # M3d 结构化字段归一: est → est_minutes（评估器/叶子统一口径）
                if "est" in child and "est_minutes" not in child:
                    try:
                        child["est_minutes"] = int(child["est"])
                    except (TypeError, ValueError):
                        pass
                children.append(child)
            elif isinstance(item, str) and item.strip():
                children.append(
                    {
                        "id": f"{task.get('id')}-llm{i}",
                        "name": item.strip()[:40],
                        "goal": item.strip(),
                        "requirement": item.strip(),
                        "agent_type": task.get("agent_type") or "",
                        "parent": task.get("id"),
                        "_split_mode": "final",
                    }
                )
        return children

    # ------------------------------------------------------------ 递归主体

    def _leaf(self, task: dict[str, Any], *, verified: bool, est: int = 8) -> dict[str, Any]:
        """构造原子叶子（verified=False → unverified 诚实标注，不含内部字段）。"""
        files = self.extract_files(task)
        _ok, verify_cmd = self._verify_cmd_ok(files, explicit=task.get("verify_cmd"))
        leaf = {
            "id": str(task.get("id") or self._new_id()),
            "name": str(task.get("name") or task.get("goal") or "原子任务"),
            "goal": str(task.get("goal") or task.get("requirement") or ""),
            "agent_type": str(task.get("agent_type") or ""),
            "target_file": str(task.get("target_file") or (files[0] if files else "")),
            "verify_cmd": str(task.get("verify_cmd") or verify_cmd or ""),
            "est_minutes": int(task.get("est_minutes") or est),
            "verified": bool(verified),
            "unverified": not bool(verified),
            "parent": str(task.get("parent") or ""),
            "source": "atomic" if verified else "unverified",
        }
        # M3d: LLM 深度拆解字段透传（risks/depends_on 供六维评估; 缺失 → 缺省空）
        risks = task.get("risks")
        if isinstance(risks, (list, tuple)):
            leaf["risks"] = [str(r) for r in risks if str(r).strip()]
        elif isinstance(risks, str) and risks.strip():
            leaf["risks"] = [risks]
        deps = task.get("depends_on")
        if isinstance(deps, str) and deps.strip():
            leaf["depends_on"] = [deps]
        elif isinstance(deps, (list, tuple)):
            leaf["depends_on"] = [str(d) for d in deps if str(d).strip()]
        return leaf

    # ------------------------------------------------------------ M3d 后置评估

    def _run_post_evaluation(
        self,
        task: dict[str, Any],
        product: dict[str, Any],
        capabilities: Optional[dict[str, Any]],
        llm_fn: Optional[Callable[..., Any]],
    ) -> None:
        """M3d 后置质量评估（S10-095 §3/§4/§5; 失败安全, 不中断拆解）。

        decompose() 产出 leaves 后 → DecompositionEvaluator.evaluate() →
        四档行动:
          - adopt  (≥0.9)     → 采用当前 leaves
          - adjust (0.7-0.9)  → evaluator.adjust() 自动修正（补 feature /
            补 verify / 修剪环）→ 修正后采用（adjusted 标注）; 修正仍 <0.7
            → 回退确定性（诚实）
          - reject (<0.7)     → 回退确定性技术层模板（诚实降级, 不伪造 LLM 质量）
          - ask_user (<0.5)   → 引擎无 REPL 问询 → 确定性兜底 + questions 记录
            （REPL 层处理后重评）
        审计: EVAL_COMPLETED（每次评估）+ EVAL_REJECTED_FALLBACK（回退时）;
        落盘: evaluation 进 decomposition.json state + evidence 证据包。
        """
        if not self._evaluate_after:
            return
        try:
            from .decomposition_evaluator import DecompositionEvaluator  # 延迟导入

            if self._evaluator is None:
                self._evaluator = DecompositionEvaluator(
                    audit=self._audit,
                    workspace=self.workspace,
                    project_id=self.project_id,
                )
            context = {"capabilities": capabilities, "product": product}
            decomposition = {"tasks": list(self._leaves)}
            result = self._evaluator.evaluate(decomposition, task, context)

            if result.decision == "adjust":
                adjusted, adj_result = self._evaluator.adjust(decomposition, task, context)
                self._evaluation = adj_result
                if adj_result.decision == "adopt":
                    # 修正后采用（adjusted 标注; 依赖环修剪后 leaves 同步）
                    self._leaves = list(adjusted["tasks"])
                else:
                    # 修正仍 <0.7 → 诚实回退确定性模板
                    self._fallback_deterministic(task, product, capabilities)
                    self._emit_eval("EVAL_REJECTED_FALLBACK", adj_result)
                self._emit_eval("EVAL_COMPLETED", adj_result)
                self._sync_tree_from_leaves()
            else:
                self._evaluation = result
                self._emit_eval("EVAL_COMPLETED", result)
                if result.decision == "reject" and llm_fn is not None:
                    self._fallback_deterministic(task, product, capabilities)
                    self._emit_eval("EVAL_REJECTED_FALLBACK", result)
                elif result.decision == "ask_user" and llm_fn is not None:
                    # 引擎无问询能力 → 确定性兜底（不产出 <0.5 拆解）;
                    # questions 留在 evaluation 供 REPL 层重评
                    self._fallback_deterministic(task, product, capabilities)
            self._save_evaluation_evidence()
        except Exception as exc:  # noqa: BLE001 — 失败安全: 评估故障不中断拆解
            self._error = self._error or f"拆解质量评估失败: {exc}"

    def _emit_eval(self, event_type: str, result: Any) -> None:
        """评估审计事件（失败安全; 事件名同步进 state.events）。"""
        self._events.append(event_type)
        try:
            if self._evaluator is not None:
                self._evaluator.emit(
                    event_type, result, task_id=str(self.project_id or "")
                )
        except Exception:  # noqa: BLE001 — 失败安全铁律
            pass

    def _fallback_deterministic(
        self,
        task: dict[str, Any],
        product: dict[str, Any],
        capabilities: Optional[dict[str, Any]],
    ) -> None:
        """回退确定性技术层模板（无 LLM 重跑 _walk; 诚实降级, 不伪造）。"""
        self._leaves = []
        self._tree = []
        self._seen = set()
        try:
            self._walk(task, product, capabilities, None, 0, [])
        except Exception as exc:  # noqa: BLE001 — 失败安全: 回退异常不抛
            self._error = self._error or str(exc)

    def _sync_tree_from_leaves(self) -> None:
        """adjust 替换 leaves 后同步 tree 原子节点（无新 id → 跳过, 防重）。"""
        tree_ids = {str(n.get("id")) for n in self._tree}
        for lf in self._leaves:
            if lf["id"] not in tree_ids:
                self._tree.append(
                    {
                        "id": lf["id"],
                        "name": lf.get("name", ""),
                        "type": "atomic",
                        "parent": lf.get("parent") or "",
                        "children": [],
                        "verified": bool(lf.get("verified", False)),
                        "depth": 0,
                    }
                )

    def _save_evaluation_evidence(self) -> None:
        """evaluation 落盘进 evidence 证据包（失败安全 → None）。"""
        if self._evaluation is None or self.workspace is None or not self.project_id:
            return
        from .evidence import save_evaluation_evidence

        save_evaluation_evidence(
            self.workspace,
            self.project_id,
            project_id=self.project_id,
            task_id=self.project_id,
            evaluation=self._evaluation.to_dict(),
        )

    def decompose(
        self,
        task: dict[str, Any],
        *,
        product: Optional[Any] = None,
        capabilities: Optional[dict[str, Any]] = None,
        llm_fn: Optional[Callable[..., Any]] = None,
        depth: int = 0,
        ancestors: Optional[list[str]] = None,
    ) -> DecomposeResult:
        """递归拆解入口: 复合任务 → 原子叶子（每次调用重置状态）。

        失败安全: 任何异常 → 返回已产出的部分结果 + 明确 error（不抛）。
        """
        self._reset()
        task_id = str(task.get("id") or "task-root")
        self._emit("DECOMPOSE_STARTED", task_id=task_id, task_name=str(task.get("name") or ""))
        try:
            product_dict = self._product_dict(product)
            self._walk(task, product_dict, capabilities, llm_fn, depth, list(ancestors or []))
            # M3d: 后置质量评估（可注入, 默认开; 失败安全: 评估故障不中断拆解）
            self._run_post_evaluation(task, product_dict, capabilities, llm_fn)
        except Exception as exc:  # noqa: BLE001 — 失败安全: 部分结果 + error
            self._error = str(exc)
        finally:
            self._emit(
                "DECOMPOSE_COMPLETED",
                task_id=task_id,
                leaf_count=len(self._leaves),
                tree_count=len(self._tree),
            )
            self._save_state()
        return DecomposeResult(
            leaves=self._leaves,
            tree=self._tree,
            state=self._state_dict(),
            error=self._error,
        )

    def _walk(
        self,
        task: dict[str, Any],
        product: dict[str, Any],
        capabilities: Optional[dict[str, Any]],
        llm_fn: Optional[Callable[..., Any]],
        depth: int,
        ancestors: list[str],
    ) -> dict[str, Any]:
        """递归核心: 环检测 → 原子判定 → 叶子 | 拆分递归。"""
        task = dict(task)
        task.setdefault("id", self._new_id())
        task_id = str(task["id"])

        # 环检测（祖先链成环 → 拒绝 + 审计事件）
        if task_id in ancestors:
            self._emit(
                "DECOMPOSE_CYCLE_REJECTED",
                task_id=task_id,
                ancestor=str(ancestors[-1] if ancestors else ""),
                reason="cyclic dependency",
            )
            self._error = self._error or f"环检测拒绝: {task_id} 出现在祖先链"
            leaf = self._leaf(task, verified=False)
            leaf["cycle_rejected"] = True
            leaf["depth"] = depth
            self._register(leaf, task, depth=depth, is_leaf=True)
            return leaf

        # 深度/任务数上限 → unverified 原子（诚实标注, 不伪造原子性）
        if depth >= self.max_depth or len(self._seen) >= self.max_tasks:
            leaf = self._leaf(task, verified=False, est=30)
            leaf["depth_cap"] = depth >= self.max_depth
            leaf["task_cap"] = len(self._seen) >= self.max_tasks
            leaf["depth"] = depth
            self._emit("DECOMPOSE_ATOMIC", task_id=task_id, verified=False, reason="cap")
            self._register(leaf, task, depth=depth, is_leaf=True)
            return leaf

        # 原子判定
        ok, reasons = self.is_atomic(task, capabilities)
        if ok:
            _ok, est = self._est_ok(task)
            leaf = self._leaf(task, verified=True, est=est)
            leaf["depth"] = depth
            self._emit("DECOMPOSE_ATOMIC", task_id=task_id, verified=True)
            self._register(leaf, task, depth=depth, is_leaf=True)
            return leaf

        # 复合 → 拆分 → 递归
        children = self._split(task, product, llm_fn)
        if not children:
            # 无法/不再拆分 → unverified 原子（诚实: 能力边界，不假装原子）
            _ok, est = self._est_ok(task)
            leaf = self._leaf(task, verified=False, est=est)
            leaf["depth"] = depth
            leaf["unsplittable"] = True
            self._emit("DECOMPOSE_ATOMIC", task_id=task_id, verified=False, reason="unsplittable")
            self._register(leaf, task, depth=depth, is_leaf=True)
            return leaf

        self._emit(
            "DECOMPOSE_SPLIT",
            task_id=task_id,
            child_count=len(children),
            reasons=reasons,
        )
        node: dict[str, Any] = {
            "id": task_id,
            "name": str(task.get("name") or task.get("goal") or "复合任务"),
            "type": "compound",
            "parent": str(task.get("parent") or ""),
            "children": [str(c.get("id") or "") for c in children],
            "depth": depth,
        }
        self._tree.append(node)
        self._seen.add(task_id)
        for child in children:
            self._walk(child, product, capabilities, llm_fn, depth + 1, ancestors + [task_id])
        return node

    def _register(
        self, leaf: dict[str, Any], task: dict[str, Any], *, depth: int, is_leaf: bool
    ) -> None:
        """登记叶子 + 树节点（id 唯一防重）。"""
        if leaf["id"] in self._seen:
            return
        self._seen.add(leaf["id"])
        self._leaves.append(leaf)
        self._tree.append(
            {
                "id": leaf["id"],
                "name": leaf.get("name", ""),
                "type": "atomic",
                "parent": leaf.get("parent") or task.get("parent") or "",
                "children": [],
                "verified": bool(leaf.get("verified", False)),
                "depth": depth,
            }
        )

    # ------------------------------------------------------------ 落盘

    def _state_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "leaves": self._leaves,
            "tree": self._tree,
            "events": self._events,
            "error": self._error,
            "evaluation": self._evaluation.to_dict() if self._evaluation is not None else None,
            "stats": {
                "depth_cap": self.max_depth,
                "task_cap": self.max_tasks,
                "total_nodes": len(self._tree),
                "leaf_count": len(self._leaves),
                "atomic_verified": sum(1 for lf in self._leaves if lf.get("verified")),
                "unverified": sum(1 for lf in self._leaves if lf.get("unverified")),
            },
        }

    def _save_state(self) -> Optional[Path]:
        """落盘 projects/<slug>/decomposition.json（失败安全: 不抛）。"""
        try:
            if self.workspace is None or not self.project_id:
                return None
            project_dir = self.workspace / "projects" / self.project_id
            project_dir.mkdir(parents=True, exist_ok=True)
            out = project_dir / "decomposition.json"
            out.write_text(
                json.dumps(self._state_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return out
        except Exception:  # noqa: BLE001 — 失败安全: 落盘故障不中断
            return None

    # ------------------------------------------------------------ 工具

    @staticmethod
    def _product_dict(product: Any) -> dict[str, Any]:
        if product is None:
            return {}
        if isinstance(product, dict):
            return product
        if hasattr(product, "to_dict"):
            try:
                return product.to_dict() or {}
            except Exception:  # noqa: BLE001
                pass
        try:
            return {
                k: getattr(product, k)
                for k in ("core_features", "features", "modules", "name")
                if hasattr(product, k)
            }
        except Exception:  # noqa: BLE001
            return {}
