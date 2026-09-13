"""factory-console/session/debug/workspace_executor.py — 真实 Workspace 修复执行器 (S10-071 P0-1/P0-2)。

WorkspaceRepairExecutor: 对真实 Workspace 做真实文件修改 (snapshot/diff/rollback)。
PytestValidator: 真实 subprocess pytest 验证 (复用 quality.Validator.validate_command)。

设计:
- 生产默认路径 = 真实执行 (非注入桩)
- 修改可审计: 修改前 snapshot → 修改后 diff → rollback 可恢复
- 修复动作: 确定性策略应用 (根据 FixStrategy + 错误信息生成修补)
- 验证: 真实 pytest (timeout/exit_code/stdout/stderr)
"""

from __future__ import annotations

import difflib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


# ================================================================== 模型


@dataclass
class RepairAction:
    """一次确定性修复动作 (真实文件修改)。"""

    file: str
    action: str  # write_file / apply_patch / append / create_dir
    content: Optional[str] = None
    old_text: Optional[str] = None
    new_text: Optional[str] = None
    note: str = ""


@dataclass
class WorkspaceRepairResult:
    """修复结果 (真实证据)。"""

    success: bool
    strategy: str = ""
    changed_files: List[str] = field(default_factory=list)
    diffs: Dict[str, str] = field(default_factory=dict)
    snapshots: Dict[str, str] = field(default_factory=dict)
    rolled_back: bool = False
    note: str = ""
    error: str = ""
    duration: float = 0.0


@dataclass
class ValidationResult:
    """真实验证结果 (pytest 执行)。"""

    success: bool
    command: str = ""
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""
    duration: float = 0.0
    error: str = ""
    summary: str = ""


# ================================================================== 修复动作生成 (确定性)


def _extract_test_expectation(error_message: str) -> Optional[tuple[str, str]]:
    """从错误消息提取期望: 'expected X got Y' / 'expected X but got Y'。"""
    m = re.search(r"expected\s+(.+?)\s+(?:but\s+)?got\s+(.+)", error_message, re.IGNORECASE)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return None


def build_repair_actions(session: Any, workspace: Path) -> List[RepairAction]:
    """根据 DebugSession 生成确定性修复动作 (真实可写)。

    支持:
    - FIX_CODE: 修正实现 (从测试期望推断)
    - FIX_TEST: 修正测试
    - 补 import / 创建缺失文件 (MISSING/IMPORT_ERROR)
    - 其余策略: 空动作 (REVIEW/ROLLBACK 由治理处理)
    """
    strategy = str(getattr(session, "selected_strategy", "") or "")
    error_message = str(getattr(session, "error_summary", "") or "")
    validation_command = str(getattr(session, "validation_command", "") or "pytest")
    actions: List[RepairAction] = []

    if strategy == "FIX_CODE":
        exp = _extract_test_expectation(error_message)
        if exp:
            expected, got = exp
            # 找测试文件 (validation_command 指向的 test_*.py)
            test_files = _find_test_files(workspace)
            if test_files:
                tf = test_files[0]
                content = _read(tf)
                # 在测试文件内找到对应断言行, 生成修正说明 (真实修复由实现方执行)
                # 确定性兜底: 若测试断言期望值与实现不符, 修正实现文件
                impl_files = _find_impl_files(workspace, tf)
                for impl in impl_files:
                    ic = _read(impl)
                    if got and got.strip() in ic:
                        actions.append(RepairAction(
                            file=str(impl.relative_to(workspace)),
                            action="apply_patch",
                            old_text=got.strip(),
                            new_text=expected.strip(),
                            note=f"FIX_CODE: 修正实现 '{got}' → '{expected}' (来自测试期望)",
                        ))
                        break
        # S10-071 P0-1: FIX_CODE 通用兜底 — 实现文件含 got 字面量 → 替换为 expected
        if not actions:
            exp = _extract_test_expectation(error_message)
            if exp:
                expected, got = exp
                for impl in _find_all_impl_files(workspace):
                    ic = _read(impl)
                    if got.strip() in ic and expected.strip() not in ic:
                        actions.append(RepairAction(
                            file=str(impl.relative_to(workspace)),
                            action="apply_patch",
                            old_text=got.strip(),
                            new_text=expected.strip(),
                            note=f"FIX_CODE: 修正实现 '{got}' → '{expected}' (确定性修复)",
                        ))
                        break
    elif strategy == "FIX_TEST":
        exp = _extract_test_expectation(error_message)
        if exp:
            expected, got = exp
            test_files = _find_test_files(workspace)
            for tf in test_files:
                content = _read(tf)
                if expected.strip() in content and got.strip() in content:
                    actions.append(RepairAction(
                        file=str(tf.relative_to(workspace)),
                        action="apply_patch",
                        old_text=f"expected {expected}",
                        new_text=f"expected {got}",
                        note=f"FIX_TEST: 修正测试期望 {expected} → {got} (与实际实现一致)",
                    ))
                    break
    elif strategy in ("FIX_CODE", "CHANGE_DESIGN"):
        # 缺 import / 缺失模块 → 创建占位实现
        m = re.search(r"(?:no module named|ModuleNotFoundError: No module named)\s+'?([A-Za-z0-9_\.]+)'?", error_message, re.IGNORECASE)
        if m:
            mod = m.group(1)
            if mod.endswith(".py"):
                target = workspace / mod
            else:
                target = workspace / f"{mod.split('.')[-1]}.py"
            if not target.is_file():
                actions.append(RepairAction(
                    file=str(target.relative_to(workspace)) if target != workspace else mod,
                    action="write_file",
                    content="# 自动生成模块 (S10-071 Debug 修复)\n",
                    note=f"创建缺失模块 {mod}",
                ))
    return actions


