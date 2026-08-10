"""factory-console/workflow_runner.py — S10-006.5 P1-A Workflow 启动执行器。

真实 Agent 执行链 (禁 mock): 创建项目后, POST /api/projects/{id}/start 触发
本模块在**后台线程**执行完整链:

    Idea → PM (product-manager) → UX/UI (ui-designer) → Architect (architect)
         → Developer (developer, 真实代码写入沙箱目录) → Tester (tester,
           确定性测试 + DevTestLoop ≤2 修复轮) → Release (devops, zip 构建)

设计 (只组合, 不重写 — 复用 S8-005 已验证模式):
- 阶段执行器全部来自 factory-exec (PMAgent/UXUIDesignerAgent/ArchitectAgent/
  DeveloperAgent/TesterAgent/ReleaseAgent), 真实 LLM 调用 (provider 由
  ConfigProvider 配置: deepseek/openai/ollama → OpenAIProvider 兼容端点,
  anthropic → AnthropicProvider; RecordingProvider 记录 usage/延迟/成本估算)。
- key 进程内注入 (禁明文, S10-007 阶段一): ConfigProvider 解析
  (env > 项目 .env > ~/.factory/config.json > 默认; 支持 env:VAR 引用) →
  进程环境注入 provider 对应变量 (deepseek/openai → OPENAI_API_KEY,
  anthropic → ANTHROPIC_API_KEY, ollama 无 key); 缺失 → WorkflowStartError
  (HTTP 层 503, 诚实失败 — 不假装执行)。不读取任何 ~/.hermes 路径。
- 编排: org WorkflowLifecycle/WorkflowRunner/DevTestLoopRunner (只消费, 零修改
  Core Workflow/Artifact/Approval); org.* 事件经 EventLogger 落库到与 Timeline
  同一 events.db → GET /api/projects/{id}/timeline 直接可见 (真实事件, 非伪造)。
- 产物: ArtifactRegistry 自动注册 (create→generated→VALIDATED), 写入 org
  store; 代码/zip 写入 runs_dir/{project_id}/{run_id}/ 沙箱目录。
- 运行报告: 每阶段完成写 progress JSON (成本/调用数/tokens 实时可见), 整链
  完成/失败写 report JSON (验收断言 + totals)。

并发: 每项目同时只允许一个运行 (模块级 _RUNNING 集合); 重复 start →
WorkflowConflictError (HTTP 层 409, 诚实拒绝)。

测试注入: chain_factory 参数 — 测试传假链 (写 org 事件/产物, 零 LLM), 生产
默认 None → 真实链。run_async=False → 同步执行 (测试可等待断言)。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from .config import get_config

#: LLM provider 配置已移入 factory-console/config.py (PROVIDER_DEFAULTS 映射表)
#: — MODEL/BASE_URL/费率不再硬编码 (S10-007 阶段一: 多 Provider 支持,
#: 不写死 DeepSeek)。消费方一律经 get_config().get_llm() 读取。

#: 仓库根 (sys.path 挂载 factory-core/factory-org/factory-exec)
ROOT = Path(__file__).resolve().parents[1]

_RUNNING_LOCK = threading.Lock()
_RUNNING: set[str] = set()


class WorkflowStartError(Exception):
    """启动失败 (LLM key 缺失/存储不可用) → HTTP 503。"""


class WorkflowConflictError(WorkflowStartError):
    """项目已有运行中的 workflow → HTTP 409 (诚实拒绝重复启动)。"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_llm_key() -> str:
    """LLM API key 解析 + 进程内注入 (ConfigProvider; 禁明文, 不读 ~/.hermes)。

    S10-007 阶段一: 来源链 (config.py 完整语义) — LLM_API_KEY (进程 env >
    项目 .env > ~/.factory/config.json, 支持 env:VAR 引用) → provider 专属
    环境变量 (deepseek → DEEPSEEK_API_KEY 等) → OPENAI_API_KEY (历史 Hermes
    进程环境注入目标, 开发环境向后兼容)。注入目标按 provider 转换:
    deepseek/openai → OPENAI_API_KEY (OpenAI 兼容端点); anthropic →
    ANTHROPIC_API_KEY; ollama → 无 key (本地模型不注入)。
    返回 key (空串 = 缺失)。只写进程环境, 不打印/不落盘明文。
    """
    llm = get_config().get_llm()
    key = llm.get("api_key") or ""
    key_env = llm.get("key_env")
    if key and key_env:
        os.environ[key_env] = key
    return key


def has_llm_key() -> bool:
    """LLM key 可用性 (进程环境已注入 OR 配置可解析; ollama 本地无需 key)。

    向后兼容: 进程环境 OPENAI_API_KEY 仍优先 (Hermes 曾注入的部署形态)。
    其余走 ConfigProvider — 无 ~/.hermes 依赖 (S10-007 P0 解除)。
    """
    if os.environ.get("OPENAI_API_KEY"):
        return True
    llm = get_config().get_llm()
    if llm.get("provider") == "ollama":
        return True  # 本地模型不需要 API key
    return bool(llm.get("api_key"))


