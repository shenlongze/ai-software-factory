#!/usr/bin/env python3
"""S9-005 Real Project Pilot — DevToolBox 真实项目试点 (禁 mock)。

链: S9-004 register (Existing Project Adoption) → 分析/快照 → 真实 bug
    修复任务 → 沙箱 Workflow (Developer v4-pro → Tester → Release,
    禁改真实源) → 人工审批门 (Release 前) → 验收全链证据 → JSON/成本记录。

试点项目: DevToolBox (/Users/agentdev/devtoolbox — 33 工具纯前端静态站,
用户生产项目 devcheat.com)。生产保护: 源项目零接触 — 全部修改在沙箱副本
(benchmark_s9_pilot/sandbox/) 内; patch 应用在沙箱; apply 到真实源需人工
(报告注明, 不自动)。

真实 bug (人工挑选, 来自代码审查): js/tools/base64.js 的 clear() 引用
不存在的 DOM 元素 id ('base-input'/'base-output'/'base-mode', 实际应为
'b64-input'/'b64-output'/'b64-mode') → 点击 Clear 按钮抛 TypeError 且无效;
example() 返回 '#base-input' 同样失效。修复 = 4 行最小改动。

简化链 (报告说明): 已有项目 bug 修复 → PM/Architect 不必要 (任务即输入,
idea artifact 承载); 只走 Developer→Tester→Release + Release 前人工审批
(S9-001 三挡板之一, 演示 Console 审批流)。

约束: 不修改 Developer/Tester/Release 核心 (只组合); Core/Runtime/Desktop
冻结; scripts_diag_empty.py 不触碰; 无 rm; key 进程内注入 (禁明文);
mock 不当证明; 失败诚实记录。

输出: results/s9-005-pilot.json (全链记录 + 成本) + stdout 日志。
"""

from __future__ import annotations

import hashlib
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

BASE = ROOT / "factory-exec" / "benchmark_s9_pilot"
ORG_DIR = BASE / "org"
DB_PATH = BASE / "events.db"
SANDBOX_ROOT = BASE / "sandbox"
DIST_DIR = BASE / "dist"
RESULTS_DIR = BASE / "results"
PATCH_DIR = BASE / "sandbox_patches"
SOURCE_PROJECT = Path("/Users/agentdev/devtoolbox")

MODEL = "deepseek-v4-pro"
BASE_URL = "https://api.deepseek.com/v1/chat/completions"
# DeepSeek v4 费率估算 (per 1K tokens; 仅成本估算, 非计费 — S8-005 同源)
INPUT_RATE_PER_1K = 0.00028
OUTPUT_RATE_PER_1K = 0.00042

# Artifact 链固定 id (跨阶段预定义引用)
A_TASK = "A-S9-TASK"
A_CODE = "A-S9-CODE"
A_TEST = "A-S9-TEST"
A_RELEASE = "A-S9-RELEASE"
WF_ID = "WF-S9-PILOT"
P_ID = "P-S9-DEVTOOLBOX"

BUG_TARGET = "js/tools/base64.js"

TASK_TEXT = (
    "修复 DevToolBox 中 base64 工具 (js/tools/base64.js) 的一个真实 UI 缺陷: "
    "clear() 方法引用了不存在的 DOM 元素 id ('base-input'/'base-output'/"
    "'base-mode'), 而页面实际元素 id 为 'b64-input'/'b64-output'/"
    "'b64-mode' (textarea / output div / radio name) — 导致点击 Clear 按钮时 "
    "getElementById 返回 null 并抛出 TypeError, 清除功能完全失效; "
    "example() 方法返回的填充映射同样用了错误的 '#base-input' 键, "
    "示例填充不生效。修复方法: 将 clear() 内 3 处 getElementById 的元素 id "
    "和 example() 返回的对象键改为正确的 'b64-*' id, 保持其余逻辑不变。"
)

REQ_TEXT = (
    "1. 只修改 js/tools/base64.js, 不触碰其他文件;\n"
    "2. clear() 内三处 getElementById 的 id 必须为 'b64-input'、"
    "'b64-output'、'b64-mode';\n"
    "3. example() 返回对象键必须为 '#b64-input';\n"
    "4. 保持现有代码风格 (2 空格缩进, 单引号), 最小改动;\n"
    "5. JS 语法必须正确 (node --check 验证);\n"
    "6. 不引入任何新依赖。"
)

