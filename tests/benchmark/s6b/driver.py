#!/usr/bin/env python3
"""benchmark_s6b/driver.py — Sprint 6.5 生产 Benchmark 驱动 (27 次真实 v4-pro 执行)。

全链: 9 任务 × 3 runs, 每 run 独立物化项目 (模板 + 任务种子) →
      EmployeeExecutor.execute (Employee → Capability → AgentRuntime → v4-pro →
      Sandbox → Validation → Artifacts → Experience) → 5 维评分。

5 维评分 (0/1, 全部来自真实产物, 禁手工修改):
  1. patch 生成:   PATCH artifact 文件非空 (沙箱内真实 git diff)
  2. patch 有效:   执行链 SUCCESS 且 patch 非空 (apply 成功无异常)
  3. 沙箱测试通过:  TEST_RESULT artifact 无 [FAIL] 且含 [PASS] command (unittest 全绿)
  4. report 完整:   REPORT artifact 文件非空
  5. experience 保存: ContextExperienceStore 记录数增加 (成功/失败都记录)

成本: usage.estimated_cost_usd (OpenAIProvider 费率估算, 与 6.2 闭环同口径)。

CLI:
  python3 driver.py --precheck        # 离线: key + 模板绿 + 各任务种子预期失败
  python3 driver.py --run [--task T1] [--limit N]   # 真实执行 (可续跑)
  python3 driver.py --summary         # 从 results JSON 汇总 5 维统计
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
import traceback
from pathlib import Path

REPO = Path("/Users/Shared/work/ai-software-factory")
sys.path.insert(0, str(REPO / "factory-exec"))

from exec.employee_executor import EmployeeExecutor  # noqa: E402
from exec.experience_ctx import ContextExperienceStore  # noqa: E402
from exec.models import ArtifactType  # noqa: E402
from exec.providers.openai import OpenAIProvider  # noqa: E402
from exec.store import ExecStore  # noqa: E402

from tasks import TASKS, get_task  # noqa: E402

# ---------------------------------------------------------------- 常量

MODEL = "deepseek-v4-pro"
BASE_URL = "https://api.deepseek.com/v1/chat/completions"
VALIDATION_CMD = "PYTHONPATH=. python3 -m unittest discover -s tests -v"
RUNS_PER_TASK = 3

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "project_template"
RESULTS_PATH = HERE / "results" / "sprint6.5-benchmark-results.json"
LOG_PATH = Path("/tmp/s6b_bench.log")

BASE_RUNS = Path("/tmp/s6b_runs")

#: key 来源 (进程内注入, 命令行禁明文)
ENV_FILE = Path.home() / ".hermes" / ".env"
ENV_KEY_NAME = "DEEPSEEK_API_KEY"


# ---------------------------------------------------------------- 工具

def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def load_env_key() -> str:
    """从 ~/.hermes/.env 读 DEEPSEEK_API_KEY (不打印 key 本身)。"""
    if not ENV_FILE.exists():
        return ""
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(ENV_KEY_NAME + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


class _Employee:
    """duck-typed Employee (id/name/capabilities/role_ids — EmployeeExecutor 契约)。"""

    id = "E-bench-dev"
    name = "Benchmark Developer"
    capabilities = ["python", "debugging", "testing"]
    role_ids = ["developer"]


def run_unittest(proj: Path) -> tuple[bool, str]:
    """沙箱同款验证命令 (离线判定用)。"""
    import subprocess

    proc = subprocess.run(
        VALIDATION_CMD,
        shell=True,
        cwd=str(proj),
        capture_output=True,
        text=True,
        timeout=90,
    )
    out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
    return proc.returncode == 0, out.strip()[-800:]


def seed_project(run_dir: Path, task: dict) -> Path:
    """模板副本 + 任务种子 → 每 run 独立项目 (work_root 与项目分离)。"""
    proj = run_dir / "project"
    shutil.copytree(TEMPLATE, proj)
    for rel, content in task["seed_files"].items():
        p = proj / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return proj


def exp_count(exp_dir: Path) -> int:
    try:
        return ContextExperienceStore(exp_dir).count()
    except Exception:  # noqa: BLE001 — 经验文件损坏/缺失 → 0
        return 0


def _read(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""


def score_result(result, store_dir: Path, exp_dir: Path, exp_before: int) -> dict:
    """ExecutionResult + 落盘产物 → 5 维评分 (全部真实产物)。"""
    dims = {
        "patch_gen": 0,
        "patch_valid": 0,
        "test_pass": 0,
        "report": 0,
        "experience": 0,
    }
    if result is None:
        return dims
    patch_text = ""
    test_text = ""
    report_text = ""
    for art in result.artifacts:
        if art.type is ArtifactType.PATCH:
            patch_text = _read(art.path)
        elif art.type is ArtifactType.TEST_RESULT:
            test_text = _read(art.path)
        elif art.type is ArtifactType.REPORT:
            report_text = _read(art.path)
    has_patch = bool(patch_text.strip())
    if has_patch:
        dims["patch_gen"] = 1
    if result.status.value == "success" and has_patch:
        dims["patch_valid"] = 1
    if test_text and "[FAIL]" not in test_text and "[PASS] command:" in test_text:
        dims["test_pass"] = 1
    if bool(report_text.strip()):
        dims["report"] = 1
    if exp_count(exp_dir) > exp_before:
        dims["experience"] = 1
    return dims


def run_once(task: dict, run_idx: int) -> dict:
    """单次真实执行 (EmployeeExecutor 全链) → 记录 dict。"""
    run_dir = BASE_RUNS / task["id"] / f"run{run_idx}"
    run_dir.mkdir(parents=True, exist_ok=True)
    proj = seed_project(run_dir, task)
    store_dir = run_dir / "store"
    exp_dir = run_dir / "exp"
    work = run_dir / "work"
    store_dir.mkdir(exist_ok=True)
    exp_dir.mkdir(exist_ok=True)
    work.mkdir(exist_ok=True)
    exp_before = exp_count(exp_dir)

    provider = OpenAIProvider(model=MODEL, base_url=BASE_URL, timeout=240)
    executor = EmployeeExecutor(
        provider,
        store=ExecStore(store_dir),
        validation_command=VALIDATION_CMD,
        work_root=work,
        experience_store=exp_dir,
    )
    rec: dict = {
        "task_id": task["id"],
        "level": task["level"],
        "title": task["title"],
        "run": run_idx,
        "model": MODEL,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    t0 = time.monotonic()
    error = ""
    try:
        result = executor.execute(
            _Employee(),
            task_id=task["id"],
            objective=task["objective"],
            project_dir=proj,
            requirement=task["requirement"],
            role_id="developer",
        )
        rec["result_id"] = result.id
        rec["request_id"] = result.request_id
        rec["status"] = result.status.value
        rec["usage"] = dict(result.usage)
        rec["cost_usd"] = result.usage.get("estimated_cost_usd")
        rec["report_head"] = result.report[:300]
        rec["dims"] = score_result(result, store_dir, exp_dir, exp_before)
        # 证据: 测试输出头 (沙箱 unittest 输出)
        for art in result.artifacts:
            if art.type is ArtifactType.TEST_RESULT:
                rec["test_head"] = _read(art.path)[:300]
                break
        if result.error:
            rec["error"] = result.error[:500]
    except Exception as exc:  # noqa: BLE001 — 单 run 失败安全, 记录不中断
        error = f"{type(exc).__name__}: {exc}"[:800]
        traceback.print_exc()
    rec["duration_s"] = round(time.monotonic() - t0, 3)
    if error:
        rec["error"] = error
        rec["status"] = "exception"
        rec["dims"] = score_result(None, store_dir, exp_dir, exp_before)
    rec["score"] = sum(rec.get("dims", {}).values())
    return rec


# ---------------------------------------------------------------- 主流程

def load_results() -> list[dict]:
    if RESULTS_PATH.exists():
        try:
            return json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
    return []


def save_results(records: list[dict]) -> None:
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {
            "sprint": "6.5",
            "model": MODEL,
            "base_url": BASE_URL,
            "validation_command": VALIDATION_CMD,
            "runs_per_task": RUNS_PER_TASK,
            "scoring": (
                "patch_gen/patch_valid/test_pass/report/experience — 全部来自真实产物 "
                "(PATCH 文件 / 执行状态 / TEST_RESULT 输出 / REPORT 文件 / 经验库计数增量)"
            ),
            "cost_note": "usage.estimated_cost_usd = OpenAIProvider 费率估算 (gpt-4o 代理费率, 与 6.2 闭环同口径); 真实计费以 DeepSeek 账单为准",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        "runs": records,
    }
    tmp = RESULTS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, RESULTS_PATH)


def precheck() -> int:
    """离线预检: key / 模板绿 / 各任务种子预期失败 (禁 mock, 真实 unittest)。"""
    problems = []
    key = load_env_key()
    if not key:
        problems.append("DEEPSEEK_API_KEY 缺失 (~/.hermes/.env)")
    else:
        log(f"key 就绪: {ENV_KEY_NAME} 已注入 (长度 {len(key)}, 不打印内容)")
    ok, out = run_unittest(TEMPLATE)
    if not ok:
        problems.append(f"模板基线测试未全绿: {out}")
    else:
        log("模板基线: 16 测试全绿 ✅")
    for task in TASKS:
        tmp = Path("/tmp/s6b_precheck") / task["id"]
        if tmp.exists():
            shutil.rmtree(tmp)
        proj = seed_project(tmp, task)
        ok, out = run_unittest(proj)
        if ok:
            problems.append(f"{task['id']}: 种子未产生预期失败 (测试竟然通过) — 种子无效!")
        else:
            log(f"{task['id']} (L{task['level']}): 种子预期失败确认 ✅ — {task['pre_fail']}")
    if problems:
        log("预检失败:\n" + "\n".join("  - " + p for p in problems))
        return 1
    log("预检全部通过 ✅")
    return 0


def run_benchmark(task_filter: str | None = None, limit: int | None = None) -> int:
    os.environ["OPENAI_API_KEY"] = load_env_key()
    if not os.environ.get("OPENAI_API_KEY"):
        log("错误: 无 API key, 中止")
        return 1
    records = load_results()
    done = {(r["task_id"], r["run"]) for r in records}
    tasks = [get_task(task_filter)] if task_filter else TASKS
    total = 0
    for task in tasks:
        for run_idx in range(RUNS_PER_TASK):
            if (task["id"], run_idx) in done:
                log(f"跳过 (已存在): {task['id']}/run{run_idx}")
                continue
            if limit is not None and total >= limit:
                log(f"已达 limit={limit}, 停止")
                return 0
            log(f"▶ 执行 {task['id']} (L{task['level']}) run{run_idx}/2 — {task['title']}")
            rec = run_once(task, run_idx)
            dims = rec.get("dims", {})
            log(
                f"  → status={rec.get('status')} score={rec['score']}/5 "
                f"[patch={dims.get('patch_gen')} valid={dims.get('patch_valid')} "
                f"test={dims.get('test_pass')} report={dims.get('report')} "
                f"exp={dims.get('experience')}] {rec.get('duration_s')}s "
                f"cost=${rec.get('cost_usd')}"
            )
            if rec.get("error"):
                log(f"  error: {rec['error'][:200]}")
            records.append(rec)
            save_results(records)
            total += 1
    log(f"完成: {len(records)} runs 已记录 → {RESULTS_PATH}")
    return 0


def summary() -> None:
    records = load_results()
    if not records:
        print("无结果")
        return
    by_task: dict[str, list[dict]] = {}
    for r in records:
        by_task.setdefault(r["task_id"], []).append(r)
    print(f"\n=== Sprint 6.5 Benchmark 汇总 ({len(records)} runs, {MODEL}) ===")
    print(f"{'任务':<4}{'级':<4}{'Runs':<6}{'成功(patch+test)':<18}{'均分':<6}{'均耗时':<8}{'均成本'}")
    for task in TASKS:
        rs = by_task.get(task["id"], [])
        if not rs:
            continue
        full = sum(1 for r in rs if r["dims"]["patch_gen"] and r["dims"]["test_pass"])
        avg_score = sum(r["score"] for r in rs) / len(rs)
        avg_dur = sum(r["duration_s"] for r in rs) / len(rs)
        avg_cost = sum(r.get("cost_usd") or 0 for r in rs) / len(rs)
        print(
            f"{task['id']:<4}L{task['level']:<3}{len(rs):<6}"
            f"{full}/{len(rs)}            {avg_score:.1f}    "
            f"{avg_dur:6.1f}s  ${avg_cost:.5f}"
        )
    total_cost = sum(r.get("cost_usd") or 0 for r in records)
    total_tokens = sum(
        (r.get("usage") or {}).get("prompt_tokens", 0) + (r.get("usage") or {}).get("completion_tokens", 0)
        for r in records
    )
    print(f"\n总成本估算: ${total_cost:.5f} | 总 token: {total_tokens}")


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--precheck" in argv:
        sys.exit(precheck())
    if "--summary" in argv:
        summary()
        sys.exit(0)
    task_filter = None
    limit = None
    if "--task" in argv:
        task_filter = argv[argv.index("--task") + 1]
    if "--limit" in argv:
        limit = int(argv[argv.index("--limit") + 1])
    sys.exit(run_benchmark(task_filter, limit))