def is_project_running(project_id: str) -> bool:
    """项目当前是否有运行中的 workflow (模块级 _RUNNING — run-status 判定用)。"""
    with _RUNNING_LOCK:
        return project_id in _RUNNING


# ------------------------------------------------------------------ 运行报告


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_dirs(runs_dir: Path, project_id: str, run_id: str) -> dict[str, Path]:
    """运行目录布局 (唯一 basename, 每 run 独立沙箱)。"""
    base = runs_dir / project_id / run_id
    return {
        "project_dir": base / "app",
        "dist_dir": base / "dist",
        "progress": base / "progress.json",
        "report": base / "report.json",
    }


def _setup_sys_path() -> None:
    for p in ("factory-core", "factory-org", "factory-exec"):
        path = ROOT / p
        if path.is_dir() and str(path) not in sys.path:
            sys.path.insert(0, str(path))


# ------------------------------------------------------------------ 启动入口


def start_project_workflow(
    *,
    project_id: str,
    idea: str,
    org_dir: str | Path,
    events_db_path: str | Path,
    runs_dir: str | Path,
    chain_factory: Callable[..., dict[str, Any]] | None = None,
    run_async: bool = True,
) -> dict[str, Any]:
    """POST /projects/{id}/start 执行入口: key 校验 → 后台线程启动真实链。

    返回 {status: "started", project_id, run_id, note} — HTTP 层立即回包,
    执行在后台线程 (事件/产物落库后 Timeline 可见)。失败安全:
    - key 缺失 → WorkflowStartError (503)
    - 项目已有运行 → WorkflowConflictError (409)
    """
    if not has_llm_key():
        raise WorkflowStartError(
            "LLM API key unavailable (LLM_API_KEY not configured — 见 "
            "factory-console/.env.example: LLM_PROVIDER/LLM_API_KEY) "
            "— 无法启动真实 Agent 执行"
        )
    # 解析配置 key 并注入 provider 专属环境变量 (仅检查不注入 → 干净环境 provider 读不到)
    load_llm_key()
    run_id = f"R{int(time.time() * 1000)}"
    with _RUNNING_LOCK:
        if project_id in _RUNNING:
            raise WorkflowConflictError(
                f"workflow already running for project {project_id} (等待完成后再试)"
            )
        _RUNNING.add(project_id)

    kwargs = dict(
        project_id=project_id,
        idea=idea,
        run_id=run_id,
        org_dir=Path(org_dir),
        events_db_path=Path(events_db_path),
        runs_dir=Path(runs_dir),
        chain_factory=chain_factory,
    )
    if run_async:
        thread = threading.Thread(
            target=_thread_main,
            kwargs=kwargs,
            daemon=True,
            name=f"wf-{project_id}-{run_id}",
        )
        thread.start()
    else:
        _thread_main(**kwargs)
    return {
        "status": "started",
        "project_id": project_id,
        "run_id": run_id,
        "note": "真实 Agent 执行链已启动 (pm→uxui→architect→developer→tester→release)",
    }


def _thread_main(**kwargs: Any) -> None:
    """后台线程主体: 执行链 + 报告落盘 (异常 → 失败报告, 不拖垮进程)。"""
    project_id: str = kwargs["project_id"]
    run_id: str = kwargs["run_id"]
    runs_dir: Path = kwargs["runs_dir"]
    report_path = _run_dirs(runs_dir, project_id, run_id)["report"]
    try:
        report = run_project_chain(**kwargs)
        report["status"] = "completed"
        report["finished_at"] = _now()  # run-status updated_at 数据源
        _write_json(report_path, report)
    except Exception as exc:  # noqa: BLE001 — 诚实失败报告
        _write_json(
            report_path,
            {
                "status": "failed",
                "project_id": project_id,
                "run_id": run_id,
                "error": f"{type(exc).__name__}: {exc}",
                "finished_at": _now(),
            },
        )
    finally:
        with _RUNNING_LOCK:
            _RUNNING.discard(project_id)


# ------------------------------------------------------------------ 执行链