# ------------------------------------------------------------------ 记录


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Recorder:
    """阶段/调用/产物/事件/审批集中记录 (S9-005 全链证据 + 成本)。"""

    def __init__(self) -> None:
        self.stages: list[dict[str, Any]] = []
        self.calls: list[dict[str, Any]] = []
        self.artifacts: list[dict[str, Any]] = []
        self.events: dict[str, int] = {}
        self.errors: list[dict[str, Any]] = []
        self.approvals: list[dict[str, Any]] = []
        self.started = time.monotonic()
        self.current_stage: dict[str, Any] | None = None

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
        log(f"[stage] {workflow} / {name} (role={role}) start")

    def stage_done(self, status: str, note: str = "") -> None:
        if self.current_stage is None:
            return
        self.current_stage["status"] = status
        self.current_stage["note"] = note
        log(f"[stage] {self.current_stage['workflow']} / "
            f"{self.current_stage['stage']} -> {status} {note}")
        self.current_stage = None

    def add_call(self, call: dict[str, Any]) -> None:
        self.calls.append(call)
        if self.current_stage is not None:
            self.current_stage["calls"].append(len(self.calls) - 1)
            self.current_stage["cost_usd_est"] = round(
                self.current_stage["cost_usd_est"]
                + float(call.get("cost_usd_est") or 0.0), 6
            )
            self.current_stage["latency_s"] = round(
                self.current_stage["latency_s"]
                + float(call.get("latency_s") or 0.0), 2
            )

    def add_artifact(self, artifact: dict[str, Any]) -> None:
        self.artifacts.append(artifact)

    def add_event(self, type_: str) -> None:
        self.events[type_] = self.events.get(type_, 0) + 1

    def add_approval(self, gate: dict[str, Any]) -> None:
        self.approvals.append(gate)

    def add_error(self, where: str, message: Any) -> None:
        self.errors.append({"where": where, "message": str(message)[:2000]})
        log(f"[error] {where}: {message}")

    def totals(self) -> dict[str, Any]:
        prompt = sum(int(c.get("usage", {}).get("prompt_tokens") or 0)
                     for c in self.calls)
        completion = sum(int(c.get("usage", {}).get("completion_tokens") or 0)
                         for c in self.calls)
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


# ------------------------------------------------------------------ Provider


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
        # v4-pro reasoning 耗尽防护: Tester/分析 请求默认 4096 太低 → 强制 ≥16384
        if getattr(request, "max_tokens", 0) < 16384:
            request = request.model_copy(update={"max_tokens": 16384})
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
            "cost_usd_est": round(float(usage.get("estimated_cost_usd") or 0.0), 6),
        }
        if self.recorder is not None:
            self.recorder.add_call(call)
        log(f"[call] model={MODEL} max_tokens={request.max_tokens} ok={resp.ok} "
            f"latency={dt}s tokens={usage.get('total_tokens')} "
            f"cost_est={call['cost_usd_est']} content_len={len(resp.content or '')}")
        return resp


def build_provider(recorder: Recorder) -> RecordingProvider:
    _load_key()
    from exec.providers.openai import OpenAIProvider

    inner = OpenAIProvider(
        model=MODEL,
        base_url=BASE_URL,
        timeout=300,
        input_rate_per_1k=INPUT_RATE_PER_1K,
        output_rate_per_1k=OUTPUT_RATE_PER_1K,
    )
    wrapper = RecordingProvider(inner)
    wrapper.recorder = recorder
    return wrapper


# ------------------------------------------------------------------ org + 注册


