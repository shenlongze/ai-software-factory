"""factory-exec/exec/benchmark/runner.py — Benchmark 执行框架 (Phase A+++++)。

样本 → factory-exec 执行链 → 记录 7 指标 + 五维评分:

执行链 (复用 factory-exec 组件, 同 AgentRuntime 核心):
  Sandbox (项目副本/空沙箱) → DeveloperAgent.work (Provider 真实调用)
    → patch 应用 (沙箱内) → verifier 判定 (纯 Python, 不依赖 LLM)

每样本记录 7 指标 (BenchmarkResult):
  1. success      → status (SUCCESS/FAILED) + verifier_passed
  2. token        → usage (provider usage 原样记录)
  3. cost         → cost_usd (usage.estimated_cost_usd; 无 → None, 不臆造)
  4. latency      → latency_s (真实计时)
  5. patch_quality→ 0-100 启发式 (可应用 40 + verifier 通过 40 + 最小性 10 + 有产物 10)
  6. human_intervention → 次数 (自动化判定全程 0; 人工协助场景 >0)
  7. 五维评分     → FiveDimScore (Understanding/Analysis/Implementation/
                    Validation/Communication, Level 1-3)

评分诚实原则 (无 LLM 幻觉):
- verifier 通过 → 五维全 2 (Level 2 独立完成简单任务 — 自动化证据);
- verifier 未过 → 全 1 (Level 1 未达);
- Level 3 (生产级) 只由人工评审确认 (runner 不自动判 3, 报告标注待核验)。

BLOCKED 语义: 预检发现 Provider key 缺失 → 全部样本 status=BLOCKED +
blocked_reason (ProviderError 消息), 不调 LLM, 不 mock 当能力证明 —
诚实标注「模型待 key」, key 一到立即重跑 (无需改代码)。

CLI: python -m exec.benchmark.runner --check   (预检: key + 样本集完整性)
     python -m exec.benchmark.runner --run --provider openai [--runs 1]
     python -m exec.benchmark.runner --run --provider openai \\
         --base-url https://api.deepseek.com/v1/chat/completions --model deepseek-chat \\
         --input-rate-per-1k 0.00027 --output-rate-per-1k 0.0011   (DeepSeek 端点)

DeepSeek 端点 (OpenAI 兼容): OpenAIProvider 是通用 Chat Completions adapter —
base_url/model/费率均可配, provider_id 仍为 openai (适配器身份), model 记录
真实端点模型 (deepseek-chat)。key 用 OPENAI_API_KEY 承载 (DeepSeek key 导出后
运行, 禁明文); 费率按 deepseek-chat 定价估算成本 (仅估算, 非计费)。
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from ..developer import DeveloperAgent, DeveloperError, FailureReason, classify_failure
from ..provider import ProviderConfigChecker, ProviderInterface
from ..sandbox import Sandbox
from . import verifiers as benchmark_verifiers
from .models import (
    BenchmarkReport,
    BenchmarkResult,
    BenchmarkSample,
    FiveDimScore,
    SampleKind,
    SampleStatus,
)
from .samples import ALL_SAMPLES

#: Bug/Feature 样本的项目源目录 (只读输入; 沙箱副本创建后原项目零接触)。
#: 可用环境变量 BENCHMARK_MARKPAD_DIR 覆盖 (CI/其他机器)。
DEFAULT_PROJECT_DIR = Path(os.environ.get("BENCHMARK_MARKPAD_DIR", "/Users/Shared/work/markpad"))

#: 最小性阈值: 改动文件数 ≤ 3 → 满分档; ≤ 6 → 半档; 更多 → 0 分档
_MIN_FILES_FULL = 3
_MIN_FILES_HALF = 6


def _env_float(name: str) -> float | None:
    """环境变量 → float (缺失/非法 → None; CLI 缺省值解析用)。"""
    raw = os.environ.get(name)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


# ================================================================ 工具函数

def estimate_cost_usd(usage: dict[str, Any]) -> float | None:
    """usage → 美元成本 (适配器已附 estimated_cost_usd → 直接取; 无 → None)。

    诚实原则: 无成本数据 → None (不臆造费率); 由报告标注「成本待真实数据」。
    """
    if not usage:
        return None
    try:
        est = usage.get("estimated_cost_usd")
        if est is not None:
            return round(float(est), 6)
    except (TypeError, ValueError):
        return None
    return None


def patch_stats(diff_text: str) -> dict[str, int]:
    """unified diff 文本 → 统计: 改动文件数 / 插入行 / 删除行。

    解析 `diff --git a/... b/...` 头与 +/- 行 (不依赖 git 命令)。
    """
    files, insertions, deletions = 0, 0, 0
    seen: set[str] = set()
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            files += 1
        elif line.startswith("+") and not line.startswith("+++"):
            insertions += 1
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1
    return {"files": files, "insertions": insertions, "deletions": deletions}


def patch_quality_score(
    *,
    applied: bool,
    verifier_passed: bool,
    files_touched: int,
    has_patch: bool,
) -> int:
    """patch 质量 0-100 (确定性启发式, 无 LLM):

    - 可应用 (patch apply 成功): 40
    - verifier 通过 (修复有效): 40
    - 最小性 (改动文件数 1-3 → 10; 4-6 → 5; 0 或无产物 → 0): 10
    - 有产物 (Agent 产出 patch 或沙箱存在变更): 10
    """
    score = 0
    if applied:
        score += 40
    if verifier_passed:
        score += 40
    # 最小性仅在有实际改动时计分 (files_touched=0 且无产物 → 0 分, 不误加分)
    if 0 < files_touched <= _MIN_FILES_FULL:
        score += 10
    elif 0 < files_touched <= _MIN_FILES_HALF:
        score += 5
    if has_patch:
        score += 10
    return max(0, min(100, score))


def provisional_score(passed: bool) -> FiveDimScore:
    """五维评分 (Level 1-3, 自动化启发式 — 待人工核验):

    - verifier 通过 → 全 2 (Level 2 独立完成: 常见任务无人工干预);
    - verifier 未过 → 全 1 (Level 1 未达);
    - Level 3 (生产级) 由人工评审确认 (runner 不自动判 3)。
    """
    if passed:
        return FiveDimScore(understanding=2, analysis=2, implementation=2,
                            validation=2, communication=2)
    return FiveDimScore(understanding=1, analysis=1, implementation=1,
                        validation=1, communication=1)


def model_name(provider: Any) -> str:
    """Provider 模型名 (公开属性优先, 私有回退; 无 → 空, 不报错)。"""
    return str(getattr(provider, "model", "") or getattr(provider, "_model", ""))


# ================================================================ Runner

class BenchmarkRunner:
    """Benchmark 执行框架: 样本集 → 执行链 → 7 指标 + 五维评分 → 报告。

    构造:
    - provider: ProviderInterface (真实 Adapter; 无 key → run_all 全 BLOCKED)。
    - samples: 样本列表 (缺省 ALL_SAMPLES: 5 Bug + 3 Feature + 1 Greenfield)。
    - project_dir: Bug/Feature 样本的项目源 (缺省 markpad; 只读输入)。
    - work_root: 沙箱父目录 (None → 系统临时目录; 测试注入 tmp_path)。
    - runs: 每样本执行次数 (Provider 对比/稳定性; 缺省 1)。
    - env: 配置检查环境 (缺省 os.environ; 测试注入空 dict 模拟无 key)。
    """

    def __init__(
        self,
        provider: ProviderInterface,
        *,
        samples: list[BenchmarkSample] | None = None,
        project_dir: str | Path | None = None,
        work_root: str | Path | None = None,
        runs: int = 1,
        git_bin: str = "git",
        env: dict[str, str] | None = None,
    ) -> None:
        self._provider = provider
        self._samples = list(samples) if samples else list(ALL_SAMPLES)
        self._project_dir = Path(project_dir) if project_dir else DEFAULT_PROJECT_DIR
        self._work_root = Path(work_root) if work_root else None
        self._runs = max(1, int(runs))
        self._git_bin = git_bin
        self._env = env
        self._developer = DeveloperAgent(provider)

    # ------------------------------------------------------------ 预检

    def precheck(self) -> tuple[bool, str]:
        """Provider key 可用性预检 (不调网络; 配置检查是前置门槛非能力证明)。

        返回 (ok, reason): ok=True → key 就绪; False → 缺失说明 (报告 BLOCKED 原因)。
        """
        checker = ProviderConfigChecker(env=self._env)
        statuses = checker.check(self._provider.provider_id)
        missing = [s for s in statuses if not s.configured]
        if missing:
            return False, missing[0].message
        return True, ""

    def validate_samples(self) -> list[str]:
        """样本集完整性预检: verifier 已注册 + 样本字段合法 → 问题列表 (空 = 完整)。"""
        problems: list[str] = []
        seen: set[str] = set()
        for s in self._samples:
            if s.id in seen:
                problems.append(f"duplicate sample id: {s.id}")
            seen.add(s.id)
            if not s.objective.strip():
                problems.append(f"{s.id}: objective 为空")
            if benchmark_verifiers.get(s.verifier_id) is None:
                problems.append(f"{s.id}: verifier 未注册: {s.verifier_id}")
            if s.kind is not SampleKind.GREENFIELD:
                for rel in s.project_files:
                    if not (self._project_dir / rel).exists():
                        problems.append(f"{s.id}: 项目文件缺失: {rel} (项目: {self._project_dir})")
        return problems

    # ------------------------------------------------------------ 执行

    def run_all(self) -> BenchmarkReport:
        """全样本集执行 (预检无 key → 全部 BLOCKED, 诚实不假装)。"""
        ok, reason = self.precheck()
        report = BenchmarkReport(
            provider_id=getattr(self._provider, "provider_id", ""),
            model=model_name(self._provider),
            blocked=not ok,
            blocked_reason=reason if not ok else "",
        )
        problems = self.validate_samples()
        if problems:
            report.blocked = True
            report.blocked_reason = (
                f"{report.blocked_reason}; " if report.blocked_reason else ""
            ) + "样本集校验失败: " + "; ".join(problems)
        for sample in self._samples:
            for run_i in range(self._runs):
                report.results.append(
                    self.run_sample(
                        sample,
                        blocked=not ok,
                        blocked_reason=report.blocked_reason,
                        run=run_i,
                    )
                )
        return report

    def run_sample(
        self,
        sample: BenchmarkSample,
        *,
        blocked: bool = False,
        blocked_reason: str = "",
        run: int = 0,
    ) -> BenchmarkResult:
        """单样本执行 → BenchmarkResult (失败安全: 全部路径不抛)。

        run: 执行序号 (0-based; 报告 result.id 区分多次执行)。
        """
        result = BenchmarkResult(
            sample_id=sample.id,
            kind=sample.kind,
            verifier_id=sample.verifier_id,
            provider_id=getattr(self._provider, "provider_id", ""),
            model=model_name(self._provider),
        )
        if blocked:
            result.status = SampleStatus.BLOCKED
            result.blocked_reason = blocked_reason or "no provider key configured"
            return result

        # 1. 沙箱 (greenfield → 空项目; 否则 markpad 项目副本)
        try:
            sandbox, sandbox_root = self._make_sandbox(sample)
        except Exception as exc:  # noqa: BLE001 — 失败安全
            result.status = SampleStatus.FAILED
            result.error = f"sandbox error: {exc}"[:1000]
            return result

        # 2. Developer 执行 (真实 Provider 调用; 计时; 空 patch 重试 1 次 +
        #    verifier 反馈循环 ≤2 轮修复; 空内容/无解析由 work 内建重试)
        started = time.monotonic()
        output = None
        last_error: str = ""
        retried = False
        usage_acc: dict[str, Any] = {}
        feedback: str = ""
        passed: bool | None = None
        detail = ""
        applied = False
        # 验证循环总尝试上限: 1 次初始 + 2 轮 verifier 反馈修复 (任务约束 ≤2 轮)
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                output = self._developer.work(
                    request=sample,  # duck-typed: objective/requirement
                    project_context=self._project_context(sample),
                    sandbox_path=str(sandbox_root),
                    source_files=sample.source_files or None,
                    extra_instruction=feedback,
                )
            except DeveloperError as exc:
                # work 已内建空内容/无解析重试; 其余失败 (Provider 层/操作锚点/
                # 语法) 是环境或能力判定 — 不重试 (重试是放水/掩盖环境问题)
                last_error = str(exc)
                output = None
                break
            usage_acc = self._accumulate_usage(usage_acc, output.usage)
            if output.patch_text.strip() == "":
                # 空 patch (NO_CHANGE/空操作列表) — Benchmark 样本全部要求改代码,
                # 空 patch 一律视为失败, 重试 1 次 (带提示, 非 verifier 放水)
                if attempt == 0:
                    last_error = "provider returned empty patch (no code change)"
                    output = None
                    retried = True
                    feedback = (
                        "上次输出未包含任何代码修改 (空 patch)。本任务要求修改代码, "
                        "请直接输出 <operations> 或 <patch>。"
                    )
                    continue
                last_error = "provider returned empty patch (no code change)"
                output = None
                break
            try:
                sandbox.apply_patch(output.patch_text)
                applied = True
            except Exception as exc:  # noqa: BLE001 — 失败安全
                last_error = f"patch apply failed: {exc}"[:1000]
                # 保持既有语义: apply 失败后仍跑 verifier (未修改文件 → False)
                fn = benchmark_verifiers.get(sample.verifier_id)
                if fn is not None:
                    try:
                        passed, detail = fn(sandbox_root, sample)
                    except Exception as exc2:  # noqa: BLE001 — verifier 异常转 FAIL
                        passed = False
                        detail = f"verifier error: {exc2}"
                break
            # verifier 判定 (纯 Python, 不依赖 LLM; 反馈 detail 不含 fix_hint)
            fn = benchmark_verifiers.get(sample.verifier_id)
            passed = None
            if fn is not None:
                try:
                    passed, detail = fn(sandbox_root, sample)
                except Exception as exc2:  # noqa: BLE001 — verifier 异常转 FAIL
                    passed = False
                    detail = f"verifier error: {exc2}"
            if passed:
                break
            if attempt < max_attempts - 1:
                # 验证循环: 反馈验收失败给 Developer, 下一轮基于当前沙箱状态再修
                feedback = (
                    f"你的修改未通过验收 (第 {attempt + 1} 轮, 最多 "
                    f"{max_attempts - 1} 轮自动修复)。\n"
                    f"验收反馈:\n{detail[:800]}\n"
                    "请分析失败原因并修复, 直接输出新的 <operations> 或 <patch>。"
                )
                continue
            last_error = f"verifier failed: {detail[:200]}"
            break

        result.latency_s = round(time.monotonic() - started, 3)
        result.usage = usage_acc
        result.cost_usd = estimate_cost_usd(usage_acc)
        result.verifier_passed = passed
        if detail:
            result.verifier_detail = detail[:500]

        if output is None:
            result.status = SampleStatus.FAILED
            result.error = (
                f"{last_error[:900]} (after 1 retry)" if retried else last_error
            )[:1000]
            result.score = provisional_score(False)
            result.patch_quality = 0
            # 失败必记结构化原因 (复盘循环归因: 空内容/hunk 不匹配/功能缺失)
            result.failure_reason = classify_failure(result.error)
            return result

        # 3. diff 统计 (已应用; 沙箱导出最终变更)
        diff_text = ""
        try:
            diff_text = sandbox.diff()
        except Exception:  # noqa: BLE001 — diff 失败不致命
            diff_text = ""

        # 4. 7 指标 + 五维评分
        stats = patch_stats(diff_text)
        result.patch_quality = patch_quality_score(
            applied=applied,
            verifier_passed=bool(passed),
            files_touched=stats["files"],
            # 有产物 = Agent 产出了 patch (即使未可应用) 或沙箱存在变更
            has_patch=bool(diff_text.strip() or output.patch_text.strip()),
        )
        result.score = provisional_score(bool(passed))
        # 自动化判定全程无需人工介入; 人工协助场景由调用方补录 (>0)
        result.human_intervention = 0
        result.status = (
            SampleStatus.SUCCESS if (applied and passed) else SampleStatus.FAILED
        )
        if result.status is SampleStatus.FAILED:
            result.error = (
                last_error or f"verifier failed: {detail[:200]}"
            )[:1000]
            result.failure_reason = (
                classify_failure(result.error) or FailureReason.VERIFIER_FAILED.value
            )
        return result

    # ------------------------------------------------------------ 内部

    @staticmethod
    def _accumulate_usage(acc: dict[str, Any], usage: dict[str, Any]) -> dict[str, Any]:
        """跨重试累计 usage (token/成本真实总花费; 非数值字段取末次)。"""
        out = dict(usage)
        for k, v in acc.items():
            if isinstance(v, (int, float)) and isinstance(out.get(k), (int, float)):
                out[k] = v + out[k]
        return out

    def _make_sandbox(self, sample: BenchmarkSample) -> tuple[Sandbox, Path]:
        """创建沙箱副本 → (sandbox, 副本根目录)。

        greenfield: 空项目源 (临时目录, create 完成后源即弃);
        其他: markpad 项目副本 (原项目零接触 — 沙箱铁律)。
        """
        if sample.kind is SampleKind.GREENFIELD:
            with tempfile.TemporaryDirectory(prefix="benchmark-greenfield-src-") as td:
                sandbox = Sandbox(Path(td), work_root=self._work_root, git_bin=self._git_bin)
                session = sandbox.create()
            return sandbox, Path(session.workspace_copy_path)
        if not self._project_dir.is_dir():
            raise FileNotFoundError(
                f"project dir not found: {self._project_dir} "
                "(set BENCHMARK_MARKPAD_DIR 指定项目目录)"
            )
        sandbox = Sandbox(self._project_dir, work_root=self._work_root, git_bin=self._git_bin)
        session = sandbox.create(project_files=sample.project_files or None)
        return sandbox, Path(session.workspace_copy_path)

    def _project_context(self, sample: BenchmarkSample) -> str:
        """项目上下文 (提示词素材; 不泄露 fix_hint)。"""
        if sample.kind is SampleKind.GREENFIELD:
            return "空项目目录 — 从零构建, 交付物直接放在沙箱根目录。"
        if sample.project_files:
            return (
                "沙箱内为项目副本 (已选择性复制以下路径, 其余项目文件不在沙箱内):\n- "
                + "\n- ".join(sample.project_files)
                + "\n相关源文件内容已内联在下方 Relevant source files 节 "
                "(模型无 shell 访问, 以内联代码为准)。"
            )
        return "项目文件在沙箱内, 请先浏览相关目录再动手。"


# ================================================================ CLI

def _print_report(report: BenchmarkReport) -> None:
    print(f"Benchmark report: {report.id}")
    print(f"  provider={report.provider_id} model={report.model or '(default)'}")
    print(f"  blocked={report.blocked} blocked_reason={report.blocked_reason or '-'}")
    print(f"  counts={report.counts} success_rate={report.success_rate} "
          f"total_cost_usd={report.total_cost_usd} avg_latency_s={report.avg_latency_s} "
          f"avg_score={report.avg_score}")
    for r in report.results:
        print(f"  [{r.kind.value:9s}] {r.sample_id:16s} {r.status.value:7s} "
              f"verifier={r.verifier_passed} pq={r.patch_quality} "
              f"score={r.score.average if r.score else '-'} "
              f"latency={r.latency_s}s cost={r.cost_usd} "
              f"{(r.blocked_reason or r.error or '')[:80]}")


def main(argv: list[str] | None = None) -> int:
    """CLI 入口: --check 预检 / --run 真实执行 (无 key → 全 BLOCKED, 退出码 0)。"""
    import argparse

    parser = argparse.ArgumentParser(prog="exec.benchmark.runner",
                                     description="AI Software Factory Benchmark runner")
    parser.add_argument("--check", action="store_true", help="预检: Provider key + 样本集完整性")
    parser.add_argument("--run", action="store_true", help="执行全部样本 (真实 Provider 调用)")
    parser.add_argument("--provider", default="openai", choices=["openai", "anthropic"],
                        help="Provider id (缺省 openai)")
    parser.add_argument("--runs", type=int, default=1, help="每样本执行次数")
    # OpenAI 兼容端点参数 (DeepSeek: base_url=https://api.deepseek.com/v1/chat/completions,
    # model=deepseek-chat; 费率按 deepseek-chat 定价估算成本)。支持环境变量覆盖
    # (BENCHMARK_BASE_URL/BENCHMARK_MODEL/BENCHMARK_INPUT_RATE_PER_1K/
    # BENCHMARK_OUTPUT_RATE_PER_1K) — 可复现运行, 命令不含 key 明文。
    parser.add_argument("--base-url", default=os.environ.get("BENCHMARK_BASE_URL"),
                        help="OpenAI 兼容端点完整 URL (缺省 api.openai.com)")
    parser.add_argument("--model", default=os.environ.get("BENCHMARK_MODEL"),
                        help="模型名 (DeepSeek: deepseek-chat)")
    parser.add_argument("--input-rate-per-1k", type=float,
                        default=_env_float("BENCHMARK_INPUT_RATE_PER_1K"),
                        help="输入成本估算费率 (美元/1K token; DeepSeek: 0.00027)")
    parser.add_argument("--output-rate-per-1k", type=float,
                        default=_env_float("BENCHMARK_OUTPUT_RATE_PER_1K"),
                        help="输出成本估算费率 (美元/1K token; DeepSeek: 0.0011)")
    args = parser.parse_args(argv)

    # 延迟导入 Provider Adapter (零副作用; 缺包 → 响亮错误)
    try:
        if args.provider == "anthropic":
            from ..providers.anthropic import AnthropicProvider
            provider = AnthropicProvider()
        else:
            from ..providers.openai import OpenAIProvider
            kwargs: dict[str, Any] = {}
            if args.base_url:
                kwargs["base_url"] = args.base_url
            if args.model:
                kwargs["model"] = args.model
            if args.input_rate_per_1k is not None:
                kwargs["input_rate_per_1k"] = args.input_rate_per_1k
            if args.output_rate_per_1k is not None:
                kwargs["output_rate_per_1k"] = args.output_rate_per_1k
            provider = OpenAIProvider(**kwargs)
    except Exception as exc:  # noqa: BLE001 — 依赖缺失响亮暴露
        print(f"provider init failed: {exc}")
        return 7

    runner = BenchmarkRunner(provider, runs=args.runs)
    problems = runner.validate_samples()
    if problems:
        print("样本集校验失败:")
        for p in problems:
            print(f"  ✗ {p}")
        return 3
    ok, reason = runner.precheck()
    print(f"Provider 预检: {'✓ 就绪' if ok else '✗ BLOCKED'} — {reason or 'key 已配置'}")
    print(f"样本集: {len(runner._samples)} 个样本 (5 Bug + 3 Feature + 1 Greenfield)")
    if args.check and not args.run:
        return 0
    if not ok:
        print("无 Provider key — 跳过真实执行, 全部样本 BLOCKED (诚实标注, key 一到重跑)")
        report = runner.run_all()
    else:
        report = runner.run_all()
    _print_report(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