def run_project_chain(
    *,
    project_id: str,
    idea: str,
    run_id: str,
    org_dir: Path,
    events_db_path: Path,
    runs_dir: Path,
    chain_factory: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """执行链 (生产 = 真实 LLM; 测试 = chain_factory 注入假链)。"""
    _setup_sys_path()
    from events.logger import EventLogger
    from events.store import EventStore
    from org.projects import ProjectStore
    from org.workflow import WorkflowLifecycle

    store = ProjectStore(org_dir)
    event_store = EventStore(events_db_path)
    try:
        logger = EventLogger(event_store)
        wf_lifecycle = WorkflowLifecycle(store, logger=logger)
        if chain_factory is not None:
            return chain_factory(
                wf_lifecycle=wf_lifecycle,
                logger=logger,
                project_id=project_id,
                idea=idea,
                run_id=run_id,
                runs_dir=runs_dir,
            )
        return _real_chain(
            project_id=project_id,
            idea=idea,
            run_id=run_id,
            store=store,
            event_store=event_store,
            logger=logger,
            wf_lifecycle=wf_lifecycle,
            runs_dir=runs_dir,
        )
    finally:
        event_store.close()


def _real_chain(
    *,
    project_id: str,
    idea: str,
    run_id: str,
    store: Any,
    event_store: Any,
    logger: Any,
    wf_lifecycle: Any,
    runs_dir: Path,
) -> dict[str, Any]:
    """真实 6 阶段链 (S8-005 demo_full_chain 复用, 只参数化不重写)。"""
    from org.workflow import DevTestLoopRunner, WorkflowRunner, WorkflowStatus
    from exec.tester import make_workflow_executor

    dirs = _run_dirs(runs_dir, project_id, run_id)
    project_dir = dirs["project_dir"]
    dist_dir = dirs["dist_dir"]

    recorder = Recorder(progress_path=dirs["progress"])
    provider = _build_provider(recorder)
    started = _now()

    # Artifact 链固定 id (run 级唯一 — 防跨 run DuplicateError)
    ids = _run_artifact_ids(project_id, run_id)
    _init_project_dir(project_dir)
    _write_test_suite(project_dir)

    # 1) 设计链 WF-DESIGN: product → ux_ui → design
    wfd, stages_design = _build_design_workflow(wf_lifecycle, project_id, run_id, ids)
    _register_idea(wf_lifecycle, stages_design[0].id, project_id, idea, ids["idea"])
    design_execs = _make_design_executors(provider, recorder, ids)
    design_runner = WorkflowRunner(
        wf_lifecycle, executor=make_workflow_executor(design_execs), logger=logger
    )
    wf1 = design_runner.run(wfd.id)
    if wf1.status != WorkflowStatus.COMPLETED:
        recorder.add_error(
            "WF-DESIGN", f"status={wf1.status.value} reason={wf1.failed_reason}"
        )
        return _finalize(
            recorder, started, wf1.status.value, wf_lifecycle, event_store, ids, project_dir
        )

    # 2) 开发测试发布链 WF-APP: development → testing → release (≤2 修复轮)
    wfa, _stages_app = _build_app_workflow(wf_lifecycle, project_id, run_id, ids)
    app_execs = {
        "developer": _make_dev_executor(
            provider, recorder, ids, project_id, idea, project_dir
        ),
        "tester": _make_tester_executor(provider, recorder, ids),
        "devops": _make_release_executor(
            provider, recorder, ids, project_dir, dist_dir
        ),
    }
    app_runner = DevTestLoopRunner(
        wf_lifecycle,
        executor=make_workflow_executor(app_execs),
        logger=logger,
        max_repair_rounds=2,
    )
    wf2 = app_runner.run(wfa.id)
    if wf2.status != WorkflowStatus.COMPLETED:
        recorder.add_error(
            "WF-APP", f"status={wf2.status.value} reason={wf2.failed_reason}"
        )
    return _finalize(
        recorder, started, wf2.status.value, wf_lifecycle, event_store, ids, project_dir
    )


# ------------------------------------------------------------------ 记录器


class Recorder:
    """阶段/调用/产物/事件集中记录 + 每阶段进度报告 (成本实时可见)。"""

    def __init__(self, progress_path: Path | None = None) -> None:
        self.stages: list[dict[str, Any]] = []
        self.calls: list[dict[str, Any]] = []
        self.artifacts: list[dict[str, Any]] = []
        self.events: dict[str, int] = {}
        self.errors: list[dict[str, Any]] = []
        self.started = time.monotonic()
        self.current_stage: dict[str, Any] | None = None
        self.progress_path = progress_path

    def stage(self, workflow: str, name: str, role: str) -> None:
        self.current_stage = {
            "workflow": workflow,
            "stage": name,
            "role": role,
            "calls": [],
            "cost_usd_est": 0.0,
            "latency_s": 0.0,
            "status": "RUNNING",
        }
        self.stages.append(self.current_stage)

    def stage_done(self, status: str, note: str = "") -> None:
        if self.current_stage is None:
            return
        self.current_stage["status"] = status
        self.current_stage["note"] = note
        self.current_stage = None
        self._write_progress()

    def add_call(self, call: dict[str, Any]) -> None:
        self.calls.append(call)
        if self.current_stage is not None:
            self.current_stage["calls"].append(len(self.calls) - 1)
            self.current_stage["cost_usd_est"] = round(
                self.current_stage["cost_usd_est"] + float(call.get("cost_usd_est") or 0.0), 6
            )
            self.current_stage["latency_s"] = round(
                self.current_stage["latency_s"] + float(call.get("latency_s") or 0.0), 2
            )

    def add_artifact(self, artifact: dict[str, Any]) -> None:
        self.artifacts.append(artifact)

    def add_error(self, where: str, message: Any) -> None:
        self.errors.append({"where": where, "message": str(message)[:2000]})

    def totals(self) -> dict[str, Any]:
        prompt = sum(int(c.get("usage", {}).get("prompt_tokens") or 0) for c in self.calls)
        completion = sum(
            int(c.get("usage", {}).get("completion_tokens") or 0) for c in self.calls
        )
        return {
            "calls": len(self.calls),
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
            "cost_usd_est": round(
                sum(float(c.get("cost_usd_est") or 0.0) for c in self.calls), 6
            ),
            "wall_s": round(time.monotonic() - self.started, 2),
        }

    def _write_progress(self) -> None:
        if self.progress_path is None:
            return
        _write_json(
            self.progress_path,
            {
                "status": "running",
                "stages": self.stages,
                "calls": self.calls,
                "totals": self.totals(),
                "errors": self.errors,
                "updated_at": _now(),
            },
        )


def _build_provider(recorder: Recorder) -> Any:
    """真实 Provider (Recording 包装) — 按配置 provider 选择, 不写死 DeepSeek。

    S10-007 阶段一: model/base_url/费率全来自 ConfigProvider.get_llm()
    (key 已由 load_llm_key 进程内注入到 provider 对应环境变量):
    - deepseek/openai/ollama → OpenAIProvider (OpenAI 兼容端点; ollama 本地
      不校验 Authorization, 用占位 key 满足兼容客户端)
    - anthropic → AnthropicProvider (Messages API)
    """
    llm = get_config().get_llm()
    provider = llm["provider"]
    if provider == "anthropic":
        from exec.providers.anthropic import AnthropicProvider

        inner = AnthropicProvider(model=llm["model"], base_url=llm["base_url"], timeout=300)
    else:
        from exec.providers.openai import OpenAIProvider

        kwargs: dict[str, Any] = {
            "model": llm["model"],
            "base_url": llm["base_url"],
            "timeout": 300,
            "input_rate_per_1k": llm.get("input_rate_per_1k"),
            "output_rate_per_1k": llm.get("output_rate_per_1k"),
        }
        if provider == "ollama":
            kwargs["api_key"] = "ollama"  # 本地占位 (Ollama 不校验 Authorization)
        inner = OpenAIProvider(**kwargs)
    wrapper = _RecordingProvider(inner)
    wrapper.recorder = recorder
    return wrapper


class _RecordingProvider:
    """真实 Provider 包装: 记录每次调用 usage/延迟/估算成本 (同 S8-005)。"""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.recorder: Recorder | None = None

    @property
    def provider_id(self) -> str:
        """记录器标识 (provider 随配置 — S10-007 多 Provider 支持)。"""
        return f"{get_config().get_llm()['provider']}-rec"

    def generate(self, request: Any) -> Any:
        t0 = time.monotonic()
        resp = self._inner.generate(request)
        dt = round(time.monotonic() - t0, 2)
        usage = dict(resp.usage or {})
        call: dict[str, Any] = {
            "model": get_config().get_llm()["model"],
            "max_tokens": request.max_tokens,
            "usage": usage,
            "latency_s": dt,
            "ok": resp.ok,
            "error": resp.error,
            "content_len": len(resp.content or ""),
            "content_head": (resp.content or "")[:300],
            "content_tail": (resp.content or "")[-300:],
            "cost_usd_est": round(float(usage.get("estimated_cost_usd") or 0.0), 6),
        }
        if self.recorder is not None:
            self.recorder.add_call(call)
        return resp


# ------------------------------------------------------------------ org 编排


def _run_artifact_ids(project_id: str, run_id: str) -> dict[str, str]:
    """run 级唯一 Artifact 链 id (跨 workflow 预定义引用; 防跨 run DuplicateError)。"""
    prefix = f"{project_id}-{run_id}"
    return {
        "idea": f"{prefix}-IDEA",
        "product": f"{prefix}-PRODUCT",
        "ux_ui": f"{prefix}-UXUI",
        "design": f"{prefix}-DESIGN",
        "code": f"{prefix}-CODE",
        "test": f"{prefix}-TEST",
        "release": f"{prefix}-RELEASE",
    }


def _build_design_workflow(
    wf_lifecycle: Any, project_id: str, run_id: str, ids: dict[str, str]
) -> tuple[Any, list[Any]]:
    """WF-DESIGN: product → ux_ui → design (线性链, run 级唯一 id)。"""
    wf = wf_lifecycle.create_workflow(
        project_id,
        f"{project_id} 设计链 (product→ux_ui→design) [{run_id}]",
        workflow_id=f"WF-{project_id}-{run_id}-DESIGN",
    )
    s_product = wf_lifecycle.create_stage(
        wf.id, "product-manager", name="product",
        input_artifacts=[ids["idea"]],
        stage_id=f"STG-{project_id}-{run_id}-PRODUCT",
    )
    s_uxui = wf_lifecycle.create_stage(
        wf.id, "ui-designer", name="ux_ui",
        depends_on=[s_product.id], input_artifacts=[ids["product"]],
        stage_id=f"STG-{project_id}-{run_id}-UXUI",
    )
    s_design = wf_lifecycle.create_stage(
        wf.id, "architect", name="design",
        depends_on=[s_uxui.id],
        input_artifacts=[ids["product"], ids["ux_ui"]],
        stage_id=f"STG-{project_id}-{run_id}-DESIGN",
    )
    return wf, [s_product, s_uxui, s_design]


def _build_app_workflow(
    wf_lifecycle: Any, project_id: str, run_id: str, ids: dict[str, str]
) -> tuple[Any, list[Any]]:
    """WF-APP: development → testing → release (DevTestLoopRunner; ≤2 修复轮)。"""
    wf = wf_lifecycle.create_workflow(
        project_id,
        f"{project_id} 开发测试发布链 (development→testing→release) [{run_id}]",
        workflow_id=f"WF-{project_id}-{run_id}-APP",
    )
    s_dev = wf_lifecycle.create_stage(
        wf.id, "developer", name="development",
        input_artifacts=[ids["product"], ids["ux_ui"], ids["design"]],
        stage_id=f"STG-{project_id}-{run_id}-DEV",
    )
    s_test = wf_lifecycle.create_stage(
        wf.id, "tester", name="testing",
        depends_on=[s_dev.id],
        stage_id=f"STG-{project_id}-{run_id}-TEST",
    )
    s_rel = wf_lifecycle.create_stage(
        wf.id, "devops", name="release",
        depends_on=[s_test.id],
        input_artifacts=[ids["code"], ids["test"]],
        stage_id=f"STG-{project_id}-{run_id}-REL",
    )
    return wf, [s_dev, s_test, s_rel]


def _register_idea(
    wf_lifecycle: Any, stage_id: str, project_id: str, idea: str, idea_artifact_id: str
) -> None:
    """idea 产物注册 (create→generated→VALIDATED; 契约失败 → 响亮失败)。"""
    art = wf_lifecycle.registry.create(
        stage_id=stage_id,
        type_="idea",
        project_id=project_id,
        ref="file:///idea.md",
        producer_role="product-manager",
        metadata={"idea": idea},
        artifact_id=idea_artifact_id,
    )
    wf_lifecycle.registry.mark_generated(art.id)
    art, validation = wf_lifecycle.registry.validate(art.id)
    if not validation.ok:
        raise RuntimeError(f"idea artifact contract failed: {validation}")


# ------------------------------------------------------------------ 阶段执行器 (真实 v4-pro)


def _make_design_executors(
    provider: Any, recorder: Recorder, ids: dict[str, str]
) -> dict[str, Callable[[Any, dict[str, Any]], dict[str, Any]]]:
    """PM / UXUI / Architect executor (真实 v4-pro; 固定产物 id)。"""
    from exec.architect import ArchitectAgent, build_arch_executor
    from exec.pm import PMAgent, build_pm_executor
    from exec.uxui import UXUIDesignerAgent, build_uxui_executor

    pm = PMAgent(provider=provider)
    uxui = UXUIDesignerAgent(provider=provider)

    def wrap(name: str, fn: Callable[[Any, dict[str, Any]], dict[str, Any]]):
        def run(stage: Any, context: dict[str, Any]) -> dict[str, Any]:
            recorder.stage("WF-DESIGN", name, stage.role_id)
            try:
                result = fn(stage, context)
                aid = ""
                if isinstance(result, dict):
                    aid = str(result.get("artifact_id") or "")
                recorder.stage_done("COMPLETED", f"artifact={aid}")
                return result
            except Exception as exc:  # noqa: BLE001 — 诚实失败
                recorder.add_error(f"design/{name}", exc)
                recorder.stage_done("FAILED", str(exc))
                raise
        return run

    def arch_run(stage: Any, context: dict[str, Any]) -> dict[str, Any]:
        """Architect: context 双输入 (product + ux_ui) → 构造 → design (S8-003 强校验)。"""
        product = _ctx_artifact(context, "product")
        uxui_art = _ctx_artifact(context, "ux_ui")
        if product is None or uxui_art is None:
            raise RuntimeError(
                "architect needs BOTH product and ux_ui artifacts in context inputs"
            )
        agent = ArchitectAgent(
            provider=provider,
            product=dict(product.get("metadata") or {}),
            ux_ui=dict(uxui_art.get("metadata") or {}),
        )
        return build_arch_executor(agent)(stage, context)

    return {
        "product-manager": _fixed_id(wrap("product", build_pm_executor(pm)), ids["product"]),
        "ui-designer": _fixed_id(wrap("ux_ui", build_uxui_executor(uxui)), ids["ux_ui"]),
        "architect": _fixed_id(wrap("design", arch_run), ids["design"]),
    }


def _make_dev_executor(
    provider: Any,
    recorder: Recorder,
    ids: dict[str, str],
    project_id: str,
    idea: str,
    project_dir: Path,
) -> Callable[[Any, dict[str, Any]], dict[str, Any]]:
    """Developer executor: 真实 v4-pro 生成代码 → git apply → code artifact。"""
    from exec.developer import DeveloperAgent

    dev = DeveloperAgent(provider=provider)
    REQ = (
        "1. 纯前端 HTML/CSS/JS, 零外部依赖 (不引 CDN/框架);\n"
        "2. 打开 index.html 即可使用 (浏览器本地存储 localStorage 持久化);\n"
        f"3. 实现用户需求: {idea}\n"
        "4. JS 语法必须正确 (node --check 验证); index.html 必须引用 style.css 与 app.js。"
    )

    def run(stage: Any, context: dict[str, Any]) -> dict[str, Any]:
        name = getattr(stage, "name", "") or stage.id
        recorder.stage("WF-APP", name, "developer")
        try:
            bugs = [
                inp for inp in context.get("inputs", [])
                if isinstance(inp, dict) and inp.get("type") == "bug_report"
            ]
            if bugs:
                objective = (
                    "修复测试发现的功能缺陷。缺陷报告:\n"
                    + json.dumps(bugs, ensure_ascii=False, indent=2)[:6000]
                )
                extra = (
                    "按缺陷报告修复对应文件 (可修改 index.html/style.css/app.js), "
                    "保持其余功能不变; 确保 JS 语法正确。"
                )
            else:
                design = next(
                    (i for i in context.get("inputs", []) if i.get("type") == "design"), {}
                )
                uxui = next(
                    (i for i in context.get("inputs", []) if i.get("type") == "ux_ui"), {}
                )
                product = next(
                    (i for i in context.get("inputs", []) if i.get("type") == "product"), {}
                )
                objective = (
                    "从零实现一个 Web App (纯前端 HTML/CSS/JS)。\n\n"
                    "## 用户需求\n" + idea
                    + "\n\n## 产品需求摘要 (Product Artifact)\n"
                    + json.dumps(product.get("metadata") or {}, ensure_ascii=False, indent=1)[:4000]
                    + "\n\n## UX/UI 设计摘要 (ux_ui Artifact)\n"
                    + json.dumps(uxui.get("metadata") or {}, ensure_ascii=False, indent=1)[:5000]
                    + "\n\n## 技术设计摘要 (design Artifact)\n"
                    + json.dumps(design.get("metadata") or {}, ensure_ascii=False, indent=1)[:5000]
                )
                extra = (
                    "项目为空目录 (greenfield): 请直接创建 index.html / style.css / app.js "
                    "三个文件 (结构合理即可), 严格遵循验收标准。"
                )
            output = dev.work(
                request=SimpleNamespace(
                    id=f"T-{project_id}-{name}", task_id=f"T-{project_id}-{name}",
                    objective=objective, requirement=REQ,
                ),
                project_context=f"greenfield Web App (纯前端) — {idea}",
                sandbox_path=str(project_dir),
                extra_instruction=extra,
            )
            if output.failure_reason:
                recorder.add_error(f"dev/{name}", output.failure_reason)
                recorder.stage_done("FAILED", output.failure_reason)
                raise RuntimeError(f"developer failed: {output.failure_reason}")
            ok = _apply_patch(project_dir, output.patch_text)
            if not ok:
                recorder.add_error(f"dev/{name}", "patch apply failed")
                recorder.stage_done("FAILED", "patch apply failed")
                raise RuntimeError("patch apply failed")
            result: dict[str, Any] = {
                "artifact_type": "code",
                "ref": "file:///app",
                "metadata": {
                    "files": _list_project_files(project_dir),
                    "changes": (output.report or "")[:600],
                    "project_dir": str(project_dir.resolve()),
                    "patch_head": (output.patch_text or "")[:200],
                },
            }
            if name == "development":
                result["artifact_id"] = ids["code"]
            recorder.stage_done("COMPLETED", f"files={len(result['metadata']['files'])}")
            return result
        except Exception as exc:  # noqa: BLE001
            recorder.add_error(f"dev/{name}", exc)
            recorder.stage_done("FAILED", str(exc))
            raise

    return run


def _make_tester_executor(
    provider: Any, recorder: Recorder, ids: dict[str, str]
) -> Callable[[Any, dict[str, Any]], dict[str, Any]]:
    """Tester executor: 真实确定性测试 + LLM 失败分析 (v4-pro)。"""
    from exec.tester import TesterAgent, build_tester_executor

    tester = TesterAgent(
        provider=provider,
        test_command="python3 tests/smoke_check.py",
        command_timeout=60.0,
    )
    base = build_tester_executor(tester)

    def run(stage: Any, context: dict[str, Any]) -> dict[str, Any]:
        name = getattr(stage, "name", "") or stage.id
        recorder.stage("WF-APP", name, "tester")
        try:
            result = base(stage, context)
            test_spec = next(
                (a for a in result.get("artifacts", []) if a.get("type") == "test"), None
            )
            passed = False
            if test_spec is not None:
                passed = bool(
                    (test_spec.get("metadata") or {}).get("results", {}).get("passed")
                )
                if passed:
                    test_spec["id"] = ids["test"]  # 通过轮固定 id (release 输入引用)
            note = (
                f"passed={passed} bugs={len((test_spec or {}).get('metadata', {}).get('bugs', []))}"
            )
            recorder.stage_done("COMPLETED", note)
            return result
        except Exception as exc:  # noqa: BLE001
            recorder.add_error(f"test/{name}", exc)
            recorder.stage_done("FAILED", str(exc))
            raise

    return run


def _make_release_executor(
    provider: Any,
    recorder: Recorder,
    ids: dict[str, str],
    project_dir: Path,
    dist_dir: Path,
) -> Callable[[Any, dict[str, Any]], dict[str, Any]]:
    """Release executor: 真实 v4-pro 生成 release 5 节 + 真实 zip build。"""
    from exec.release import ReleaseAgent

    def run(stage: Any, context: dict[str, Any]) -> dict[str, Any]:
        recorder.stage("WF-APP", "release", "devops")
        try:
            code = _ctx_artifact(context, "code")
            test = _ctx_artifact(context, "test")
            if code is None or test is None:
                raise RuntimeError("release needs BOTH code and test inputs")
            results = (test.get("metadata") or {}).get("results") or {}
            if not results.get("passed"):
                raise RuntimeError(
                    f"quality gate: test {test.get('id')} not passed "
                    f"(passed={results.get('passed')}) — 禁止发布"
                )
            code_meta = {
                "files": _list_project_files(project_dir),
                "changes": "项目最终状态 (含 DevTestLoop 修复)",
                "project_dir": str(project_dir.resolve()),
            }
            release_agent = ReleaseAgent(
                provider=provider, code=code_meta, test=test.get("metadata") or {}
            )
            artifact = release_agent.release(code_meta, test.get("metadata") or {})
            version = artifact.version

            dist_dir.mkdir(parents=True, exist_ok=True)
            zip_name = f"app-{version}.zip"
            zip_path = dist_dir / zip_name
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in _list_project_files(project_dir):
                    zf.write(project_dir / f, arcname=f)
            zip_size = zip_path.stat().st_size

            metadata = artifact.to_dict()
            metadata["artifact_refs"] = [code.get("id", ""), test.get("id", "")]
            metadata["package"] = {
                "name": "app",
                "type": "zip",
                "files": [str(zip_path)],
                "size_bytes": zip_size,
            }
            metadata["build_result"] = {
                "status": "success",
                "command": f"python3 zipfile build -> {zip_name}",
            }
            recorder.stage_done(
                "COMPLETED", f"version={version} package={zip_name} ({zip_size}B)"
            )
            return {
                "artifact_type": "release",
                "artifact_id": ids["release"],
                "ref": f"file:///{zip_path}",
                "metadata": metadata,
            }
        except Exception as exc:  # noqa: BLE001
            recorder.add_error("release", exc)
            recorder.stage_done("FAILED", str(exc))
            raise

    return run


# ------------------------------------------------------------------ 工具


def _fixed_id(
    executor: Callable[[Any, dict[str, Any]], dict[str, Any]], artifact_id: str
) -> Callable[[Any, dict[str, Any]], dict[str, Any]]:
    """包装 executor: 输出产物固定 id (链预定义引用)。"""

    def run(stage: Any, context: dict[str, Any]) -> dict[str, Any]:
        result = executor(stage, context)
        result["artifact_id"] = artifact_id
        return result

    return run


def _ctx_artifact(context: dict[str, Any], type_: str) -> dict[str, Any] | None:
    for inp in context.get("inputs", []):
        if isinstance(inp, dict) and inp.get("type") == type_:
            return inp
    return None


def _init_project_dir(project_dir: Path) -> None:
    """greenfield git 仓库初始化 (developer patch 应用基线)。"""
    project_dir.mkdir(parents=True, exist_ok=True)
    if not (project_dir / ".git").exists():
        subprocess.run(["git", "init", "-q"], cwd=project_dir, check=True)
    subprocess.run(
        ["git", "config", "user.email", "console@ai-software-factory.local"],
        cwd=project_dir, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "AI Software Factory Console"],
        cwd=project_dir, check=True,
    )
    subprocess.run(["git", "add", "-A"], cwd=project_dir, check=True)
    proc = subprocess.run(
        ["git", "commit", "-q", "-m", "baseline (greenfield)"],
        cwd=project_dir, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        # 空仓库 commit 是正常信号 (英文/中文环境输出位置不同: stdout/stderr 都可能)
        combined = proc.stderr + proc.stdout
        if "nothing to commit" not in combined and "无文件要提交" not in combined:
            raise RuntimeError(
                f"baseline commit failed: rc={proc.returncode} "
                f"stderr={proc.stderr.strip()[:300]!r} stdout={proc.stdout.strip()[:200]!r}"
            )


def _list_project_files(project_dir: Path) -> list[str]:
    files = []
    for f in sorted(project_dir.rglob("*")):
        if f.is_file() and ".git" not in f.parts:
            files.append(str(f.relative_to(project_dir)))
    return files


def _apply_patch(project_dir: Path, patch_text: str) -> bool:
    """真实应用 Developer patch (git apply; 失败 → patch -p1 兜底; 都失败 → False)。"""
    if not patch_text.strip():
        return True
    patch_path = project_dir / ".console-apply.patch"
    patch_path.write_text(patch_text, encoding="utf-8")
    try:
        proc = subprocess.run(
            ["git", "apply", "--whitespace=nowarn", str(patch_path)],
            cwd=project_dir, capture_output=True, text=True,
        )
        if proc.returncode == 0:
            return True
        proc2 = subprocess.run(
            ["patch", "-p1", "-i", str(patch_path)],
            cwd=project_dir, capture_output=True, text=True,
        )
        return proc2.returncode == 0
    finally:
        patch_path.unlink(missing_ok=True)


_SMOKE_CHECK_PY = r'''#!/usr/bin/env python3
"""Web App 冒烟测试 (确定性, 非 LLM): 静态检查 + JS 语法 + 交互/持久化断言。

检查项:
1. index.html / style.css / app.js 存在
2. index.html 正确引用 style.css 与 app.js
3. app.js 非空 + node --check 语法通过
4. app.js 含核心 API (localStorage 持久化 / addEventListener 交互)
"""
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        failures.append(name)


for f in ("index.html", "style.css", "app.js"):
    check(f"{f} exists", (root / f).is_file())

html_path = root / "index.html"
if html_path.is_file():
    html = html_path.read_text(encoding="utf-8")
    check("index.html references style.css", "style.css" in html)
    check("index.html references app.js", "app.js" in html)

js_path = root / "app.js"
js = ""
if js_path.is_file():
    js = js_path.read_text(encoding="utf-8")
    check("app.js non-empty", len(js.strip()) > 100)
    try:
        proc = subprocess.run(
            ["node", "--check", str(js_path)],
            capture_output=True, text=True, timeout=30,
        )
        check("app.js node syntax", proc.returncode == 0, proc.stderr.strip()[:200])
    except FileNotFoundError:
        check("app.js node syntax", False, "node not found")

if js:
    check("app.js uses localStorage (persistence)", "localStorage" in js)
    check("app.js has addEventListener (interaction)", "addEventListener" in js)

print(f"\nRESULT: {len(failures)} failure(s)")
sys.exit(1 if failures else 0)
'''


def _write_test_suite(project_dir: Path) -> None:
    tests_dir = project_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "smoke_check.py").write_text(_SMOKE_CHECK_PY, encoding="utf-8")