def setup_org() -> tuple[Any, Any, Any, Any, Any]:
    """ProjectStore + EventStore/Logger + Lifecycle + WorkflowLifecycle +
    ProjectAdoption (S9-004 消费端)。"""
    from events.logger import EventLogger
    from events.store import EventStore
    from org.project_adoption import ProjectAdoption
    from org.projects import ProjectLifecycle, ProjectStore
    from org.workflow import WorkflowLifecycle

    for p in (ORG_DIR, DIST_DIR, PATCH_DIR):
        if p.exists():
            shutil.rmtree(p)
    for f in (DB_PATH, Path(f"{DB_PATH}-shm"), Path(f"{DB_PATH}-wal")):
        if f.exists():
            f.unlink()
    ORG_DIR.mkdir(parents=True, exist_ok=True)
    store = ProjectStore(ORG_DIR)
    event_store = EventStore(DB_PATH)
    logger = EventLogger(event_store)
    lifecycle = ProjectLifecycle(store, logger=logger)
    wf_lifecycle = WorkflowLifecycle(store, logger=logger)
    adoption = ProjectAdoption(store, logger=logger, lifecycle=lifecycle)
    log(f"[org] infra ready; org_dir={ORG_DIR}")
    return store, event_store, logger, wf_lifecycle, adoption


def register_project(adoption: Any) -> dict[str, Any]:
    """S9-004 ProjectAdoption.register: 注册 DevToolBox (分析/基线/快照自动)。"""
    log(f"[register] adopting {SOURCE_PROJECT} (javascript, static web)")
    project = adoption.register(
        SOURCE_PROJECT,
        name="DevToolBox",
        language="javascript",
        project_type="static-web",
        goal="S9-005 Real Project Pilot: 已有项目接入 → 沙箱 bug 修复 → 发布 (人工审批)",
        user_id="s9-005-pilot",
        project_id=P_ID,
    )
    log(f"[register] project {project.id} registered; "
        f"analysis_ref={project.analysis_ref} baseline_ref={project.baseline_ref} "
        f"snapshot_ref={project.snapshot_ref}")
    return {
        "id": project.id,
        "name": project.name,
        "repo_path": project.repo_path,
        "language": project.language,
        "framework": project.framework,
        "project_type": project.project_type,
        "analysis_ref": project.analysis_ref,
        "baseline_ref": project.baseline_ref,
        "snapshot_ref": project.snapshot_ref,
    }


def dump_adoption(adoption: Any, summary: dict[str, Any]) -> dict[str, Any]:
    """分析/基线/快照记录转储 (Agent 理解项目证据 + 环境确认)。"""
    out: dict[str, Any] = {"project": summary}
    analysis = adoption.get_analysis(summary["analysis_ref"])
    baseline = adoption.get_baseline(summary["baseline_ref"])
    snapshot = adoption.get_snapshot(summary["snapshot_ref"])
    if analysis is not None:
        payload = analysis.payload or {}
        out["analysis"] = {
            "id": analysis.id,
            "valid": analysis.valid,
            "errors": analysis.errors,
            "language": payload.get("language"),
            "framework": payload.get("framework"),
            "build_method": payload.get("build_method"),
            "test_method": payload.get("test_method"),
            "structure": payload.get("structure", [])[:8],
            "dependencies": payload.get("dependencies", {}),
        }
    if baseline is not None:
        payload = baseline.payload or {}
        out["baseline"] = {
            "id": baseline.id,
            "valid": baseline.valid,
            "errors": baseline.errors,
            "build": payload.get("build", {}),
            "test": payload.get("test", {}),
        }
    if snapshot is not None:
        payload = snapshot.payload or {}
        out["snapshot"] = {
            "id": snapshot.id,
            "tree_entries": payload.get("tree_entries"),
            "important_count": payload.get("important_count"),
            "important_files": payload.get("important_files", [])[:10],
            "architecture": payload.get("architecture", {}),
            "summary_text": payload.get("summary_text", ""),
        }
    log(f"[adoption] analysis={out.get('analysis', {}).get('id')} "
        f"lang={out.get('analysis', {}).get('language')} "
        f"build={out.get('baseline', {}).get('build', {}).get('status')} "
        f"test={out.get('baseline', {}).get('test', {}).get('status')}")
    return out


# ------------------------------------------------------------------ 沙箱


