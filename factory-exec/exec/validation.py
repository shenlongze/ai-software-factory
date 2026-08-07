"""factory-exec/exec/validation.py — Validation 最小 (语法检查/简单测试命令)。

设计依据 (docs/architecture/phase-a-execution-mvp-design.md §4/§6):
- 允许范围: ✅ 沙箱内测试执行 / 分析 / 报告生成 (不改外部状态) — 可自动。
- Validation 只负责检查 (门禁, 无执行权 — 设计 §2 执行权归属)。
- 失败语义: 语法错误/测试命令失败 → passed=False + 输出 (供审批人判断,
  也供 Experience 记录失败原因)。

实现 (KISS, 确定性优先):
- syntax_check(): 进程内 ast.parse 全部 .py 文件 (零子进程, 确定性快;
  语法错误逐文件记录)。
- run_command(cmd): 沙箱内跑测试命令 (subprocess, cwd=副本, 捕获输出,
  rc 非 0 → 失败; timeout 防御)。command=None → 跳过 (只做语法检查)。
- validate(): 语法检查 + 可选命令 → ValidationResult (passed/checks/output)。
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ValidationCheck(BaseModel):
    """单条检查记录 (名称 + 通过 + 输出; test_result Artifact 内容源)。"""

    name: str
    passed: bool
    output: str = ""

    @field_validator("name", "output", mode="before")
    @classmethod
    def _strs_none(cls, v: Any) -> Any:
        return v if v is not None else ""


class ValidationResult(BaseModel):
    """验证结果: passed (语法 + 命令全过) + checks 明细 + 汇总输出。"""

    passed: bool
    checks: list[ValidationCheck] = Field(default_factory=list)
    output: str = ""

    @field_validator("checks", mode="before")
    @classmethod
    def _checks_none(cls, v: Any) -> Any:
        if v is None:
            return []
        return [c if isinstance(c, ValidationCheck) else ValidationCheck.model_validate(c) for c in v]

    @field_validator("output", mode="before")
    @classmethod
    def _output_none(cls, v: Any) -> Any:
        return v if v is not None else ""


class Validation:
    """沙箱验证器 (只检查不执行外部状态; 失败响亮返回 passed=False)。"""

    def __init__(
        self,
        project_dir: str | Path,
        *,
        command_timeout: float = 60.0,
        shell: bool = True,
    ) -> None:
        self._dir = Path(project_dir)
        self._timeout = command_timeout
        self._shell = shell

    # ------------------------------------------------------------------ 语法

    def syntax_check(self) -> ValidationCheck:
        """进程内 ast.parse 全部 .py 文件 (零子进程, 确定性; 失败逐文件记录)。"""
        errors: list[str] = []
        count = 0
        if self._dir.is_dir():
            for path in sorted(self._dir.rglob("*.py")):
                if any(part.startswith(".") for part in path.relative_to(self._dir).parts):
                    continue  # 跳过隐藏目录 (venv/.git 等副本过滤项)
                count += 1
                try:
                    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                except SyntaxError as exc:
                    errors.append(f"{path.name}:{exc.lineno}: {exc.msg}")
                except (OSError, UnicodeDecodeError) as exc:
                    errors.append(f"{path.name}: read failed: {exc}")
        if errors:
            return ValidationCheck(
                name="syntax",
                passed=False,
                output=f"语法错误 {len(errors)} 处:\n" + "\n".join(errors[:20]),
            )
        return ValidationCheck(
            name="syntax", passed=True, output=f"语法检查通过 ({count} 个 .py 文件)"
        )

    # ------------------------------------------------------------------ 命令

    def run_command(self, command: str) -> ValidationCheck:
        """沙箱内跑测试命令 (subprocess; rc 0 → 通过; 超时/异常 → 失败)。"""
        try:
            proc = subprocess.run(
                command,
                shell=self._shell,
                cwd=str(self._dir),
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired as exc:
            return ValidationCheck(
                name=f"command: {command}",
                passed=False,
                output=f"timed out after {self._timeout:g}s",
            )
        except OSError as exc:
            return ValidationCheck(
                name=f"command: {command}",
                passed=False,
                output=f"command failed to start: {exc}",
            )
        output = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
        return ValidationCheck(
            name=f"command: {command}",
            passed=proc.returncode == 0,
            output=(output or "(no output)").strip()[:2000],
        )

    # ------------------------------------------------------------------ 总入口

    def validate(self, command: str | None = None) -> ValidationResult:
        """语法检查 + 可选测试命令 → ValidationResult (门禁输入, 无执行权)。"""
        checks = [self.syntax_check()]
        if command:
            checks.append(self.run_command(command))
        passed = all(c.passed for c in checks)
        output = "\n".join(
            f"[{'PASS' if c.passed else 'FAIL'}] {c.name}\n{c.output}" for c in checks
        )
        return ValidationResult(passed=passed, checks=checks, output=output)
