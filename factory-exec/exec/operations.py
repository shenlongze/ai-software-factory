"""factory-exec/exec/operations.py — File Operation API (确定性 diff 生成)。

设计依据 (docs/architecture/developer-agent-reliability-model.md §2):
```
LLM → Intent (结构化意图) → Structured Code Operation → Validation → Patch
Intent: {target_file, operation, anchor, new_content}
Structured Operation: 基于 Symbol/行号定位的精确修改 (非文本猜测)
Validation: 语法检查 + 锚点存在性 + 应用试跑
Patch: 由 Operation 生成 (确定性, 非模型手写 diff)
```

背景 (真实 Benchmark 22.2%): diff 不可应用 ×2 的根因是模型手写 hunk
上下文与真实文件不匹配 (rc 128)。File Operation API 把「模型手写 diff」
改为「模型输出结构化操作 → 本模块确定性生成 git diff」— 操作只描述
意图 (改哪个文件/哪个符号/新内容), 不要求模型回忆精确上下文行。

操作类型:
- create_file:  新建文件 (change = 完整内容)
- delete_file:  删除文件
- modify_file:  整文件内容替换 (change = 完整新内容; 小文件/大规模改动)
- replace_block: 定位代码块 (symbol 名或行范围) 替换 (change = 新块内容)
                 — 核心操作: 锚点定位由引擎做, 模型只需给符号名/行号

生成链路 (全部确定性, 无 LLM 参与):
  plan(operations) → FileChange 列表 (新旧内容)
    → to_diff()  → unified diff 文本 (difflib 生成, git apply 兼容)
    → apply()    → 写入文件系统 (沙箱内; 不接触沙箱外)
    → validate() → 锚点存在性 + ast.parse 语法检查 (.py)

锚点解析 (replace_block):
- symbol: 函数/类名 → 定位定义行 → 块结束 (下一个同缩进定义行/文件尾,
  正则级启发式, 多语言 — 与 repo_index.scan_symbols 同源)。
- line_range: [start, end] 1-based inclusive (行号内联上下文让模型可精确指定)。

保持兼容: DeveloperAgent 仍接受模型直接输出 diff (fallback), 但操作优先
(模型先尝试结构化操作; 系统执行操作生成 patch)。
"""

from __future__ import annotations

import ast
import difflib
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

#: 支持符号扫描的语言定义模式 (行首; 正则级, 多语言启发式 — 非 AST)
_DEF_START = re.compile(
    r"^(?:"
    r"(?:public|private|protected|static|final|abstract|async|sync|export|"
    r"default|const|var|let|function|override)\s+)*"
    r"(?:"
    r"def\s+\w+\s*\(|"          # python def
    r"class\s+\w+|"              # 多数语言 class
    r"interface\s+\w+|"          # java/ts interface
    r"enum\s+\w+|"               # dart/java/ts enum
    r"struct\s+\w+|"             # go/rust struct
    r"function\s+\w+\s*\(|"      # js/ts function
    r"[A-Za-z_]\w*[<>,?\[\] .]*\s+\w+\s*\(|"  # 类型化方法/函数: void foo( / String bar(
    r"\w+\s*\("                  # 裸函数名: foo(
    r")"
)


class OperationError(Exception):
    """操作无效 (文件缺失/锚点缺失/JSON 非法/语法错误 — 响亮, 不静默)。

    消息以稳定前缀开头 (供测试/审计断言); DeveloperAgent 捕获后转
    DeveloperError (failure_reason=operation_error)。
    """


class OperationType(str, Enum):
    """结构化操作类型 (模型输出 JSON 的 operation 字段值)。"""

    CREATE_FILE = "create_file"
    DELETE_FILE = "delete_file"
    MODIFY_FILE = "modify_file"
    REPLACE_BLOCK = "replace_block"