def make_sandbox() -> tuple[Any, str, dict[str, str]]:
    """创建 DevToolBox 沙箱副本 (源项目零接触) + 写入确定性测试套件。

    返回 (sandbox, 副本根目录, 源文件 hash 基线 — 验收时对比证明源未改)。
    """
    from exec.sandbox import Sandbox

    SANDBOX_ROOT.mkdir(parents=True, exist_ok=True)
    sandbox = Sandbox(SOURCE_PROJECT, work_root=SANDBOX_ROOT, git_bin="git")
    session = sandbox.create(project_files=None)  # 全量副本 (3.7M, 可接受)
    copy_dir = Path(session.workspace_copy_path)
    log(f"[sandbox] created {session.id} -> {copy_dir}")

    # 确定性测试套件写入沙箱副本 (非真实源)
    tests_dir = copy_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "tool_checks.py").write_text(TOOL_CHECKS_PY, encoding="utf-8")
    log("[sandbox] tests/tool_checks.py written (沙箱副本内, 非真实源)")

    # 源 hash 基线 (验收对比)
    hashes = _hash_project(SOURCE_PROJECT)
    return sandbox, str(copy_dir), hashes


def _hash_project(root: Path) -> dict[str, str]:
    """项目源文件 md5 基线 (相对路径 → hash; 验收时对比证明源未改)。"""
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if ".git" in rel.split("/"):
            continue
        out[rel] = hashlib.md5(path.read_bytes()).hexdigest()
    return out


def hash_project_unchanged(root: Path, baseline: dict[str, str]) -> tuple[bool, list[str]]:
    """对比源项目 hash 与基线 → (未变?, 变化文件列表)。"""
    current = _hash_project(root)
    changed = [f for f, h in baseline.items() if current.get(f) != h]
    added = [f for f in current if f not in baseline]
    return (not changed and not added), changed + added


TOOL_CHECKS_PY = r'''#!/usr/bin/env python3
"""DevToolBox base64.js 修复验证 (S9-005 确定性测试, 非 LLM)。

检查项:
1. js/tools/base64.js 存在;
2. node --check 语法通过;
3. bug 修复正确性 (S9-005 缺陷断言):
   - clear() 不再引用不存在的 'base-input'/'base-output'/'base-mode';
   - clear() 引用正确的 'b64-input'/'b64-output'/'b64-mode';
   - example() 返回键为 '#b64-input';
4. 回归: js/tools/ 全部工具 JS 语法通过。
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


def node_check(rel: str) -> bool:
    path = root / rel
    try:
        proc = subprocess.run(["node", "--check", str(path)],
                              capture_output=True, text=True, timeout=30)
        return proc.returncode == 0
    except FileNotFoundError:
        check(f"{rel} node syntax", False, "node not found")
        return False


# 1. 目标文件存在
target = root / "js" / "tools" / "base64.js"
check("js/tools/base64.js exists", target.is_file())
if not target.is_file():
    print("\nRESULT: 1 failure(s)")
    sys.exit(1)

src = target.read_text(encoding="utf-8")

# 2. 语法
check("base64.js node syntax", node_check("js/tools/base64.js"))

# 3. bug 修复断言
check("no stale 'base-input' ref", "getElementById('base-input')" not in src)
check("no stale 'base-output' ref", "getElementById('base-output')" not in src)
check("no stale 'base-mode' ref", "getElementById('base-mode')" not in src)
check("clear() uses b64-input", "getElementById('b64-input')" in src)
check("clear() uses b64-output", "getElementById('b64-output')" in src)
check("clear() uses b64-mode", "getElementById('b64-mode')" in src)
check("example() key is #b64-input", "'#b64-input'" in src)

# 4. 回归: 全部工具 JS 语法
tools_dir = root / "js" / "tools"
if tools_dir.is_dir():
    for js in sorted(tools_dir.glob("*.js")):
        rel = f"js/tools/{js.name}"
        if not node_check(rel):
            check(f"{rel} node syntax", False)

print(f"\nRESULT: {len(failures)} failure(s)")
sys.exit(1 if failures else 0)
'''


# ------------------------------------------------------------------ Workflow


def register_task_artifact(wf_lifecycle: Any) -> None:
    """任务输入 artifact (idea 契约承载任务描述; development 输入)。"""
    art = wf_lifecycle.registry.create(
        stage_id="STG-S9-DEV",
        type_="idea",
        project_id=P_ID,
        ref="file:///task.md",
        producer_role="product-manager",
        metadata={"idea": TASK_TEXT},
        artifact_id=A_TASK,
    )
    wf_lifecycle.registry.mark_generated(art.id)
    art, validation = wf_lifecycle.registry.validate(art.id)
    if not validation.ok:
        raise SystemExit(f"task artifact contract failed: {validation}")
    log(f"[org] task artifact {A_TASK} VALIDATED")