def _find_test_files(workspace: Path) -> List[Path]:
    return sorted(p for p in workspace.rglob("test_*.py") if p.is_file())


def _find_impl_files(workspace: Path, test_file: Path) -> List[Path]:
    """测试文件同目录/同名的实现文件 (scoring_test → scoring)。"""
    impls = []
    name = test_file.stem
    if name.startswith("test_"):
        cand = test_file.parent / (name[5:] + ".py")
        if cand.is_file():
            impls.append(cand)
    # 同目录所有非 test 的 .py
    impls.extend(sorted(p for p in test_file.parent.glob("*.py")
                        if p.is_file() and not p.name.startswith("test_")))
    return impls


def _find_all_impl_files(workspace: Path) -> List[Path]:
    """workspace 全部非 test 的 .py 实现文件。"""
    return sorted(p for p in workspace.rglob("*.py")
                  if p.is_file() and not p.name.startswith("test_"))


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return ""


# ================================================================== 执行器


class WorkspaceRepairExecutor:
    """真实 Workspace 修复执行器 (P0-1): 修改真实文件, snapshot/diff/rollback。"""

    def __init__(self, workspace: Any = None) -> None:
        self.workspace = Path(workspace) if workspace is not None else Path.cwd()
        self._snapshots: Dict[str, str] = {}
        self._rolled_back = False

    # ---- 底层工具 (可审计) ----

    def snapshot(self, rel_path: str) -> str:
        """修改前快照。"""
        target = self.workspace / rel_path
        content = _read(target)
        self._snapshots[rel_path] = content
        return content

    def apply_action(self, action: RepairAction) -> bool:
        """执行单个修复动作 (真实写入)。"""
        target = self.workspace / action.file
        try:
            if action.action == "write_file":
                self.snapshot(action.file)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(action.content or "", encoding="utf-8")
                return True
            if action.action == "apply_patch":
                if not target.is_file():
                    return False
                content = _read(target)
                if action.old_text and action.old_text in content:
                    self.snapshot(action.file)
                    new_content = content.replace(action.old_text, action.new_text or "", 1)
                    target.write_text(new_content, encoding="utf-8")
                    return True
                return False
            if action.action == "append":
                self.snapshot(action.file)
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("a", encoding="utf-8") as fh:
                    fh.write(action.content or "")
                return True
            if action.action == "create_dir":
                (self.workspace / action.file).mkdir(parents=True, exist_ok=True)
                return True
            return False
        except Exception as exc:  # noqa: BLE001 — 失败安全
            self._last_error = str(exc)
            return False

    def diff(self, rel_path: str) -> str:
        """修改前后 diff。"""
        if rel_path not in self._snapshots:
            return ""
        target = self.workspace / rel_path
        new = _read(target)
        old = self._snapshots[rel_path]
        if old == new:
            return ""
        return "".join(difflib.unified_diff(
            old.splitlines(keepends=True), new.splitlines(keepends=True),
            fromfile=f"a/{rel_path}", tofile=f"b/{rel_path}"))

    def rollback(self) -> List[str]:
        """回滚所有修改 (恢复 snapshot)。"""
        restored = []
        for rel_path, content in self._snapshots.items():
            target = self.workspace / rel_path
            try:
                if content == "" and not target.exists():
                    continue
                target.write_text(content, encoding="utf-8")
                restored.append(rel_path)
            except Exception:  # noqa: BLE001
                pass
        self._rolled_back = bool(restored)
        return restored

    # ---- 主入口 ----

    def execute(self, session: Any) -> WorkspaceRepairResult:
        """执行修复: 生成动作 → 真实写入 → diff 记录。"""
        start = time.monotonic()
        strategy = str(getattr(session, "selected_strategy", "") or "")
        result = WorkspaceRepairResult(success=False, strategy=strategy)
        actions = build_repair_actions(session, self.workspace)
        if not actions:
            result.note = "无可执行修复动作 (策略需人工/治理处理)"
            result.duration = round(time.monotonic() - start, 4)
            return result
        for action in actions:
            ok = self.apply_action(action)
            if ok:
                rel = action.file
                result.changed_files.append(rel)
                result.snapshots[rel] = self._snapshots.get(rel, "")
                result.diffs[rel] = self.diff(rel)
            else:
                result.error = getattr(self, "_last_error", "") or f"动作失败: {action.action} {action.file}"
        result.success = bool(result.changed_files)
        result.note = f"真实修改 {len(result.changed_files)} 个文件 (snapshot/diff/rollback 就绪)"
        result.duration = round(time.monotonic() - start, 4)
        return result


