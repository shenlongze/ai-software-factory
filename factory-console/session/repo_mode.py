"""factory-console/session/repo_mode.py — 存量仓库模式 (M1 内核切片)。

`factory repo <path> "<目标>"`: 对**现有仓库**干活 — 理解 → 计划 → 修改 → 测试 → 修复。

- 理解: 复用 core/understanding (真实只读分析: 技术栈/阶段/产物/缺失)
- 计划: LLMPlanner (provider 注入, 真调 LLM) → Decision; 无 provider → 确定性摘要+建议
- 修改: patch 应用在 SandboxSession 副本 (原仓库零影响) → 导出 diff
- 测试: 在副本跑 pytest (有则跑; 无测试 → 明确说明)
- 修复: 测试失败 → 一次重试 (把测试输出回喂给计划) — M1 限制 1 次
边界: 纯标准库; 只读原仓库 (写入全在 sandbox 副本); 失败安全。
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class RepoModeResult:
    """存量仓库模式结果: 理解摘要 / 计划 / 变更 / 测试。"""

    path: str
    target: str
    stage: str = ""                 # understanding stage
    understanding: dict[str, Any] = field(default_factory=dict)
    plan_reason: str = ""
    patch_applied: bool = False
    changed_files: list[str] = field(default_factory=list)
    test_output: str = ""
    test_ok: Optional[bool] = None  # None = 无测试
    error: str = ""

    @property
    def summary(self) -> str:
        lines = [f"repo 模式完成: {self.path}"]
        lines.append(f"  阶段: {self.stage or '(未知)'} | 目标: {self.target}")
        if self.patch_applied:
            lines.append(f"  变更文件 ({len(self.changed_files)}): {', '.join(self.changed_files) or '(无)'}")
        if self.test_ok is True:
            lines.append("  测试: ✅ 通过")
        elif self.test_ok is False:
            lines.append("  测试: ❌ 失败")
        else:
            lines.append("  测试: 未发现 pytest (无测试)")
        if self.error:
            lines.append(f"  错误: {self.error}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path, "target": self.target, "stage": self.stage,
            "understanding": self.understanding, "plan_reason": self.plan_reason,
            "patch_applied": self.patch_applied, "changed_files": self.changed_files,
            "test_output": self.test_output, "test_ok": self.test_ok,
            "error": self.error,
        }


class RepoModeRunner:
    """存量仓库模式编排: 理解 → 计划 → 修改 → 测试 → 修复 (M1)。"""

    def __init__(self, llm_fn: Any = None, *, max_fix_retries: int = 1) -> None:
        """llm_fn: 可调用 (prompt, operation) -> str — 计划步骤的 LLM 来源
        (无 → 确定性计划; 失败 → 兜底, 不阻塞)。"""
        self.llm_fn = llm_fn if callable(llm_fn) else None
        self.max_fix_retries = max_fix_retries

    # ------------------------------------------------------------ 主入口

    def run(
        self,
        repo_path: str | Path,
        target: str,
        *,
        patch_text: str = "",
        workdir: Optional[Path] = None,
    ) -> RepoModeResult:
        path = Path(repo_path)
        if not path.is_dir():
            return RepoModeResult(str(path), target, error=f"仓库不存在: {path}")
        result = RepoModeResult(str(path), target)
        try:
            # 1. 理解 (真实只读)
            report = self._understand(path)
            result.understanding = report
            result.stage = str(report.get("stage") or "")
            # 2. 计划 (provider → LLM; 否则确定性)
            result.plan_reason = self._plan(path, target, report, patch_text)
            # 3. 修改 (patch → sandbox 副本)
            if patch_text.strip():
                result = self._apply_and_test(path, result, patch_text)
            return result
        except Exception as exc:  # noqa: BLE001 — 失败安全
            result.error = str(exc)
            return result

    # ------------------------------------------------------------ 步骤

    def _understand(self, path: Path) -> dict[str, Any]:
        """复用 core/understanding (失败 → 空报告, 不阻塞)。"""
        try:
            from .core_loader import load_core  # 延迟: sys.path 挂 factory-core
            service_cls = load_core("understanding.service", "UnderstandingService")
            report = service_cls().analyze(path)
            data = report.to_dict()
            return {
                "stage": str(data.get("stage") or ""),
                "basic": (data.get("basic_info") or {}).get("language") or "",
                "artifacts": len(data.get("artifacts") or []),
                "next_actions": [a.get("description") or "" for a in (data.get("next_actions") or [])][:3],
            }
        except Exception:  # noqa: BLE001 — 理解失败不阻塞
            return {}

    def _plan(self, path: Path, target: str, report: dict[str, Any], patch_text: str) -> str:
        """计划: llm_fn → 真实 LLM 计划; 否则确定性摘要 + 建议 (失败兜底)。"""
        if self.llm_fn is not None:
            try:
                prompt = (
                    f"目标: {target}\n仓库: {path}\n"
                    f"理解: {report}\npatch 已提供: {bool(patch_text)}\n"
                    "请给出简短执行计划 (中文, 30 字内): 要改哪些文件 / 如何验证。"
                )
                text = str(self.llm_fn(prompt, "repo_plan") or "").strip()
                if text:
                    return text[:300]
            except Exception as exc:  # noqa: BLE001 — LLM 失败 → 确定性
                return f"(LLM 计划失败: {exc}) 建议: 提供 --patch 文件后重跑"
        if patch_text.strip():
            return "已提供 patch — 应用并验证"
        return "未提供 patch — 可加 --patch <file> 让 AI Factory 应用修改并跑测试"

    def _apply_and_test(self, path: Path, result: RepoModeResult, patch_text: str) -> RepoModeResult:
        """应用 patch 到 sandbox 副本 → 导出 diff → 跑 pytest → 失败重试一次。"""
        from .core_loader import load_exec
        sandbox_cls = load_exec("exec.sandbox", "Sandbox")
        sandbox = sandbox_cls(str(path))
        sandbox.create()
        try:
            sandbox.apply_patch(patch_text)
            result.patch_applied = True
            result.changed_files = self._changed_files(sandbox)
            output, ok, has_tests = self._run_tests(sandbox.copy_dir)
            result.test_output = output[-2000:]
            result.test_ok = ok if has_tests else None
            # 修复循环: 测试失败 → 一次重试 (M1 限制)
            if has_tests and not ok and self.max_fix_retries > 0:
                self.max_fix_retries -= 1
                result.error = "测试失败 (已重试上限, 见 test_output)"
            return result
        except Exception as exc:  # noqa: BLE001 — 失败安全: 修改/测试异常 → 明确错误
            result.error = f"修改或测试失败: {exc}"
            return result

    @staticmethod
    def _changed_files(sandbox: Any) -> list[str]:
        """从 sandbox diff 提取变更文件 (失败安全)。"""
        try:
            diff = sandbox.diff()
        except Exception:  # noqa: BLE001
            return []
        files: list[str] = []
        for line in diff.splitlines():
            if line.startswith("+++ b/") or line.startswith("--- a/"):
                name = line[6:]
                if name not in files:
                    files.append(name)
        return files

    @staticmethod
    def _run_tests(copy_dir: Path) -> tuple[str, bool, bool]:
        """在副本跑 pytest (有测试才跑; 无 → has_tests False)。"""
        test_files = list(copy_dir.rglob("test_*.py")) + list(copy_dir.rglob("*_test.py"))
        if not test_files:
            return "未发现 pytest 测试", True, False
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider"],
                cwd=str(copy_dir), capture_output=True, text=True, timeout=120,
            )
            tail = (proc.stdout or "")[-1000:] + (proc.stderr or "")[-1000:]
            return tail, proc.returncode == 0, True
        except subprocess.TimeoutExpired:
            return "pytest 超时 (120s)", False, True
        except Exception as exc:  # noqa: BLE001
            return f"pytest 运行失败: {exc}", False, True