def build_workflow(wf_lifecycle: Any) -> tuple[Any, list[Any]]:
    """WF-S9-PILOT: development → testing → release (DevTestLoopRunner;
    release 前人工审批门 S9-001)。"""
    wf = wf_lifecycle.create_workflow(
        P_ID, "S9-005 DevToolBox base64.js 修复 (development→testing→release)",
        workflow_id=WF_ID,
    )
    s_dev = wf_lifecycle.create_stage(
        wf.id, "developer", name="development",
        input_artifacts=[A_TASK], stage_id="STG-S9-DEV",
    )
    s_test = wf_lifecycle.create_stage(
        wf.id, "tester", name="testing",
        depends_on=[s_dev.id], stage_id="STG-S9-TEST",
    )
    s_rel = wf_lifecycle.create_stage(
        wf.id, "devops", name="release",
        depends_on=[s_test.id],
        input_artifacts=[A_CODE, A_TEST],
        approval_required=True,  # S9-001 三挡板: release 前发布
        stage_id="STG-S9-REL",
    )
    log(f"[org] workflow {wf.id} defined (3 stages; release approval_required=True)")
    return wf, [s_dev, s_test, s_rel]


# ------------------------------------------------------------------ Executors


def fixed_id(executor: Callable[[Any, dict[str, Any]], dict[str, Any]],
             artifact_id: str) -> Callable[[Any, dict[str, Any]], dict[str, Any]]:
    """包装 executor: 输出产物固定 id (链预定义引用)。"""
    def run(stage: Any, context: dict[str, Any]) -> dict[str, Any]:
        result = executor(stage, context)
        result["artifact_id"] = artifact_id
        return result
    return run


def make_dev_executor(provider: RecordingProvider, recorder: Recorder,
                      sandbox: Any, snapshot: dict[str, Any]):
    """Developer executor: 真实 v4-pro 修复 base64.js bug → 沙箱 git apply。"""
    from exec.developer import DeveloperAgent

    dev = DeveloperAgent(provider=provider)
    snapshot_summary = (
        f"DevToolBox (js/tools/base64.js 为目标文件)。"
        f"{snapshot.get('summary_text', '')}\n"
        f"关键文件: " + ", ".join(
            f["path"] for f in snapshot.get("important_files", [])[:8]
        )
    )

    def run(stage: Any, context: dict[str, Any]) -> dict[str, Any]:
        name = getattr(stage, "name", "") or stage.id
        recorder.stage(WF_ID, name, "developer")
        try:
            task = next(
                (i for i in context.get("inputs", []) if i.get("type") == "idea"), {}
            )
            objective = (task.get("metadata") or {}).get("idea") or TASK_TEXT
            output = dev.work(
                request=SimpleNamespace(
                    id="T-S9-005", task_id="T-S9-005",
                    objective=objective, requirement=REQ_TEXT,
                ),
                project_context=snapshot_summary,
                sandbox_path=str(sandbox.copy_dir),
                source_files=[BUG_TARGET],
            )
            if output.failure_reason:
                recorder.add_error(f"dev/{name}", output.failure_reason)
                recorder.stage_done("FAILED", output.failure_reason)
                raise RuntimeError(f"developer failed: {output.failure_reason}")
            if output.patch_text.strip():
                sandbox.apply_patch(output.patch_text)
                diff = sandbox.diff()
                PATCH_DIR.mkdir(parents=True, exist_ok=True)
                patch_file = PATCH_DIR / "s9-005-base64-fix.patch"
                patch_file.write_text(diff, encoding="utf-8")
                log(f"[dev] patch applied to sandbox; diff saved -> {patch_file}")
            else:
                diff = ""
                log("[dev] empty patch — no changes")
            result: dict[str, Any] = {
                "artifact_type": "code",
                "ref": "file:///sandbox/project",
                "metadata": {
                    "files": [BUG_TARGET],
                    "changes": (output.report or "")[:600],
                    "project_dir": str(sandbox.copy_dir),
                    "patch_head": (output.patch_text or "")[:200],
                    "diff_len": len(diff.splitlines()),
                },
            }
            recorder.stage_done("COMPLETED",
                                f"files={len(result['metadata']['files'])}")
            return result
        except Exception as exc:  # noqa: BLE001
            recorder.add_error(f"dev/{name}", exc)
            recorder.stage_done("FAILED", str(exc))
            raise

    return fixed_id(run, A_CODE)