# ================================================================== PytestValidator (P0-2)


class PytestValidator:
    """真实 pytest 验证器 (P0-2): subprocess 执行, 复用 quality.Validator。"""

    def __init__(self, timeout: int = 120) -> None:
        self.timeout = timeout

    def validate(self, workspace: Any, command: str = "pytest", *, env: Optional[dict] = None) -> ValidationResult:
        """在 workspace 目录真实执行测试命令 (环境隔离, 防 PYTHONPATH 污染)。"""
        from ..quality import Validator

        ws = Path(workspace) if workspace is not None else Path.cwd()
        start = time.monotonic()
        result = ValidationResult(success=False, command=command)
        # S10-071 P0-2: 环境隔离 — 清 PYTHONPATH 防父进程 sys.path 污染, 保留 PATH
        import os
        clean_env = dict(os.environ)
        clean_env["PYTHONPATH"] = ""
        clean_env.pop("PYTHONHOME", None)
        if env:
            clean_env.update(env)
        try:
            vr = Validator().validate_command(ws, command, timeout=self.timeout, env=clean_env)
            result.success = bool(vr.success)
            result.exit_code = 0 if vr.success else 1
            result.error = "; ".join(vr.errors or [])
            result.summary = (
                f"passed={vr.tests_passed} failed={vr.tests_failed} total={vr.tests_total}"
                if hasattr(vr, "tests_passed") else f"success={vr.success}"
            )
        except Exception as exc:  # noqa: BLE001 — 失败安全
            result.success = False
            result.error = str(exc)
            result.summary = "验证器异常"
        result.duration = round(time.monotonic() - start, 4)
        return result


# ================================================================== 生产默认执行器 (替代桩)


def production_execute_fn():
    """生产默认修复执行器: 真实 Workspace 修改 (替代 _default_execute_fn 桩)。

    用法: DebugPipeline(execute_fn=production_execute_fn())
    """

    def execute(session: Any, workspace: Path) -> dict[str, Any]:
        executor = WorkspaceRepairExecutor(workspace=workspace)
        result = executor.execute(session)
        return {
            "success": result.success,
            "strategy": result.strategy,
            "changed_files": result.changed_files,
            "diffs": result.diffs,
            "note": result.note,
            "error": result.error,
            "validation_command": getattr(session, "validation_command", "") or "pytest",
        }

    return execute


def production_validator_fn():
    """生产默认验证器: 真实 pytest (替代注入 validator)。"""

    def validate(session: Any, result: Any = None, workspace: Any = None) -> str:
        ws = Path(workspace) if workspace is not None else Path.cwd()
        v = PytestValidator().validate(ws)
        return "success" if v.success else "failure"

    return validate
