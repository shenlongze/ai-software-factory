"""factory-exec/exec/benchmark/verifiers.py — 样本验证器注册表 (不依赖 LLM)。

设计 (Phase A+++++ Benchmark): 每个样本配 verifier = 纯 Python 静态/行为检查,
零 LLM 调用:
- 静态检查: 读沙箱内修复后的源码, 断言修复语义 (反模式缺失 + 正模式就位)。
- 行为检查 (greenfield): 真实运行沙箱内的 CLI, 断言命令行为与产物 (todo.py)。
正/反例有效由 tests/benchmark/test_benchmark_verifiers.py 独立验证 (不调 LLM)。

verifier 签名: fn(sandbox_dir: Path, sample: BenchmarkSample) -> (passed, detail)
注册表 VERIFIERS: verifier_id → fn (样本通过 verifier_id 引用)。

重要: fix_hint 只进测试/人工核验, 绝不进 Agent prompt (样本 prompt_text 已排除)。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

from .models import BenchmarkSample

#: verifier 注册表: verifier_id → fn(sandbox_dir, sample) -> (passed, detail)
VERIFIERS: dict[str, Callable[[Path, BenchmarkSample], tuple[bool, str]]] = {}


def register(verifier_id: str):
    """verifier 注册装饰器 (id 冲突 → 后注册覆盖, 同 provider registry 语义)。"""

    def deco(fn):
        VERIFIERS[verifier_id] = fn
        return fn

    return deco


def get(verifier_id: str):
    """按 id 取 verifier (未注册 → None; 样本定义错误响亮暴露于 runner 预检)。"""
    return VERIFIERS.get(verifier_id)


def _read(sandbox_dir: Path, rel: str) -> str:
    """读沙箱文件 (相对 sandbox 根); 缺失 → 抛 FileNotFoundError (verifier 转 FAIL)。"""
    path = sandbox_dir / rel
    if not path.is_file():
        raise FileNotFoundError(f"{rel} (沙箱缺失该文件)")
    return path.read_text(encoding="utf-8", errors="replace")


# ================================================================ BUG 样本

# ------------------------------------------------------------------ BUG-001
@register("verify_bug_001_replace_current")
def verify_bug_001_replace_current(sandbox_dir: Path, sample: BenchmarkSample) -> tuple[bool, str]:
    """BUG-MKP-001: replaceCurrent 只替换当前匹配, 不再整文档替换。

    修复语义 (镜像 editor_page.dart _replaceCurrent 正确实现 + verify_search_fix.py):
    1. 签名接收全文参数 (fullContent/display 语义) + 回调。
    2. 方法体对当前匹配范围 replaceRange (局部替换)。
    3. 反模式 `onContentChanged(_replaceQuery)` (整文档替换成替换词) 必须消失。
    """
    src = _read(sandbox_dir, "lib/editor/services/search_service.dart")
    fails: list[str] = []

    m = re.search(
        r"void\s+replaceCurrent\s*\(\s*((?:[^()]|\([^)]*\))*)\)\s*\{", src, re.DOTALL
    )
    if not m:
        fails.append("replaceCurrent 签名不可解析")
    else:
        params = m.group(1)
        has_full = bool(re.search(r"\bfullContent\b|\bdisplay\b", params))
        has_cb = "onContentChanged" in params
        if not (has_full and has_cb):
            fails.append("replaceCurrent 签名缺全文参数或回调")

    if "replaceRange" not in src:
        fails.append("方法体未使用 replaceRange (局部替换语义)")
    if "onContentChanged(_replaceQuery)" in src:
        fails.append("反模式残留: onContentChanged(_replaceQuery) 整文档替换")

    if fails:
        return False, "; ".join(fails)
    return True, "replaceCurrent 局部替换语义就位"


# ------------------------------------------------------------------ BUG-002
@register("verify_bug_002_readonly_tab")
def verify_bug_002_readonly_tab(sandbox_dir: Path, sample: BenchmarkSample) -> tuple[bool, str]:
    """BUG-MKP-002: 切换 tab 不丢失只读状态 (大文件只读保护)。

    原缺陷: switchToTab 无条件 `_readOnly = false` — 打开 >100MB 只读文件后
    切 tab 再切回, 只读保护丢失, 超大文件可编辑 → 性能/崩溃风险。
    修复语义: switchToTab 从文件/缓存恢复只读状态 (不无条件重置 false)。
    """
    src = _read(sandbox_dir, "lib/editor/controllers/file_controller.dart")
    fails: list[str] = []

    m = re.search(r"void\s+switchToTab\s*\([^)]*\)\s*\{", src)
    if not m:
        return False, "switchToTab 方法不存在"
    body_start = m.end()
    # 取 switchToTab 方法体 (到下一个 'void ' 方法或文件尾)
    rest = src[body_start:]
    nxt = re.search(r"\n\s*(void|Future|bool|String|int|MdFile|@override)", rest)
    body = rest[: nxt.start()] if nxt else rest

    if "_readOnly = false" in body:
        fails.append("switchToTab 仍无条件重置 _readOnly = false (只读保护丢失)")
    # 正模式: 从文件记录恢复只读 (isReadOnly/readOnly 来源引用)
    if not re.search(r"_readOnly\s*=\s*(?!false)", body):
        if "isReadOnly" not in body and "readOnly" not in body:
            fails.append("switchToTab 未从文件状态恢复只读标记")

    if fails:
        return False, "; ".join(fails)
    return True, "switchToTab 恢复只读状态语义就位"


# ------------------------------------------------------------------ BUG-003
@register("verify_bug_003_bom_order")
def verify_bug_003_bom_order(sandbox_dir: Path, sample: BenchmarkSample) -> tuple[bool, str]:
    """BUG-MKP-003: 编码检测 BOM 优先于长度守卫。

    原缺陷: `if (bytes.length < 4) return 'utf-8';` 在 BOM 检测之前 — 2-3 字节
    带 UTF-16 BOM (FF FE / FE FF) 的短文件被误判为 utf-8。
    修复语义: BOM 检查 (0xFF 0xFE / 0xFE 0xFF) 出现在长度守卫之前。
    """
    src = _read(sandbox_dir, "lib/editor/services/encoding_service.dart")
    fails: list[str] = []

    len_guard = re.search(r"bytes\.length\s*<\s*4", src)
    bom_le = re.search(r"0xFF\s*&&\s*bytes\[1\]\s*==\s*0xFE", src)
    bom_be = re.search(r"0xFE\s*&&\s*bytes\[1\]\s*==\s*0xFF", src)

    if not len_guard:
        fails.append("未找到长度守卫 bytes.length < 4 (修复需保留守卫, 仅调整其位置)")
    if not (bom_le or bom_be):
        fails.append("未找到 UTF-16 BOM 检测分支")
    else:
        if len_guard and bom_le:
            if len_guard.start() < bom_le.start():
                fails.append("长度守卫在 UTF-16LE BOM 检测之前 (短 BOM 文件误判)")
        if len_guard and bom_be:
            if len_guard.start() < bom_be.start():
                fails.append("长度守卫在 UTF-16BE BOM 检测之前 (短 BOM 文件误判)")

    if fails:
        return False, "; ".join(fails)
    return True, "BOM 检测优先于长度守卫"


# ------------------------------------------------------------------ BUG-004
@register("verify_bug_004_snapshot_fields")
def verify_bug_004_snapshot_fields(sandbox_dir: Path, sample: BenchmarkSample) -> tuple[bool, str]:
    """BUG-MKP-004: undo 快照深拷贝保留 TableBlock aligns/columnWidths。

    原缺陷: DocumentSnapshot._cloneBlock 对 TableBlock 只拷贝 rows, 丢失
    aligns/columnWidths — 表格对齐/列宽在 undo/redo 后丢失。
    修复语义: TableBlock 深拷贝保留 aligns + columnWidths。
    """
    src = _read(sandbox_dir, "lib/editor/undo/document_snapshot.dart")
    fails: list[str] = []

    if "TableBlock" not in src:
        fails.append("未找到 TableBlock 分支")
    else:
        if "aligns" not in src:
            fails.append("_cloneBlock 未拷贝 aligns (表格对齐丢失)")
        if "columnWidths" not in src:
            fails.append("_cloneBlock 未拷贝 columnWidths (表格列宽丢失)")

    if fails:
        return False, "; ".join(fails)
    return True, "快照深拷贝保留表格 aligns/columnWidths"


# ------------------------------------------------------------------ BUG-005
@register("verify_bug_005_nested_list_numbering")
def verify_bug_005_nested_list_numbering(sandbox_dir: Path, sample: BenchmarkSample) -> tuple[bool, str]:
    """BUG-MKP-005: 嵌套有序列表序号每级重新计数。

    原缺陷: _serializeList 用全局 i+1 作有序序号 — 嵌套有序列表
    `1. a\n   1. b` round-trip 变 `1. a\n   2. b` (嵌套序号错误)。
    修复语义: 序号按 indent 层级独立计数 (每级从 1 重新编号)。
    """
    src = _read(sandbox_dir, "lib/core/document/serializer.dart")
    fails: list[str] = []

    m = re.search(r"String\s+_serializeList\s*\([^)]*\)\s*\{", src)
    if not m:
        return False, "_serializeList 方法不存在"
    body_start = m.end()
    rest = src[body_start:]
    nxt = re.search(r"\n\s*(String|Document|TableBlock|ListBlock|void)", rest)
    body = rest[: nxt.start()] if nxt else rest

    # 反模式: 全局 i+1 直接作序号 (嵌套层级共享计数)
    if re.search(r"\$\{i\s*\+\s*1\}\.\s", body):
        fails.append("仍用全局 i+1 作有序序号 (嵌套列表序号共享, 不每级重数)")
    # 正模式: 按 indent 层级计数 (per-level counter / lastIndent 键控)
    if not re.search(r"indent", body):
        fails.append("序号逻辑未感知 indent 层级 (无法每级重新计数)")

    if fails:
        return False, "; ".join(fails)
    return True, "嵌套有序列表序号按 indent 层级独立计数"


# ============================================================== FEATURE 样本

# ------------------------------------------------------------------ FEAT-001
@register("verify_feat_001_recent_time")
def verify_feat_001_recent_time(sandbox_dir: Path, sample: BenchmarkSample) -> tuple[bool, str]:
    """FEAT-MKP-001: 最近文件条目显示相对修改时间。

    需求: 侧边栏「最近文件」区域每个条目显示 file.modifiedAt 的相对时间
    (如「3 分钟前」), 而非只有文件名。
    verifier: 最近文件条目渲染引用 modifiedAt + 存在相对时间格式化辅助。
    """
    src = _read(sandbox_dir, "lib/shared/pages/file_tree.dart")
    fails: list[str] = []
    if "modifiedAt" not in src:
        fails.append("最近文件条目未引用 modifiedAt (修改时间未接入)")
    if not re.search(
        r"_relativeTime|formatRelative|relativeTime|timeAgo|timeago|分钟前|小时前|ago",
        src,
    ):
        fails.append("未实现相对时间格式化 (如「3 分钟前」)")
    if fails:
        return False, "; ".join(fails)
    return True, "最近文件条目显示相对修改时间"


# ------------------------------------------------------------------ FEAT-002
@register("verify_feat_002_format_size")
def verify_feat_002_format_size(sandbox_dir: Path, sample: BenchmarkSample) -> tuple[bool, str]:
    """FEAT-MKP-002: 文件列表显示人类可读大小 (formatSize)。

    需求: 文件树/最近文件显示 '12.5 KB' / '3.2 MB' 而非裸字节数。
    verifier: md_file.dart 存在 formatSize 辅助 (KB/MB 分支)。
    """
    src = _read(sandbox_dir, "lib/shared/models/md_file.dart")
    fails: list[str] = []
    if "formatSize" not in src:
        fails.append("未新增 formatSize 辅助方法")
    else:
        if not re.search(r"KB|MB|GB", src):
            fails.append("formatSize 无 KB/MB 单位分支")
    if fails:
        return False, "; ".join(fails)
    return True, "formatSize 人类可读大小辅助就位"


# ------------------------------------------------------------------ FEAT-003
@register("verify_feat_003_tab_dirty")
def verify_feat_003_tab_dirty(sandbox_dir: Path, sample: BenchmarkSample) -> tuple[bool, str]:
    """FEAT-MKP-003: 标签页未保存修改指示器 (dirty dot)。

    需求: 有未保存修改的文件标签显示修改指示点, 保存后消失。
    verifier: tab_bar.dart 感知 dirty/未保存状态 + 渲染指示器 (小圆点)。
    """
    src = _read(sandbox_dir, "lib/shared/widgets/tab_bar.dart")
    fails: list[str] = []
    if not re.search(r"\bdirty\b|unsaved|hasUnsaved", src):
        fails.append("标签栏未感知 dirty/未保存状态")
    if not re.search(r"Icons\.circle|Icons\.fiber_manual_record|'•'|\"•\"", src):
        fails.append("标签上未渲染修改指示器 (小圆点)")
    if fails:
        return False, "; ".join(fails)
    return True, "未保存标签渲染修改指示点"


# ============================================================= GREENFIELD

# ------------------------------------------------------------------ TODO CLI
@register("verify_greenfield_todo_cli")
def verify_greenfield_todo_cli(sandbox_dir: Path, sample: BenchmarkSample) -> tuple[bool, str]:
    """GREENFIELD-001: 命令行待办管理 CLI (真实行为验证, 不依赖 LLM)。

    行为契约:
      todo.py add "任务"            → 添加 (输出含 id)
      todo.py list                  → 列出未完成任务 (含刚添加的任务)
      todo.py done <id>             → 标记完成
      todo.py list --all            → 含已完成任务
      todo.py remove <id>           → 删除
    JSON 持久化 (todo.json 落在沙箱 cwd)。
    """
    script = sandbox_dir / "todo.py"
    if not script.is_file():
        return False, "todo.py 缺失"
    fails: list[str] = []
    python = sys.executable

    def run(*args: str) -> tuple[int, str]:
        proc = subprocess.run(
            [python, str(script), *args],
            capture_output=True, text=True, timeout=30,
            cwd=str(sandbox_dir),
        )
        return proc.returncode, (proc.stdout + proc.stderr).strip()

    # add
    rc, out = run("add", "benchmark verification task")
    if rc != 0:
        return False, f"add 失败 (rc {rc}): {out[:200]}"
    task_id = ""
    m = re.search(r"(\d+)", out)
    if m:
        task_id = m.group(1)
    if not task_id:
        # add 输出无 id → 从 list 取
        rc, out = run("list")
        m = re.search(r"(\d+)", out)
        task_id = m.group(1) if m else ""
    if not task_id:
        fails.append("无法从 add/list 输出解析任务 id")

    # list 含任务
    rc, out = run("list")
    if rc != 0:
        fails.append(f"list 失败 (rc {rc})")
    elif "benchmark verification task" not in out:
        fails.append("list 未包含刚添加的任务")

    # done
    if task_id:
        rc, out = run("done", task_id)
        if rc != 0:
            fails.append(f"done 失败 (rc {rc})")
        rc, all_out = run("list", "--all")
        if rc == 0 and "benchmark verification task" not in all_out:
            fails.append("list --all 未包含已完成任务")

    # remove
    if task_id:
        rc, out = run("remove", task_id)
        if rc != 0:
            fails.append(f"remove 失败 (rc {rc})")
        rc, out = run("list", "--all")
        if rc == 0 and "benchmark verification task" in out:
            fails.append("remove 后任务仍存在")

    if fails:
        return False, "; ".join(fails)
    return True, "todo CLI add/list/done/remove + JSON 持久化行为全通过"