class LocationSpec(BaseModel):
    """代码块定位: symbol (函数/类名) 或 line_range (1-based inclusive)。

    二者至少提供一个 (model_validator 校验); symbol 优先 (更鲁棒,
    不依赖模型精确记忆行号)。
    """

    symbol: str = ""
    line_range: tuple[int, int] | None = None

    @field_validator("symbol", mode="before")
    @classmethod
    def _symbol_none(cls, v: Any) -> Any:
        return v if v is not None else ""

    @field_validator("line_range", mode="before")
    @classmethod
    def _line_range_none(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, (list, tuple)) and len(v) == 2:
            return (int(v[0]), int(v[1]))
        raise ValueError(f"line_range 须为 [start, end] 两元素列表, 收到: {v!r}")

    @model_validator(mode="after")
    def _require_anchor(self) -> "LocationSpec":
        if not self.symbol and self.line_range is None:
            raise ValueError("location 须提供 symbol 或 line_range 之一")
        if self.line_range is not None:
            start, end = self.line_range
            if start < 1 or end < start:
                raise ValueError(
                    f"line_range 非法: [{start}, {end}] (1-based, start <= end)"
                )
        return self


class StructuredCodeOperation(BaseModel):
    """结构化代码操作 (模型输出的最小意图单元)。

    ```json
    {
      "operation": "replace_block",
      "target": "lib/editor/services/search_service.dart",
      "location": {"symbol": "replaceCurrent"},
      "change": "void replaceCurrent(...) { ... }",
      "expected": "只替换当前匹配, 不整文档替换"
    }
    ```

    target: 相对仓库根的路径; change: 新内容 (create/modify/replace_block
    必填); expected: 预期验证规则描述 (记录/报告用, 不参与执行)。
    """

    operation: OperationType
    target: str
    location: LocationSpec | None = None
    change: str = ""
    expected: str = ""

    @field_validator("operation", mode="before")
    @classmethod
    def _coerce_operation(cls, v: Any) -> OperationType:
        if isinstance(v, OperationType):
            return v
        try:
            return OperationType(str(v))
        except ValueError as exc:
            raise ValueError(
                f"operation 非法: {v!r} (可选: {[t.value for t in OperationType]})"
            ) from exc

    @field_validator("target", "change", "expected", mode="before")
    @classmethod
    def _strs_none(cls, v: Any) -> Any:
        return v if v is not None else ""

    @field_validator("location", mode="before")
    @classmethod
    def _location_none(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, LocationSpec):
            return v
        if isinstance(v, dict):
            return LocationSpec.model_validate(v)
        raise ValueError(f"location 非法: {v!r}")

    @model_validator(mode="after")
    def _require_change(self) -> "StructuredCodeOperation":
        if self.operation in (
            OperationType.CREATE_FILE,
            OperationType.MODIFY_FILE,
            OperationType.REPLACE_BLOCK,
        ) and not self.change:
            raise ValueError(f"{self.operation.value} 操作须提供 change 内容")
        if self.operation is OperationType.REPLACE_BLOCK and self.location is None:
            raise ValueError("replace_block 操作须提供 location")
        if not self.target.strip():
            raise ValueError("target 路径不能为空")
        return self


# ================================================================ 变更结果


@dataclass
class FileChange:
    """单文件确定性变更 (新旧内容; 由 Operation 计算, 非模型手写)。"""

    path: str            # 相对仓库根路径
    old_text: str        # 原内容 (文件不存在 → "")
    new_text: str        # 新内容 (删除 → "")
    block_desc: str = ""  # 定位描述 (symbol/行范围), 报告/审计用


@dataclass
class OperationValidation:
    """操作校验结果 (锚点存在性 + .py 语法检查)。"""

    passed: bool
    errors: list[str] = field(default_factory=list)
    changes: list[FileChange] = field(default_factory=list)


