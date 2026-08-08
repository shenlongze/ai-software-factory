#!/usr/bin/env python3
"""S8-005 Full App Lifecycle Demo — 记账 Web App 全链真实执行 (禁 mock)。

链: Idea → PM (product) → UX/UI (ux_ui) → Architect (design) → Developer
    (development, 真实代码 HTML/CSS/JS) → Tester (testing, 真实测试 +
    DevTestLoop 修复轮 ≤2) → Release (release, 真实 zip build)。

设计 (S7-005 已验证模式, 只组合不重写):
- WF-S8-DESIGN: product→ux_ui→design 3 阶段线性链 (base WorkflowRunner)
- WF-S8-APP: development→testing→release (DevTestLoopRunner; 测试失败 →
  repair/retest ≤2 轮 → 通过后交回 base Runner 推 release)
- 拆分原因 (诚实): DevTestLoopRunner 语义只处理 dev/test 对, 不推上游
  stage (S7-005 §2 教训); 6 阶段链语义完整, Artifact 跨 workflow 同项目
  引用 (就绪判定只要求同项目 VALIDATED)。

每阶段: 真实 DeepSeek v4-pro 调用 (RecordingProvider 记录 usage/延迟/成本);
artifact 自动注册 (create→generated→VALIDATED); org.workflow.* 事件。
输出: results/s8-005-demo.json + 日志 (stdout)。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

# ------------------------------------------------------------------ 环境

ROOT = Path("/Users/Shared/work/ai-software-factory")
for p in ("factory-core", "factory-org", "factory-exec"):
    sys.path.insert(0, str(ROOT / p))

BASE = ROOT / "factory-exec" / "benchmark_s8_demo"
ORG_DIR = BASE / "org"
DB_PATH = BASE / "events.db"
PROJECT_DIR = BASE / "app_project"
DIST_DIR = BASE / "dist"
RESULTS_DIR = BASE / "results"

IDEA_TEXT = (
    "开发一个简单记账 App (纯前端网页应用): 用户可以快速记录每笔收入和支出, "
    "查看当前余额与收支明细列表, 数据保存在浏览器本地 (刷新不丢失), 界面简洁易用。"
)
MODEL = "deepseek-v4-pro"
BASE_URL = "https://api.deepseek.com/v1/chat/completions"

# Artifact 链固定 id (跨 workflow 预定义引用)
A_IDEA = "A-S8-IDEA"
A_PRODUCT = "A-S8-PRODUCT"
A_UXUI = "A-S8-UXUI"
A_DESIGN = "A-S8-DESIGN"
A_CODE = "A-S8-CODE"
A_TEST = "A-S8-TEST"
A_RELEASE = "A-S8-RELEASE"

# ------------------------------------------------------------------ 记录


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Recorder:
    """阶段/调用/产物/事件集中记录。"""

    def __init__(self) -> None:
        self.stages: list[dict[str, Any]] = []
        self.calls: list[dict[str, Any]] = []
        self.artifacts: list[dict[str, Any]] = []
        self.events: dict[str, int] = {}
        self.errors: list[dict[str, Any]] = []
        self.started = time.monotonic()
        self.current_stage: dict[str, Any] | None = None

    def stage(self, workflow: str, name: str, role: str, artifact_ids: list[str]) -> None:
        self.current_stage = {
            "workflow": workflow,
            "stage": name,
            "role": role,
            "artifact_ids": artifact_ids,
            "calls": [],
            "cost_usd_est": 0.0,
            "latency_s": 0.0,
            "status": "RUNNING",
        }
        self.stages.append(self.current_stage)
        log(f"[stage] {workflow} / {name} (role={role}) start")

    def stage_done(self, status: str, note: str = "") -> None:
        if self.current_stage is None:
            return
        self.current_stage["status"] = status
        self.current_stage["note"] = note
        log(f"[stage] {self.current_stage['workflow']} / {self.current_stage['stage']} -> {status} {note}")
        self.current_stage = None

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

    def add_event(self, type_: str) -> None:
        self.events[type_] = self.events.get(type_, 0) + 1

    def add_error(self, where: str, message: Any) -> None:
        self.errors.append({"where": where, "message": str(message)[:2000]})
        log(f"[error] {where}: {message}")

    def totals(self) -> dict[str, Any]:
        prompt = sum(int(c.get("usage", {}).get("prompt_tokens") or 0) for c in self.calls)
        completion = sum(
            int(c.get("usage", {}).get("completion_tokens") or 0) for c in self.calls
        )
        cost = round(sum(float(c.get("cost_usd_est") or 0.0) for c in self.calls), 6)
        return {
            "calls": len(self.calls),
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
            "cost_usd_est": cost,
            "wall_s": round(time.monotonic() - self.started, 2),
        }


def log(msg: str) -> None:
    print(f"[{_now()}] {msg}", flush=True)


# ------------------------------------------------------------------ 真实 Provider (Recording 包装)

def _load_key() -> str:
    """~/.hermes/.env DEEPSEEK_API_KEY → 进程内注入 OPENAI_API_KEY (禁明文)。"""
    env_path = Path.home() / ".hermes" / ".env"
    key = ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("DEEPSEEK_API_KEY="):
            key = line.split("=", 1)[1].strip().strip('"').strip("'")
            break
    if not key:
        raise SystemExit("DEEPSEEK_API_KEY not found in ~/.hermes/.env")
    os.environ["OPENAI_API_KEY"] = key
    return key


class RecordingProvider:
    """真实 OpenAIProvider 包装: 记录每次调用的 usage/延迟/估算成本。"""

    provider_id = "deepseek-v4-pro-rec"

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.recorder: Recorder | None = None

    def generate(self, request: Any) -> Any:
        t0 = time.monotonic()
        resp = self._inner.generate(request)
        dt = round(time.monotonic() - t0, 2)
        usage = dict(resp.usage or {})
        call: dict[str, Any] = {
            "model": MODEL,
            "max_tokens": request.max_tokens,
            "usage": usage,
            "latency_s": dt,
            "ok": resp.ok,
            "error": resp.error,
            "content_len": len(resp.content or ""),
            # S8-005: 记录头/尾各 300 字符 (诊断用, 不存全量) — demo7
            # 输出 12579/9953 chars 解析失败却无法定位形态的教训
            "content_head": (resp.content or "")[:300],
            "content_tail": (resp.content or "")[-300:],
            "cost_usd_est": round(float(usage.get("estimated_cost_usd") or 0.0), 6),
        }
        if self.recorder is not None:
            self.recorder.add_call(call)
        log(
            f"[call] model={MODEL} max_tokens={request.max_tokens} "
            f"ok={resp.ok} latency={dt}s tokens={usage.get('total_tokens')} "
            f"cost_est={call['cost_usd_est']} content_len={len(resp.content or '')}"
        )
        return resp


def build_provider(recorder: Recorder) -> RecordingProvider:
    _load_key()
    from exec.providers.openai import OpenAIProvider

    inner = OpenAIProvider(
        model=MODEL,
        base_url=BASE_URL,
        timeout=300,
        # DeepSeek v4 费率估算 (per 1K tokens; 仅成本估算, 非计费)
        input_rate_per_1k=0.00028,
        output_rate_per_1k=0.00042,
    )
    wrapper = RecordingProvider(inner)
    wrapper.recorder = recorder
    return wrapper


# ------------------------------------------------------------------ org 基础设施


def setup_org(recorder: Recorder) -> tuple[Any, Any, Any, Any]:
    from events.logger import EventLogger
    from events.store import EventStore
    from org.projects import ProjectLifecycle, ProjectStore
    from org.workflow import WorkflowLifecycle

    # Demo 自清理 (仅本 demo 目录; 幂等重跑)
    for p in (ORG_DIR, DIST_DIR):
        if p.exists():
            shutil.rmtree(p)
    # events.db 连同 sqlite 伴随文件 (-shm/-wal) 一起清理 — 上次异常退出
    # (如契约失败 sys.exit) 可能残留 WAL, 只删主文件会导致新建 db 时
    # sqlite "disk I/O error" (S8-005 demo3 真实遇到)。
    for f in (
        DB_PATH,
        Path(f"{DB_PATH}-shm"),
        Path(f"{DB_PATH}-wal"),
    ):
        if f.exists():
            f.unlink()
    ORG_DIR.mkdir(parents=True, exist_ok=True)
    store = ProjectStore(ORG_DIR)
    event_store = EventStore(DB_PATH)
    logger = EventLogger(event_store)
    lifecycle = ProjectLifecycle(store, logger=logger)
    wf_lifecycle = WorkflowLifecycle(store, logger=logger)
    project = lifecycle.create_project(
        "S8-005 记账 Web App Demo",
        goal="Idea → PM → UX/UI → Architect → Developer → Tester → Release 全链真实执行",
        project_id="P-S8-DEMO",
    )
    log(f"[org] project {project.id} created; org_dir={ORG_DIR}")
    return store, event_store, logger, wf_lifecycle


def register_idea(wf_lifecycle: Any, stage_id: str) -> None:
    art = wf_lifecycle.registry.create(
        stage_id=stage_id,
        type_="idea",
        project_id="P-S8-DEMO",
        ref="file:///idea.md",
        producer_role="product-manager",
        metadata={"idea": IDEA_TEXT},
        artifact_id=A_IDEA,
    )
    wf_lifecycle.registry.mark_generated(art.id)
    art, validation = wf_lifecycle.registry.validate(art.id)
    if not validation.ok:
        raise SystemExit(f"idea artifact contract failed: {validation}")
    log(f"[org] idea artifact {A_IDEA} VALIDATED")


def build_design_workflow(wf_lifecycle: Any) -> tuple[Any, list[Any]]:
    """WF-S8-DESIGN: product → ux_ui → design (线性链, 固定产物 id)。"""
    wf = wf_lifecycle.create_workflow(
        "P-S8-DEMO",
        "S8-005 设计链 (product→ux_ui→design)",
        workflow_id="WF-S8-DESIGN",
    )
    s_product = wf_lifecycle.create_stage(
        wf.id, "product-manager", name="product",
        input_artifacts=[A_IDEA], stage_id="STG-S8-PRODUCT",
    )
    s_uxui = wf_lifecycle.create_stage(
        wf.id, "ui-designer", name="ux_ui",
        depends_on=[s_product.id], input_artifacts=[A_PRODUCT],
        stage_id="STG-S8-UXUI",
    )
    s_design = wf_lifecycle.create_stage(
        wf.id, "architect", name="design",
        depends_on=[s_uxui.id],
        input_artifacts=[A_PRODUCT, A_UXUI],
        stage_id="STG-S8-DESIGN",
    )
    return wf, [s_product, s_uxui, s_design]


def build_app_workflow(wf_lifecycle: Any) -> tuple[Any, list[Any]]:
    """WF-S8-APP: development → testing → release (DevTestLoopRunner)。"""
    wf = wf_lifecycle.create_workflow(
        "P-S8-DEMO",
        "S8-005 开发测试发布链 (development→testing→release)",
        workflow_id="WF-S8-APP",
    )
    s_dev = wf_lifecycle.create_stage(
        wf.id, "developer", name="development",
        input_artifacts=[A_PRODUCT, A_UXUI, A_DESIGN],
        stage_id="STG-S8-DEV",
    )
    s_test = wf_lifecycle.create_stage(
        wf.id, "tester", name="testing",
        depends_on=[s_dev.id], stage_id="STG-S8-TEST",
    )
    s_rel = wf_lifecycle.create_stage(
        wf.id, "devops", name="release",
        depends_on=[s_test.id],
        input_artifacts=[A_CODE, A_TEST],
        stage_id="STG-S8-REL",
    )
    return wf, [s_dev, s_test, s_rel]


def fixed_id(executor: Callable[[Any, dict[str, Any]], dict[str, Any]], artifact_id: str):
    """包装 executor: 输出产物固定 id (S7-005 模式 — 链预定义引用)。"""

    def run(stage: Any, context: dict[str, Any]) -> dict[str, Any]:
        result = executor(stage, context)
        result["artifact_id"] = artifact_id
        return result

    return run


# ------------------------------------------------------------------ 项目目录 (greenfield git)


def init_project() -> None:
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    if not (PROJECT_DIR / ".git").exists():
        subprocess.run(["git", "init", "-q"], cwd=PROJECT_DIR, check=True)
    # repo 级身份 (防止全局未配置导致 commit 失败)
    subprocess.run(
        ["git", "config", "user.email", "s8-demo@ai-software-factory.local"],
        cwd=PROJECT_DIR, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "S8-005 Demo"],
        cwd=PROJECT_DIR, check=True,
    )
    # baseline commit (git apply 需要)
    subprocess.run(["git", "add", "-A"], cwd=PROJECT_DIR, check=True)
    proc = subprocess.run(
        ["git", "commit", "-q", "-m", "baseline (S8-005 greenfield)"],
        cwd=PROJECT_DIR, capture_output=True, text=True,
    )
    if proc.returncode != 0 and "nothing to commit" not in proc.stderr:
        log(f"[project] baseline commit: {proc.stderr.strip()}")


def write_test_suite() -> None:
    """Tester 确定性测试套件 (静态检查 + JS 语法 + 简单断言; 非 LLM)。"""
    tests_dir = PROJECT_DIR / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "smoke_check.py").write_text(SMOKE_CHECK_PY, encoding="utf-8")
    log("[project] tests/smoke_check.py written")


def list_project_files() -> list[str]:
    files = []
    for f in sorted(PROJECT_DIR.rglob("*")):
        if f.is_file() and ".git" not in f.parts:
            files.append(str(f.relative_to(PROJECT_DIR)))
    return files


def apply_patch(patch_text: str) -> bool:
    """真实应用 Developer patch (git apply; 失败 → 返回 False, 不掩盖)。"""
    if not patch_text.strip():
        log("[dev] empty patch — no changes")
        return True
    patch_path = PROJECT_DIR / ".s8-apply.patch"
    patch_path.write_text(patch_text, encoding="utf-8")
    try:
        proc = subprocess.run(
            ["git", "apply", "--whitespace=nowarn", str(patch_path)],
            cwd=PROJECT_DIR, capture_output=True, text=True,
        )
        if proc.returncode != 0:
            log(f"[dev] git apply FAILED: {proc.stderr.strip()[:500]}")
            # fallback: patch -p1 (diff 缺 a/ b/ 前缀时)
            proc2 = subprocess.run(
                ["patch", "-p1", "-i", str(patch_path)],
                cwd=PROJECT_DIR, capture_output=True, text=True,
            )
            if proc2.returncode == 0:
                log("[dev] git apply failed, patch -p1 applied OK")
                return True
            log(f"[dev] patch -p1 also failed: {proc2.stdout.strip()[:300]}")
            return False
        return True
    finally:
        patch_path.unlink(missing_ok=True)


SMOKE_CHECK_PY = r'''#!/usr/bin/env python3
"""记账 Web App 冒烟测试: 静态检查 + JS 语法 + 简单断言 (确定性, 非 LLM)。