def make_tester_executor(provider: RecordingProvider, recorder: Recorder):
    """Tester executor: 真实确定性测试 (node --check + 断言) + LLM 失败分析。"""
    from exec.tester import TesterAgent, build_tester_executor

    tester = TesterAgent(
        provider=provider,
        test_command="python3 tests/tool_checks.py",
        command_timeout=60.0,
    )
    base = build_tester_executor(tester)

    def run(stage: Any, context: dict[str, Any]) -> dict[str, Any]:
        name = getattr(stage, "name", "") or stage.id
        recorder.stage(WF_ID, name, "tester")
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
                    test_spec["id"] = A_TEST  # 通过轮固定 id (release 输入引用)
            note = f"passed={passed} bugs=" + str(
                len((test_spec or {}).get("metadata", {}).get("bugs", []))
            )
            recorder.stage_done("COMPLETED", note)
            return result
        except Exception as exc:  # noqa: BLE001
            recorder.add_error(f"test/{name}", exc)
            recorder.stage_done("FAILED", str(exc))
            raise

    return run


def make_release_executor(provider: RecordingProvider, recorder: Recorder,
                          sandbox: Any):
    """Release executor: 真实 v4-pro 生成 release 5 节 + 真实 zip build。"""
    from exec.release import ReleaseAgent

    def run(stage: Any, context: dict[str, Any]) -> dict[str, Any]:
        recorder.stage(WF_ID, "release", "devops")
        try:
            code = next((i for i in context.get("inputs", [])
                         if i.get("type") == "code"), None)
            test = next((i for i in context.get("inputs", [])
                         if i.get("type") == "test"), None)
            if code is None or test is None:
                raise RuntimeError("release needs BOTH code and test inputs")
            results = (test.get("metadata") or {}).get("results") or {}
            if not results.get("passed"):
                raise RuntimeError(
                    f"quality gate: test {test.get('id')} not passed "
                    f"(passed={results.get('passed')}) — 禁止发布"
                )
            code_meta = {
                "files": (code.get("metadata") or {}).get("files", []),
                "changes": "沙箱内修复 base64.js clear()/example() 元素 id 引用",
                "project_dir": str(sandbox.copy_dir),
            }
            release_agent = ReleaseAgent(
                provider=provider, code=code_meta, test=test.get("metadata") or {}
            )
            artifact = release_agent.release(code_meta, test.get("metadata") or {})
            version = artifact.version

            # 真实 build: zip 打包沙箱副本 (证据产物)
            DIST_DIR.mkdir(parents=True, exist_ok=True)
            zip_name = f"devtoolbox-{version}.zip"
            zip_path = DIST_DIR / zip_name
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in sorted((sandbox.copy_dir).rglob("*")):
                    if f.is_file() and ".git" not in f.parts:
                        zf.write(f, arcname=f.relative_to(sandbox.copy_dir).as_posix())
            zip_size = zip_path.stat().st_size
            log(f"[release] built {zip_path} ({zip_size} bytes)")

            metadata = artifact.to_dict()
            metadata["artifact_refs"] = [code.get("id", ""), test.get("id", "")]
            metadata["package"] = {
                "name": "devtoolbox",
                "type": "zip",
                "files": [str(zip_path)],
                "size_bytes": zip_size,
            }
            metadata["build_result"] = {
                "status": "success",
                "command": f"python3 zipfile build -> {zip_name}",
            }
            recorder.stage_done("COMPLETED",
                                f"version={version} package={zip_name} ({zip_size}B)")
            return {
                "artifact_type": "release",
                "ref": f"file:///{zip_path}",
                "metadata": metadata,
            }
        except Exception as exc:  # noqa: BLE001
            recorder.add_error("release", exc)
            recorder.stage_done("FAILED", str(exc))
            raise

    return fixed_id(run, A_RELEASE)