@dataclass
class OperationPlan:
    """操作执行计划: 确定性 FileChange 列表 (未写盘前可预演/生成 diff)。"""

    changes: list[FileChange] = field(default_factory=list)

    def to_diff(self) -> str:
        """FileChange 列表 → unified diff 文本 (difflib 生成, git apply 兼容)。

        - 新建文件: fromfile=/dev/null; 删除: tofile=/dev/null。
        - 每个文件 diff 独立成段, 以单个换行结尾 (git apply EOF 换行规范)。
        - lineterm="" + "\\n".join (Python 3.12 unified_diff 在 lineterm="\\n"
          时内容行不带换行 — 与 tests/benchmark make_patch 同模式)。
        """
        parts: list[str] = []
        for ch in self.changes:
            if ch.old_text == ch.new_text:
                continue
            old_lines = ch.old_text.splitlines()
            new_lines = ch.new_text.splitlines()
            diff = difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile="/dev/null" if not ch.old_text else f"a/{ch.path}",
                tofile="/dev/null" if not ch.new_text else f"b/{ch.path}",
                lineterm="",
            )
            text = "\n".join(diff)
            if text:
                parts.append(text + "\n")
        return "".join(parts)


class OperationEngine:
    """操作引擎: StructuredCodeOperation → 确定性 FileChange → diff/apply/校验。

    构造: root_dir = 项目根 (沙箱副本目录; 只读输入, 变更写盘须显式 apply)。
    """

    def __init__(self, root_dir: str | Path) -> None:
        self._root = Path(root_dir)

    @property
    def root_dir(self) -> Path:
        return self._root

    # ------------------------------------------------------------ 计划

    def plan(self, operations: list[StructuredCodeOperation]) -> OperationPlan:
        """操作列表 → FileChange 列表 (只读计算, 不写盘)。

        文件缺失 → OperationError (响亮, 不静默跳过 — 样本/模型 target
        写错立即暴露); 锚点缺失 → OperationError (replace_block 无法定位)。
        """
        plan = OperationPlan()
        for op in operations:
            plan.changes.append(self._plan_one(op))
        return plan

    def _plan_one(self, op: StructuredCodeOperation) -> FileChange:
        path = self._abs(op.target)
        exists = path.is_file()
        old_text = path.read_text(encoding="utf-8", errors="replace") if exists else ""

        if op.operation is OperationType.CREATE_FILE:
            if exists:
                raise OperationError(
                    f"create_file target 已存在: {op.target} (想覆盖用 modify_file)"
                )
            return FileChange(path=op.target, old_text="", new_text=op.change,
                              block_desc="create_file")

        if op.operation is OperationType.DELETE_FILE:
            if not exists:
                raise OperationError(f"delete_file target 不存在: {op.target}")
            return FileChange(path=op.target, old_text=old_text, new_text="",
                              block_desc="delete_file")

        if op.operation is OperationType.MODIFY_FILE:
            if not exists:
                raise OperationError(f"modify_file target 不存在: {op.target}")
            return FileChange(path=op.target, old_text=old_text, new_text=op.change,
                              block_desc="modify_file")

        # replace_block (核心)
        if not exists:
            raise OperationError(f"replace_block target 不存在: {op.target}")
        assert op.location is not None  # 模型校验已保证
        lines = old_text.splitlines()
        start, end = self.resolve_block(lines, op.location)
        new_lines = list(lines)
        new_lines[start - 1:end] = op.change.splitlines()
        new_text = "\n".join(new_lines)
        return FileChange(
            path=op.target,
            old_text=old_text,
            new_text=new_text,
            block_desc=self._block_desc(op.location, start, end),
        )

    # ------------------------------------------------------------ 锚点解析

    @classmethod
    def resolve_block(cls, lines: list[str], location: LocationSpec) -> tuple[int, int]:
        """定位代码块 → (start_line, end_line) 1-based inclusive。

        - symbol: 定义行 → 块结束 (下一同缩进定义行前一行/文件尾);
        - line_range: 直接用 (越界 → OperationError)。
        """
        if location.symbol:
            start = cls.find_def_line(lines, location.symbol)
            if start is None:
                raise OperationError(
                    f"symbol 定位失败: {location.symbol!r} "
                    "(未找到函数/类定义行; 检查名称或改用 line_range)"
                )
            end = cls.block_end(lines, start)
            return start + 1, end + 1
        assert location.line_range is not None
        start, end = location.line_range
        if start < 1 or end > len(lines) or end < start:
            raise OperationError(
                f"line_range 越界: [{start}, {end}] (文件共 {len(lines)} 行)"
            )
        return start, end

    @staticmethod
    def find_def_line(lines: list[str], symbol: str) -> int | None:
        """找符号定义行 (0-based; 多语言正则级启发式, 非 AST)。"""
        pat = re.escape(symbol)
        for i, line in enumerate(lines):
            s = line.strip()
            if re.match(rf"^(?:async\s+)?def\s+{pat}\s*\(", s):
                return i
            if re.match(rf"^(?:class|interface|enum|struct|trait)\s+{pat}\b", s):
                return i
            if re.match(rf"^[A-Za-z_]\w*[<>,?\[\] .]*\s+{pat}\s*\(", s):
                return i
            if re.match(rf"^{pat}\s*\(", s):
                return i
        return None

    @staticmethod
    def looks_like_def(line: str) -> bool:
        """行是否像新定义 (块结束启发式用; 正则级)。"""
        s = line.strip()
        if not s:
            return False
        if s.startswith(("#", "//", "/*", "*", "*/")):  # 注释/文档
            return False
        return bool(_DEF_START.match(s))

    @classmethod
    def block_end(cls, lines: list[str], start: int) -> int:
        """块结束行 (0-based inclusive): 下一同缩进定义行前一行, 否则文件尾。

        - 定义行缩进 = indent; 向后找第一个"缩进 <= indent 且像定义"的行,
          其前一行即当前块结束;
        - 空行/注释跳过 (不打断块);
        - 找不到 → 文件尾 (函数延伸到 EOF, 常见于单文件脚本)。
        """
        indent = len(lines[start]) - len(lines[start].lstrip())
        for j in range(start + 1, len(lines)):
            line = lines[j]
            if not line.strip():
                continue
            cur_indent = len(line) - len(line.lstrip())
            if cur_indent <= indent and cls.looks_like_def(line):
                return j - 1
        return len(lines) - 1

    @staticmethod
    def _block_desc(location: LocationSpec, start: int, end: int) -> str:
        if location.symbol:
            return f"symbol {location.symbol!r} (行 {start}-{end})"
        return f"line_range {location.line_range}"

    # ------------------------------------------------------------ 应用/校验

    def apply(self, plan: OperationPlan) -> list[str]:
        """把计划写入文件系统 (沙箱内; 返回已写路径列表)。

        调用方负责沙箱边界 — 引擎不校验路径是否在沙箱内 (root_dir
        即沙箱副本目录, 由调用方注入; 防御性 target 绝对路径拒绝)。
        """
        written: list[str] = []
        for ch in plan.changes:
            # 防御: target 必须落在 root_dir 内 (resolve 解开符号链接,
            # macOS /var → /private/var 等临时目录场景)
            if self._abs(ch.path) != (self._root / ch.path).resolve():
                raise OperationError(f"target 非法路径: {ch.path}")
            if ch.new_text == "" and ch.old_text != "":
                # 删除文件
                self._abs(ch.path).unlink(missing_ok=True)
            else:
                target = self._abs(ch.path)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(ch.new_text, encoding="utf-8")
            written.append(ch.path)
        return written

    def validate(self, operations: list[StructuredCodeOperation]) -> OperationValidation:
        """操作校验: 锚点存在性 (plan 内) + .py 语法检查 (ast.parse)。

        锚点失败 → errors 收集 (不抛 — 调用方决定重试/失败); 语法检查
        只对最终 new_text 为 .py 的文件 (确定性, 零子进程)。
        """
        errors: list[str] = []
        try:
            plan = self.plan(operations)
        except OperationError as exc:
            return OperationValidation(passed=False, errors=[str(exc)])
        changes = plan.changes
        for ch in changes:
            if ch.path.endswith(".py") and ch.new_text.strip():
                try:
                    ast.parse(ch.new_text, filename=ch.path)
                except SyntaxError as exc:
                    errors.append(
                        f"{ch.path}: 语法错误 行 {exc.lineno}: {exc.msg}"
                    )
        return OperationValidation(passed=not errors, errors=errors, changes=changes)

    def _abs(self, rel: str) -> Path:
        if not rel or Path(rel).is_absolute():
            raise OperationError(f"target 须为相对路径: {rel!r}")
        return (self._root / rel).resolve()
