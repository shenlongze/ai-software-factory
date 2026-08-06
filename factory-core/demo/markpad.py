"""factory-core/demo/markpad.py — `factory demo markpad` 演示编排 (Phase 13A)。

设计 (KISS, Core 零修改):
- 演示 = 调用链, 不是新架构: 复用 ProductService / ProductGenerator /
  ProductLifecycleEngine / Core TaskStore 既有 API (只调用, 零修改)。
- 临时工厂根: tempfile.mkdtemp (不依赖 /tmp 固定路径; macOS 下 $TMPDIR 为
  /var/folders/...); 默认退出清理, --keep-root 保留供人工检视。
- Mock Provider (同 Phase 12B real-world-validation 模式): MockSelector +
  MockAdapter 只用于生成内容 (research/prd/ui); 生命周期/审批/决策/
  Task/经验全部走真实逻辑。
- 事件捕获: 每个动作 (advance/generate/approve) 后对 EventStore 做 seq 差集,
  阶段日志携带该动作产生的事件列表 (Artifact/Event/Decision 三要素)。
- Removal Isolation: 本模块只被 cli.commands.cmd_demo_markpad 延迟导入;
  删除 demo/ 不影响 CLI 加载。
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from cli.context import FactoryContext
from events.logger import EventLogger
from events.store import EventStore
from providers.models import ProviderRequest, ProviderResponse
from providers.selector import Recommendation
from product.experience import ExperienceStore
from product.generation import ProductGenerator
from product.lifecycle import ProductLifecycleEngine
from product.service import ProductService
from product.store import ProductStore
from tasks.store import TaskStore

#: 演示名 (CLI --json 出口与测试断言共用)
DEMO_NAME = "markpad"

#: 阶段链 (software_project 模板 8 阶段; 与 expected-flow.md 对齐)
STAGE_NAMES = [
    "idea",
    "research",
    "prd",
    "approval(prd)",
    "ui",
    "approval(ui)",
    "architecture",
    "task",
]


class DemoError(Exception):
    """演示失败 (输入缺失/编排失败; CLI 映射 → 退出码 1)。"""


def default_demo_dir() -> Path:
    """examples/markpad-demo 默认目录 (editable install 下源码布局可解析)。"""
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / "examples" / "markpad-demo"


# ------------------------------------------------------------------ Mock Provider (Phase 12B 模式)

#: 生成内容模板 (Mock 只生成内容, 不参与任何决策; ${title} 由 adapter 替换)
_MOCK_CONTENT: dict[str, str] = {
    "research": (
        "## MarkPad 表格编辑器市场研究\n"
        "- 目标用户: PC 端 Markdown 笔记用户 (Typora-like 编辑体验)\n"
        "- 竞品: Typora (逐格编辑 + Tab 导航), Notion (块级表格)\n"
        "- 机会: MarkPad 表格仅整表编辑, 逐格编辑/内联编辑体验缺失\n"
        "- 结论: 逐格编辑 + Tab 导航是笔记类编辑器基础能力, 应补齐 (${title})"
    ),
    "prd": (
        "## PRD — ${title}\n"
        "### 问题\n"
        "表格仅整表编辑 (源码模式), 单元格级编辑缺失, 与正文编辑体验割裂。\n"
        "### 目标\n"
        "- 单元格逐格编辑 (cell-edit)\n"
        "- Tab 键单元格导航 (tab-nav)\n"
        "- 内联编辑, Typora 极简风格 (inline-edit / typora-minimal)\n"
        "### 用户\n"
        "PC 笔记用户, 高频使用表格记录结构化内容。\n"
        "### 功能\n"
        "1. 点击单元格进入内联编辑态\n"
        "2. Tab/Shift+Tab 单元格间导航, Enter 提交\n"
        "3. 保持 GFM markdown 语法兼容\n"
        "### 指标\n"
        "- 表格编辑操作耗时下降 ≥50%\n"
        "- 无回归: 既有表格文档零破坏"
    ),
    "ui": (
        "## UI 设计 — ${title}\n"
        "### 方向\n"
        "Typora 极简风格: 无工具栏, 纯键盘 + 内联光标交互。\n"
        "### 流程\n"
        "表格行内点击 → 单元格进入内联编辑态 (无边框高亮) → Tab 导航 →\n"
        "Enter 提交 / Esc 取消。\n"
        "### 原型\n"
        "| 单元格 A (编辑中) | 单元格 B | 单元格 C |\n"
        "| --- | --- | --- |\n"
        "| 焦点边框高亮 | Tab 进入 | Shift+Tab 回退 |\n"
        "### 约束\n"
        "不引入重型表格框架; 交互与正文编辑一致 (typora-minimal)。"
    ),
}


class MockSelector:
    """CostAwareSelector 测试替身 (demo): 固定推荐 mock provider。

    契约 (product.generation._select): recommend(requirement, *, explicit=None)
    → Recommendation (provider_id/score/reasons/estimated_cost)。
    """

    def __init__(self, provider_id: str = "mock") -> None:
        self._provider_id = provider_id

    def recommend(self, requirement, *, explicit=None, **kw) -> Recommendation:
        return Recommendation(
            provider_id=explicit or self._provider_id,
            score=0.9,
            reasons=["mock recommendation (demo, Phase 12B pattern)"],
            estimated_cost=0.01,
        )


class MockAdapter:
    """ProviderAdapter 测试替身 (demo): 按 artifact_type 返回模板内容。

    契约 (providers/provider.py): generate 返回 ProviderResponse (ok/usage),
    不抛异常; chat/stream 桩实现 (generation 不使用)。
    """

    PROVIDER_ID = "mock"
    PROVIDER_TYPE = "local"

    def __init__(self, idea) -> None:
        self._idea = idea

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        artifact_type = (request.metadata or {}).get("artifact_type", "research")
        content = _MOCK_CONTENT.get(artifact_type, _MOCK_CONTENT["research"])
        return ProviderResponse(
            provider_id=self.PROVIDER_ID,
            content=content.replace("${title}", self._idea.title),
            model="mock-model",
            usage={"prompt_tokens": 40, "completion_tokens": 120},
        )

    def chat(self, request: ProviderRequest) -> ProviderResponse:  # 契约桩
        return self.generate(request)

    def stream(self, request: ProviderRequest):  # 契约桩
        yield self.generate(request)


# ------------------------------------------------------------------ 事件捕获 (seq 差集)


def _seen_seqs(logger: EventLogger) -> set[int]:
    return {e.seq for e in logger.store.query()}


def _delta_events(logger: EventLogger, prev: set[int]) -> list[dict[str, Any]]:
    """自上次快照以来新增事件 (seq 升序, 阶段日志的 Event 三要素之一)。"""
    events = [e for e in logger.store.query() if e.seq not in prev]
    return [
        {"seq": e.seq, "type": e.type.value, "action": e.action, "result": e.result}
        for e in sorted(events, key=lambda e: e.seq)
    ]


def _artifact_of(service: ProductService, idea_id: str, artifact_type: str):
    """idea 下指定类型的最新版本 Artifact (None → 缺)。"""
    candidates = [
        a for a in service.list_artifacts(artifact_type)
        if isinstance(a.content, dict) and a.content.get("idea_id") == idea_id
    ]
    return max(candidates, key=lambda a: a.version) if candidates else None


# ------------------------------------------------------------------ 编排


def _decide_pending(
    engine: ProductLifecycleEngine,
    service: ProductService,
    idea_id: str,
    approver: str,
    comment: str,
):
    """审批当前 pending 请求 (真实 9c 状态机) + 生命周期联动推进。"""
    snapshot = engine.status(idea_id)
    pending = snapshot.get("pending_approval")
    if pending is None:
        raise DemoError(f"expected a pending approval for idea {idea_id}, got none")
    request, _, _ = service.decide_approval(
        pending["id"], "approved", by=approver, comment=comment,
    )
    engine.handle_approval_outcome(idea_id)
    return request


def _log_step(
    logs: list[dict[str, Any]],
    stage: str,
    action: str,
    *,
    artifact=None,
    approval=None,
    events: list[dict[str, Any]],
) -> None:
    logs.append({
        "stage": stage,
        "action": action,
        "artifact": artifact.to_dict() if artifact is not None else None,
        "approval": approval.to_dict() if approval is not None else None,
        "events": events,
    })


def run_markpad_demo(
    *,
    demo_dir: str | Path | None = None,
    approver: str = "shenlongze",
    keep_root: bool = False,
) -> dict[str, Any]:
    """跑完整 MarkPad 演示生命周期, 返回 JSON 友好结果 dict。

    Args:
        demo_dir: idea.json/requirements.json 目录 (默认 examples/markpad-demo)。
        approver: 人工审批人 (demo 自动批准, 生命周期/审批逻辑真实)。
        keep_root: True 保留临时工厂根 (默认退出清理; 禁 /tmp 固定路径)。

    Returns:
        结果 dict (CLI --json 出口 / 测试断言共用): idea / lifecycle /
        stages (8 阶段日志) / artifacts / decisions / tasks / approvals /
        experiences / approval_experiences / events_count / root。

    Raises:
        DemoError: 输入缺失或编排失败 (CLI 映射 → 退出码 1)。
    """
    demo_path = Path(demo_dir) if demo_dir is not None else default_demo_dir()
    try:
        idea_spec = json.loads((demo_path / "idea.json").read_text(encoding="utf-8"))
        req_spec = json.loads((demo_path / "requirements.json").read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DemoError(
            f"demo input missing in {demo_path}: {exc.filename} "
            f"(pass --demo-dir pointing to idea.json/requirements.json)"
        ) from exc
    except json.JSONDecodeError as exc:
        raise DemoError(f"demo input not valid JSON in {demo_path}: {exc}") from exc

    root = Path(tempfile.mkdtemp(prefix="factory-demo-markpad-"))
    try:
        ctx = FactoryContext(root)
        ctx.ensure_dirs()
        store = EventStore(ctx.db_path)
        logger = EventLogger(store)
        try:
            result = _run_with_logger(
                root, logger, idea_spec, req_spec, approver=approver,
            )
        finally:
            store.close()
        result.update({
            "demo": DEMO_NAME,
            "root": str(root),
            "kept": bool(keep_root),
            "approver": approver,
            "exit_code": 0,
        })
        return result
    except Exception as exc:
        if isinstance(exc, DemoError):
            raise
        raise DemoError(f"demo failed: {type(exc).__name__}: {exc}") from exc
    finally:
        if not keep_root:
            shutil.rmtree(root, ignore_errors=True)


def _run_with_logger(
    root: Path,
    logger: EventLogger,
    idea_spec: dict[str, Any],
    req_spec: dict[str, Any],
    *,
    approver: str,
) -> dict[str, Any]:
    """生命周期编排主体 (logger 作用域内执行; 全部真实业务逻辑)。"""
    store = ProductStore(root / "product")
    service = ProductService(store, logger=logger)
    task_store = TaskStore(root / "tasks")
    engine = ProductLifecycleEngine(store, service, task_store=task_store, logger=logger)

    idea = service.create_idea(
        idea_spec["title"],
        description=idea_spec.get("description", ""),
        goals=list(idea_spec.get("goals", [])),
        context={
            "project": req_spec.get("project", "markpad"),
            "task_type": req_spec.get("task_type", "development"),
            "capabilities": list(req_spec.get("capabilities", [])),
            "constraints": list(req_spec.get("constraints", [])),
        },
        created_by="demo",
    )
    generator = ProductGenerator(
        service, logger=logger,
        selector=MockSelector(),
        adapters={"mock": MockAdapter(idea)},
        experience_store=ExperienceStore(root / "product"),
    )

    engine.start_lifecycle(idea.id, by="demo")
    logs: list[dict[str, Any]] = []
    prev = _seen_seqs(logger)

    # [1] idea → research (product_idea Artifact 已随 idea 创建)
    engine.advance(idea.id, by="demo")
    _log_step(
        logs, "idea", "advance",
        artifact=_artifact_of(service, idea.id, "product_idea"),
        events=_delta_events(logger, prev),
    )
    prev = _seen_seqs(logger)

    # [2] research: Mock 生成 + advance → prd
    r_research = generator.generate(idea.id, "research", created_by="demo")
    engine.advance(idea.id, by="demo")
    _log_step(
        logs, "research", "generate", artifact=r_research.artifact,
        events=_delta_events(logger, prev),
    )
    prev = _seen_seqs(logger)

    # [3] prd: Mock 生成 (mandatory 门自动申请审批) + advance → approval(prd)
    r_prd = generator.generate(idea.id, "prd", created_by="demo")
    engine.advance(idea.id, by="demo")
    _log_step(
        logs, "prd", "generate", artifact=r_prd.artifact,
        approval=r_prd.approval_request, events=_delta_events(logger, prev),
    )
    prev = _seen_seqs(logger)

    # [4] approval(prd): 人工批准 (真实 9c 状态机) → 联动推进 → ui
    apr_prd = _decide_pending(engine, service, idea.id, approver, "PRD 合理, 批准 (demo)")
    _log_step(logs, "approval(prd)", "approve", approval=apr_prd, events=_delta_events(logger, prev))
    prev = _seen_seqs(logger)

    # [5] ui: Mock 生成 (mandatory 门自动申请审批) + advance → approval(ui)
    r_ui = generator.generate(idea.id, "ui", created_by="demo")
    engine.advance(idea.id, by="demo")
    _log_step(
        logs, "ui", "generate", artifact=r_ui.artifact,
        approval=r_ui.approval_request, events=_delta_events(logger, prev),
    )
    prev = _seen_seqs(logger)

    # [6] approval(ui): 人工批准 → 联动推进 → architecture
    apr_ui = _decide_pending(engine, service, idea.id, approver, "UI 方向确认 (demo)")
    _log_step(logs, "approval(ui)", "approve", approval=apr_ui, events=_delta_events(logger, prev))
    prev = _seen_seqs(logger)

    # [7] architecture: 决策源产物 (architecture) + advance → 架构决策链 + task
    arch = service.create_artifact(
        "architecture",
        content={
            "idea_id": idea.id,
            "summary": "Flutter/Dart 内联表格编辑器: 单元格组件 + 键盘导航层, "
                       "GFM 语法兼容 (决策源产物, demo)",
        },
        created_by="demo",
        idea_id=idea.id,
    )
    engine.advance(idea.id, by="demo")
    _log_step(logs, "architecture", "advance", artifact=arch, events=_delta_events(logger, prev))
    prev = _seen_seqs(logger)

    # [8] task: advance → task_plan 决策 + Core Task 生成 + lifecycle completed
    lifecycle = engine.advance(idea.id, by="demo")
    _log_step(logs, "task", "advance", events=_delta_events(logger, prev))
    prev = _seen_seqs(logger)

    # Experience Loop (真实记录接口: 正向 + 负向 + 审批经验)
    exp_pos = generator.record_experience(
        r_prd.artifact.id, rating=5, approved=True,
        comment="PRD 结构完整, 评审通过 (demo 正向经验)", by=approver,
    )
    exp_neg = generator.record_experience(
        r_ui.artifact.id, rating=2, approved=False,
        comment="UI 原型信息密度过高, 需精简 (demo 负向信号)", by=approver,
    )
    exp_apr = generator.record_approval_experience(
        r_prd.artifact.id, "approved",
        comment="PRD 合理, 批准", improvement_signal="可增加表格交互细节", by=approver,
    )

    all_events = logger.store.query()
    return {
        "ok": True,
        "idea": idea.to_dict(),
        "lifecycle": {
            "id": lifecycle.id,
            "template": lifecycle.template_name,
            "status": lifecycle.status,
            "completed_at": lifecycle.completed_at,
        },
        "stages": logs,
        "artifacts": [a.to_dict() for a in service.list_artifacts()],
        "decisions": [d.to_dict() for d in store.list_decision_artifacts()],
        "tasks": [t.to_dict() for t in task_store.list()],
        "approvals": [r.to_dict() for r in service.list_approvals()],
        "experiences": [e.to_dict() for e in generator.list_experiences()],
        "approval_experiences": [
            e.to_dict() for e in ExperienceStore(root / "product").list_approval()
        ],
        "events_count": len(all_events),
        "event_types": sorted({e.type.value for e in all_events}),
        "experience_positive": exp_pos.to_dict(),
        "experience_negative": exp_neg.to_dict(),
        "approval_experience": exp_apr.to_dict(),
    }