def _finalize(
    recorder: Recorder,
    started: str,
    final_status: str,
    wf_lifecycle: Any,
    event_store: Any,
    ids: dict[str, str],
    project_dir: Path,
) -> dict[str, Any]:
    """收集产物/事件 + 验收断言 → 报告 dict (与 S8-005 同口径)。"""
    checks: dict[str, Any] = {}
    for aid in ids.values():
        try:
            art = wf_lifecycle.registry.get(aid)
        except Exception:  # noqa: BLE001 — 链中断产物 MISSING, 不崩溃
            recorder.add_artifact({"id": aid, "status": "MISSING"})
            continue
        if art is None:
            recorder.add_artifact({"id": aid, "status": "MISSING"})
            continue
        d = art.to_dict()
        meta = d.get("metadata") or {}
        recorder.add_artifact({
            "id": d.get("id"),
            "type": str(d.get("type")),
            "status": str(d.get("status")),
            "stage_id": d.get("stage_id"),
            "producer_role": d.get("producer_role"),
            "ref": d.get("ref"),
            "metadata_keys": sorted(meta.keys()) if isinstance(meta, dict) else [],
        })
    validated = {
        a["id"]: (a["status"] or "").upper() == "VALIDATED" for a in recorder.artifacts
    }
    checks["artifact_chain_all_validated"] = all(validated.values())
    checks["artifact_statuses"] = {
        k: ("VALIDATED" if v else "NOT-VALIDATED") for k, v in validated.items()
    }
    stages_ok = all(s["status"] == "COMPLETED" for s in recorder.stages)
    checks["stages_all_completed"] = stages_ok
    checks["stage_statuses"] = {
        f"{s['workflow']}/{s['stage']}": s["status"] for s in recorder.stages
    }
    checks["code_files_exist"] = {
        f: (project_dir / f).is_file() for f in ("index.html", "style.css", "app.js")
    }
    checks["all_pass"] = bool(
        checks["artifact_chain_all_validated"]
        and checks["stages_all_completed"]
        and all(checks["code_files_exist"].values())
        and final_status == "COMPLETED"
    )
    for type_, count in sorted(event_store.count_by_type().items()):
        recorder.events[type_] = count
    return {
        "model": get_config().get_llm()["model"],
        "started_at": started,
        "finished_at": _now(),
        "final_workflow_status": final_status,
        "stages": recorder.stages,
        "calls": recorder.calls,
        "artifacts": recorder.artifacts,
        "events_by_type": recorder.events,
        "totals": recorder.totals(),
        "errors": recorder.errors,
        "acceptance": checks,
    }


__all__ = [
    "Recorder",
    "WorkflowConflictError",
    "WorkflowStartError",
    "has_llm_key",
    "is_project_running",
    "load_llm_key",
    "run_project_chain",
    "start_project_workflow",
]