# ------------------------------------------------------------------ 收集/验收


def collect_events(event_store: Any, recorder: Recorder) -> None:
    for type_, count in sorted(event_store.count_by_type().items()):
        recorder.events[type_] = count


def collect_artifacts(wf_lifecycle: Any, recorder: Recorder) -> None:
    for aid in (A_TASK, A_CODE, A_TEST, A_RELEASE):
        try:
            art = wf_lifecycle.registry.get(aid)
        except Exception as exc:  # noqa: BLE001 — NotFoundError
            recorder.add_artifact({"id": aid, "status": "MISSING",
                                   "note": str(exc)[:200]})
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


def acceptance(recorder: Recorder, copy_dir: str,
               source_hashes: dict[str, str], wf_lifecycle: Any) -> dict[str, Any]:
    """验收: Existing Project → Task → Code Change → Test Pass → Release 全链。"""
    checks: dict[str, Any] = {}

    # 1. Artifact 链全 VALIDATED
    validated = {
        a["id"]: (a["status"] or "").upper() == "VALIDATED"
        for a in recorder.artifacts
    }
    checks["artifact_chain_all_validated"] = all(validated.values())
    checks["artifact_statuses"] = {
        k: ("VALIDATED" if v else "NOT-VALIDATED") for k, v in validated.items()
    }

    # 2. Stage 全 COMPLETED
    stages_ok = all(s["status"] == "COMPLETED" for s in recorder.stages)
    checks["stages_all_completed"] = stages_ok
    checks["stage_statuses"] = {
        f"{s['workflow']}/{s['stage']}": s["status"] for s in recorder.stages
    }

    # 3. Test 真实通过 (Tester 产物)
    test_meta = next((a for a in recorder.artifacts if a["id"] == A_TEST), None)
    checks["test_artifact_validated"] = test_meta is not None and \
        (test_meta["status"] or "").upper() == "VALIDATED"

    # 4. 沙箱内修复真实生效 (副本文件内容断言)
    copy = Path(copy_dir)
    fixed = copy / "js" / "tools" / "base64.js"
    if fixed.is_file():
        content = fixed.read_text(encoding="utf-8")
        checks["sandbox_fix_no_stale_refs"] = all(
            f"getElementById('{s}')" not in content
            for s in ("base-input", "base-output", "base-mode")
        )
        checks["sandbox_fix_has_b64_refs"] = all(
            f"getElementById('{s}')" in content
            for s in ("b64-input", "b64-output", "b64-mode")
        )
        checks["sandbox_fix_example_key"] = "'#b64-input'" in content
        checks["sandbox_base64_syntax"] = _node_check(fixed)
    else:
        checks.update({
            "sandbox_fix_no_stale_refs": False,
            "sandbox_fix_has_b64_refs": False,
            "sandbox_fix_example_key": False,
            "sandbox_base64_syntax": False,
        })

    # 5. 真实源零修改 (生产保护铁律)
    unchanged, changed = hash_project_unchanged(SOURCE_PROJECT, source_hashes)
    checks["source_project_unchanged"] = unchanged
    checks["source_changed_files"] = changed

    # 6. Release 产物存在
    zips = sorted(DIST_DIR.glob("*.zip"))
    checks["release_zip_exists"] = len(zips) > 0
    checks["release_zips"] = [str(z.name) for z in zips]

    # 7. 审批门演示: release gate APPROVED (S9-001)
    gates = wf_lifecycle.list_approvals() if hasattr(wf_lifecycle, "list_approvals") else []
    if gates:
        gate = gates[-1]
        recorder.add_approval({
            "id": gate.id, "stage_id": gate.stage_id,
            "workflow_id": gate.workflow_id,
            "status": str(gate.status.value),
            "reviewer": gate.reviewer, "comment": gate.comment,
        })
    checks["approval_gate_approved"] = any(
        g["status"] == "approved" for g in recorder.approvals
    )
    checks["approval_gates"] = recorder.approvals

    all_ok = (
        checks["artifact_chain_all_validated"]
        and checks["stages_all_completed"]
        and checks["test_artifact_validated"]
        and checks["sandbox_fix_no_stale_refs"]
        and checks["sandbox_fix_has_b64_refs"]
        and checks["sandbox_fix_example_key"]
        and checks["sandbox_base64_syntax"]
        and checks["source_project_unchanged"]
        and checks["release_zip_exists"]
        and checks["approval_gate_approved"]
    )
    checks["all_pass"] = bool(all_ok)
    return checks