检查项:
1. index.html / style.css / app.js 存在
2. index.html 正确引用 style.css 与 app.js
3. app.js 非空 + node --check 语法通过
4. app.js 含核心 API (localStorage 持久化 / addEventListener 交互)
5. 页面包含记账语义关键字 (ledger/expense/记账)
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


# 1. 文件存在
for f in ("index.html", "style.css", "app.js"):
    check(f"{f} exists", (root / f).is_file())

# 2. HTML 引用
html_path = root / "index.html"
if html_path.is_file():
    html = html_path.read_text(encoding="utf-8")
    check("index.html references style.css", "style.css" in html)
    check("index.html references app.js", "app.js" in html)
    lowered = html.lower()
    check(
        "index.html has ledger/expense semantics",
        any(k in lowered for k in ("ledger", "expense", "记账", "收支")),
    )

# 3. JS 语法
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

# 4. 核心交互/持久化 API
if js:
    check("app.js uses localStorage (persistence)", "localStorage" in js)
    check("app.js has addEventListener (interaction)", "addEventListener" in js)

# 5. JS 基础断言: balance 计算关键字 (函数级简单断言)
if js:
    check("app.js has balance semantics", any(k in js for k in ("balance", "total", "余额")))

print(f"\nRESULT: {len(failures)} failure(s)")
sys.exit(1 if failures else 0)
'''


# ------------------------------------------------------------------ 阶段 Executors (真实 LLM)


def make_design_executors(provider: RecordingProvider, recorder: Recorder):
    """PM / UXUI / Architect executor (真实 v4-pro; 固定产物 id)。

    Architect 双输入 (S8-003 强校验): 不在构造时预绑 — 从 workflow context
    inputs 实时解析 product + ux_ui artifact (registry 注入), 构造
    ArchitectAgent(product=..., ux_ui=...) — 禁止脱离输入独立生成。
    """
    from exec.architect import ArchitectAgent, build_arch_executor
    from exec.pm import PMAgent, build_pm_executor
    from exec.uxui import UXUIDesignerAgent, build_uxui_executor

    pm = PMAgent(provider=provider)
    uxui = UXUIDesignerAgent(provider=provider)

    def wrap(name: str, fn: Callable[[Any, dict[str, Any]], dict[str, Any]]):
        def run(stage: Any, context: dict[str, Any]) -> dict[str, Any]:
            recorder.stage("WF-S8-DESIGN", name, stage.role_id, [])
            try:
                result = fn(stage, context)
                # S8-005: 成功路径也必须 stage_done("COMPLETED") — demo5 前
                # 成功不调, recorder 报告里 stage 永远 RUNNING, acceptance
                # stages_all_completed 误判失败 (真实 bug, 已修)。
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
        """Architect executor: context 双输入 (product + ux_ui) → 构造 → design。"""
        product = _ctx_artifact(context, "product")
        uxui_art = _ctx_artifact(context, "ux_ui")
        if product is None or uxui_art is None:
            raise RuntimeError(
                "architect needs BOTH product and ux_ui artifacts in context inputs "
                "(双输入强校验 — 禁止脱离输入独立生成)"
            )
        agent = ArchitectAgent(
            provider=provider,
            product=dict(product.get("metadata") or {}),
            ux_ui=dict(uxui_art.get("metadata") or {}),
        )
        return build_arch_executor(agent)(stage, context)

    return {
        "product-manager": fixed_id(wrap("product", build_pm_executor(pm)), A_PRODUCT),
        "ui-designer": fixed_id(wrap("ux_ui", build_uxui_executor(uxui)), A_UXUI),
        "architect": fixed_id(wrap("design", arch_run), A_DESIGN),
    }


def _ctx_artifact(context: dict[str, Any], type_: str) -> dict[str, Any] | None:
    """从 executor context inputs 取指定类型产物 (id/type/metadata)。"""
    for inp in context.get("inputs", []):
        if isinstance(inp, dict) and inp.get("type") == type_:
            return inp
    return None


def make_dev_executor(provider: RecordingProvider, recorder: Recorder):
    """Developer executor: 真实 v4-pro 生成代码 → git apply → code artifact。

    首轮 (development): 输入 = product+ux_ui+design → 从零实现记账 Web App。
    修复轮 (repair N): 输入 = bug_report → 按缺陷修复 (DevTestLoop 接线)。
    """
    from exec.developer import DeveloperAgent

    dev = DeveloperAgent(provider=provider)
    REQ = (
        "1. 纯前端 HTML/CSS/JS, 零外部依赖 (不引 CDN/框架);\n"
        "2. 打开 index.html 即可使用 (浏览器本地存储 localStorage 持久化);\n"
        "3. 支持记录收入/支出 (类型、金额、说明、日期), 展示余额与明细列表;\n"
        "4. JS 语法必须正确 (node --check 验证); index.html 必须引用 style.css 与 app.js。"
    )

    def run(stage: Any, context: dict[str, Any]) -> dict[str, Any]:
        name = getattr(stage, "name", "") or stage.id
        recorder.stage("WF-S8-APP", name, "developer", [])
        try:
            bugs = [
                inp for inp in context.get("inputs", [])
                if isinstance(inp, dict) and inp.get("type") == "bug_report"
            ]
            if bugs:
                objective = (
                    "修复记账 Web App 中测试发现的功能缺陷。缺陷报告:\n"
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
                    "从零实现一个记账 Web App (纯前端 HTML/CSS/JS)。\n\n"
                    "## 产品需求摘要 (Product Artifact)\n"
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
                request=SimpleNamespace(id="T-DEMO-001", task_id="T-DEMO-001", objective=objective, requirement=REQ),
                project_context="greenfield 记账 Web App (纯前端)",
                sandbox_path=str(PROJECT_DIR),
                extra_instruction=extra,
            )
            if output.failure_reason:
                recorder.add_error(f"dev/{name}", output.failure_reason)
                recorder.stage_done("FAILED", output.failure_reason)
                raise RuntimeError(f"developer failed: {output.failure_reason}")
            ok = apply_patch(output.patch_text)
            if not ok:
                recorder.add_error(f"dev/{name}", "patch apply failed")
                recorder.stage_done("FAILED", "patch apply failed")
                raise RuntimeError("patch apply failed")
            result: dict[str, Any] = {
                "artifact_type": "code",
                "ref": "file:///app_project",
                "metadata": {
                    "files": list_project_files(),
                    "changes": (output.report or "")[:600],
                    "project_dir": str(PROJECT_DIR.resolve()),
                    "patch_head": (output.patch_text or "")[:200],
                },
            }
            if name == "development":
                result["artifact_id"] = A_CODE
            recorder.stage_done("COMPLETED", f"files={len(result['metadata']['files'])}")
            return result
        except Exception as exc:  # noqa: BLE001
            recorder.add_error(f"dev/{name}", exc)
            recorder.stage_done("FAILED", str(exc))
            raise

    return run


def make_tester_executor(provider: RecordingProvider, recorder: Recorder):
    """Tester executor: 真实确定性测试 + LLM 失败分析 (v4-pro)。

    通过轮 test 产物固定 id = A-S8-TEST (release 输入引用 = 最终通过轮);
    失败轮自动 id (防 DuplicateError — S7-005 教训)。
    """
    from exec.tester import TesterAgent, build_tester_executor

    tester = TesterAgent(
        provider=provider,
        test_command="python3 tests/smoke_check.py",
        command_timeout=60.0,
    )
    base = build_tester_executor(tester)

    def run(stage: Any, context: dict[str, Any]) -> dict[str, Any]:
        name = getattr(stage, "name", "") or stage.id
        recorder.stage("WF-S8-APP", name, "tester", [])
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
                    # 通过轮固定 id (release 输入预定义引用; 失败轮自动 id)
                    test_spec["id"] = A_TEST
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


def make_release_executor(provider: RecordingProvider, recorder: Recorder):
    """Release executor: 真实 v4-pro 生成 release 5 节 + 真实 zip build。

    质量门禁 (双保险): ReleaseAgent test VALIDATED 强校验 + 此处显式
    results.passed=True 才允许发布 (未通过测试禁发布)。
    """
    from exec.release import ReleaseAgent, build_release_executor

    # ReleaseAgent 构造强校验 (code+test 必填) → executor 内惰性构造
    def run(stage: Any, context: dict[str, Any]) -> dict[str, Any]:
        recorder.stage("WF-S8-APP", "release", "devops", [])
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
            # code metadata 用项目实时状态 (修复轮后与 artifact 同步)
            code_meta = {
                "files": list_project_files(),
                "changes": "项目最终状态 (含 DevTestLoop 修复)",
                "project_dir": str(PROJECT_DIR.resolve()),
            }
            release_agent = ReleaseAgent(
                provider=provider, code=code_meta, test=test.get("metadata") or {}
            )
            artifact = release_agent.release(code_meta, test.get("metadata") or {})
            version = artifact.version

            # 真实 build: zip 打包 (version + notes)
            DIST_DIR.mkdir(parents=True, exist_ok=True)
            zip_name = f"ledger-app-{version}.zip"
            zip_path = DIST_DIR / zip_name
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in list_project_files():
                    zf.write(PROJECT_DIR / f, arcname=f)
            zip_size = zip_path.stat().st_size
            log(f"[release] built {zip_path} ({zip_size} bytes)")

            metadata = artifact.to_dict()
            metadata["artifact_refs"] = [code.get("id", ""), test.get("id", "")]
            metadata["package"] = {
                "name": "ledger-app",
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
                "artifact_id": A_RELEASE,
                "ref": f"file:///{zip_path}",
                "metadata": metadata,
            }
        except Exception as exc:  # noqa: BLE001
            recorder.add_error("release", exc)
            recorder.stage_done("FAILED", str(exc))
            raise

    return run


# ------------------------------------------------------------------ 事件统计


def collect_events(event_store: Any, recorder: Recorder) -> None:
    for type_, count in sorted(event_store.count_by_type().items()):
        recorder.events[type_] = count


def collect_artifacts(wf_lifecycle: Any, recorder: Recorder) -> None:
    for aid in (A_IDEA, A_PRODUCT, A_UXUI, A_DESIGN, A_CODE, A_TEST, A_RELEASE):
        try:
            art = wf_lifecycle.registry.get(aid)
        except Exception as exc:  # noqa: BLE001 — NotFoundError (demo2 踩过):
            # artifact 未注册 (链中断) → 记录 MISSING 而非崩溃
            recorder.add_artifact({"id": aid, "status": "MISSING", "note": str(exc)[:200]})
            continue
        if art is None:
            recorder.add_artifact({"id": aid, "status": "MISSING"})
            continue
        d = art.to_dict()
        meta = d.get("metadata") or {}
        summary = {
            "id": d.get("id"),
            "type": str(d.get("type")),
            "status": str(d.get("status")),
            "stage_id": d.get("stage_id"),
            "producer_role": d.get("producer_role"),
            "ref": d.get("ref"),
            "metadata_keys": sorted(meta.keys()) if isinstance(meta, dict) else [],
        }
        recorder.add_artifact(summary)


# ------------------------------------------------------------------ 主流程


def acceptance(recorder: Recorder) -> dict[str, Any]:
    """验收断言: Artifact 链全 VALIDATED + Stage 全 COMPLETED + 产物真实。"""
    checks: dict[str, Any] = {}

    validated = {
        a["id"]: (a["status"] or "").upper() == "VALIDATED"
        for a in recorder.artifacts
    }
    checks["artifact_chain_all_validated"] = all(validated.values())
    checks["artifact_statuses"] = {k: ("VALIDATED" if v else "NOT-VALIDATED") for k, v in validated.items()}

    stages_ok = all(s["status"] == "COMPLETED" for s in recorder.stages)
    checks["stages_all_completed"] = stages_ok
    checks["stage_statuses"] = {f"{s['workflow']}/{s['stage']}": s["status"] for s in recorder.stages}

    checks["code_files_exist"] = {
        f: (PROJECT_DIR / f).is_file() for f in ("index.html", "style.css", "app.js")
    }
    test_meta = next(
        (a for a in recorder.artifacts if a["id"] == A_TEST), None
    )
    checks["test_artifact_validated"] = test_meta is not None and test_meta["status"] == "VALIDATED"
    zips = list(DIST_DIR.glob("*.zip"))
    checks["release_zip_exists"] = len(zips) > 0
    checks["release_zips"] = [str(z.name) for z in zips]

    all_ok = (
        checks["artifact_chain_all_validated"]
        and checks["stages_all_completed"]
        and all(checks["code_files_exist"].values())
        and checks["test_artifact_validated"]
        and checks["release_zip_exists"]
    )
    checks["all_pass"] = bool(all_ok)
    return checks


def main() -> int:
    started = _now()
    log(f"S8-005 demo start (model={MODEL}, base_url={BASE_URL})")
    log(f"project_dir={PROJECT_DIR}")

    recorder = Recorder()
    provider = build_provider(recorder)

    # 1. org + idea
    store, event_store, logger, wf_lifecycle = setup_org(recorder)

    # 2. 项目目录 + 测试套件 (Tester 工具箱; developer 生成 app 代码)
    init_project()
    write_test_suite()

    # 3. workflow 定义 (6 stage 链)
    wfd, stages_design = build_design_workflow(wf_lifecycle)
    wfa, stages_app = build_app_workflow(wf_lifecycle)
    register_idea(wf_lifecycle, "STG-S8-PRODUCT")
    log("[org] workflows WF-S8-DESIGN (3 stages) + WF-S8-APP (3 stages) defined")

    # 4. 执行 设计链 (base WorkflowRunner)
    from exec.tester import make_workflow_executor
    from org.workflow import WorkflowRunner, WorkflowStatus

    design_execs = make_design_executors(provider, recorder)
    design_runner = WorkflowRunner(
        wf_lifecycle, executor=make_workflow_executor(design_execs), logger=logger
    )
    log("[run] WF-S8-DESIGN start (product→ux_ui→design, 真实 v4-pro)")
    wf1 = design_runner.run(wfd.id)
    log(f"[run] WF-S8-DESIGN -> {wf1.status.value}")
    # S8-005 修复: WorkflowStatus.value 是小写 ("completed"), 旧代码比大写
    # "COMPLETED" 永远不相等 → 设计链成功后误判失败提前 return, WF-S8-APP
    # 从未执行 (demo6 真实踩到)。用枚举比较 (大小写无关语义)。
    if wf1.status != WorkflowStatus.COMPLETED:
        recorder.add_error("WF-S8-DESIGN", f"status={wf1.status.value} reason={wf1.failed_reason}")
        # 不中止 — 记录后继续? 不, 设计链失败则后续无输入。诚实中止。
        collect_artifacts(wf_lifecycle, recorder)
        collect_events(event_store, recorder)
        return finalize(recorder, started, wf1.status.value)

    # 5. 执行 开发测试发布链 (DevTestLoopRunner; ≤2 修复轮)
    from org.workflow import DevTestLoopRunner

    app_execs = {
        "developer": make_dev_executor(provider, recorder),
        "tester": make_tester_executor(provider, recorder),
        "devops": make_release_executor(provider, recorder),
    }
    app_runner = DevTestLoopRunner(
        wf_lifecycle,
        executor=make_workflow_executor(app_execs),
        logger=logger,
        max_repair_rounds=2,
    )
    log("[run] WF-S8-APP start (development→testing→release, DevTestLoop ≤2 修复轮)")
    wf2 = app_runner.run(wfa.id)
    log(f"[run] WF-S8-APP -> {wf2.status.value}")
    # S8-005: 同设计链修复 — 枚举比较 (value 为小写 "completed")
    if wf2.status != WorkflowStatus.COMPLETED:
        recorder.add_error(
            "WF-S8-APP",
            f"status={wf2.status.value} reason={wf2.failed_reason}",
        )

    # 6. 收集 + 验收
    collect_artifacts(wf_lifecycle, recorder)
    collect_events(event_store, recorder)
    return finalize(recorder, started, wf2.status.value)


def finalize(recorder: Recorder, started: str, final_status: str) -> int:
    checks = acceptance(recorder)
    report = {
        "task": "S8-005 Full App Lifecycle Demo",
        "model": MODEL,
        "started_at": started,
        "finished_at": _now(),
        "final_workflow_status": final_status,
        "idea": IDEA_TEXT,
        "stages": recorder.stages,
        "calls": recorder.calls,
        "artifacts": recorder.artifacts,
        "events_by_type": recorder.events,
        "totals": recorder.totals(),
        "errors": recorder.errors,
        "acceptance": checks,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / "s8-005-demo.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"[done] report -> {out}")
    log(f"[done] totals: {json.dumps(recorder.totals(), ensure_ascii=False)}")
    log(f"[done] acceptance all_pass={checks['all_pass']}")
    log(f"[done] FINAL_STATUS={final_status}")
    return 0 if checks["all_pass"] and final_status == "COMPLETED" else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"[fatal] {type(exc).__name__}: {exc}", flush=True)
        sys.exit(2)