def _node_check(path: Path) -> bool:
    try:
        proc = subprocess.run(["node", "--check", str(path)],
                              capture_output=True, text=True, timeout=30)
        return proc.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# ------------------------------------------------------------------ 主流程


def main() -> int:
    started = _now()
    log(f"S9-005 Real Project Pilot start (model={MODEL})")
    log(f"source project={SOURCE_PROJECT} (只读输入, 零修改)")

    recorder = Recorder()
    provider = build_provider(recorder)

    # 1. org + 注册 (S9-004)
    store, event_store, logger, wf_lifecycle, adoption = setup_org()
    summary = register_project(adoption)
    adoption_dump = dump_adoption(adoption, summary)

    # 2. 沙箱副本 + 源 hash 基线
    sandbox, copy_dir, source_hashes = make_sandbox()

    # 3. 任务 artifact + workflow
    wf, stages = build_workflow(wf_lifecycle)
    register_task_artifact(wf_lifecycle)

    # 4. 执行 (DevTestLoopRunner ≤2 修复轮; Release 前人工审批门)
    from exec.tester import make_workflow_executor
    from org.workflow import DevTestLoopRunner, WorkflowStatus

    execs = {
        "developer": make_dev_executor(provider, recorder, sandbox, adoption_dump["snapshot"]),
        "tester": make_tester_executor(provider, recorder),
        "devops": make_release_executor(provider, recorder, sandbox),
    }
    runner = DevTestLoopRunner(
        wf_lifecycle, executor=make_workflow_executor(execs), logger=logger,
        max_repair_rounds=2,
    )
    log("[run] WF-S9-PILOT start (development→testing→release, 真实 v4-pro)")
    wf1 = runner.run(WF_ID)
    log(f"[run] WF-S9-PILOT -> {wf1.status.value}")
    if wf1.status == WorkflowStatus.PAUSED:
        # 人工审批门 (S9-001): release COMPLETED 后 PENDING → 演示 approve
        gates = wf_lifecycle.list_approvals()
        gate = gates[-1] if gates else None
        if gate is not None:
            log(f"[approval] gate {gate.id} {gate.status.value} (stage {gate.stage_id}) "
                f"— 人工审批放行 (演示 Console 审批流)")
            updated, wf2 = wf_lifecycle.approve_approval(
                gate.id,
                reviewer="s9-005-pilot",
                comment="沙箱内测试通过 + 真实源零修改, 允许发布 (演示人工审批)",
                source="console",
            )
            log(f"[approval] gate {updated.id} -> {updated.status.value}")
            wf_final = runner.run(WF_ID)
            log(f"[run] WF-S9-PILOT (approve 后) -> {wf_final.status.value}")
        else:
            recorder.add_error("approval", "workflow PAUSED but no approval gate found")
            wf_final = wf1
    else:
        wf_final = wf1

    # 5. 收集 + 验收
    collect_artifacts(wf_lifecycle, recorder)
    collect_events(event_store, recorder)
    checks = acceptance(recorder, copy_dir, source_hashes, wf_lifecycle)
    return finalize(recorder, adoption_dump, started, wf_final.status.value, checks)


def finalize(recorder: Recorder, adoption_dump: dict[str, Any],
             started: str, final_status: str, checks: dict[str, Any]) -> int:
    report = {
        "task": "S9-005 Real Project Pilot — DevToolBox",
        "model": MODEL,
        "started_at": started,
        "finished_at": _now(),
        "final_workflow_status": final_status,
        "adoption": adoption_dump,
        "bug_target": BUG_TARGET,
        "task_text": TASK_TEXT,
        "stages": recorder.stages,
        "calls": recorder.calls,
        "artifacts": recorder.artifacts,
        "approvals": recorder.approvals,
        "events_by_type": recorder.events,
        "totals": recorder.totals(),
        "errors": recorder.errors,
        "acceptance": checks,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / "s9-005-pilot.json"
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
