"""factory-exec/exec/benchmark/bugs.py — Benchmark Bug 样本集 (5 个真实 Bug)。

来源: markpad lib/ 只读分析 (不修改生产目录; 修复在沙箱副本内完成)。
每个样本:
- objective: 自然语言任务描述 (只描述现象/影响, 禁人工答案 — 不含修复方案)。
- requirement: 验收标准 (verifier 可判定的约束)。
- fix_hint: 隐藏字段 — 仅供测试正/反例核验与人工审计, 绝不进 Agent prompt
  (BenchmarkSample.prompt_text() 已排除; runner 组装任务上下文时也不使用)。

Bug 语义 (均已对照 /Users/Shared/work/markpad 源码核实缺陷存在):
- BUG-MKP-001: replaceCurrent 整文档替换成替换词 (应只替换当前匹配)。
- BUG-MKP-002: switchToTab 无条件 _readOnly=false, 大文件只读保护切 tab 丢失。
- BUG-MKP-003: 编码检测长度守卫在 BOM 检测之前, 短 UTF-16 文件误判 utf-8。
- BUG-MKP-004: 快照深拷贝 TableBlock 丢 aligns/columnWidths (undo 后表格样式丢失)。
- BUG-MKP-005: 嵌套有序列表序号全局递增, 不按缩进层级重新计数。
"""

from __future__ import annotations

from .models import BenchmarkSample, SampleKind

#: 5 个真实 Bug 样本 (自然语言任务 + verifier 验收, 无人工答案)
BUG_SAMPLES: list[BenchmarkSample] = [
    BenchmarkSample(
        id="BUG-MKP-001",
        kind=SampleKind.BUG,
        title="替换当前: 整文档被替换成替换词",
        objective=(
            "编辑器查找替换面板中, 点击「替换当前」(Replace Current) 后, "
            "整个文档内容会被替换为替换词, 而不是只替换当前选中的那一处匹配。"
            "请修复: 点击「替换当前」应只替换当前匹配位置的内容, 文档其余部分保持不变。"
        ),
        requirement=(
            "1. replaceCurrent 方法的签名接收全文内容参数与内容回调;\n"
            "2. 方法体对当前匹配范围做局部替换 (replaceRange 语义);\n"
            "3. 不存在把全文直接替换为替换词的行为。"
        ),
        project_files=["lib/editor/services/search_service.dart"],
        verifier_id="verify_bug_001_replace_current",
        fix_hint=(
            "缺陷定位: search_service.dart 的「替换当前」处理器把整个文档内容直接"
            "回传为替换词, 正确做法是仅针对首次命中的区间做局部改写 "
            "(可参照同文件中另一个替换方法的处理方式), 并让处理器签名携带完整文本"
            "与变更通知回调。"
        ),
    ),
    BenchmarkSample(
        id="BUG-MKP-002",
        kind=SampleKind.BUG,
        title="切换标签页丢失大文件只读保护",
        objective=(
            "打开一个超过 100MB 的文件后 (文件以只读模式打开), 切换到其他标签页"
            "再切回, 该文件的只读保护失效, 变成可编辑状态 — 超大文件一旦被误编辑"
            "有性能与数据风险。请修复: 切换标签页后应恢复该文件正确的只读状态。"
        ),
        requirement=(
            "1. switchToTab 不再无条件把只读标记重置为 false;\n"
            "2. 切换后从文件/缓存状态恢复该文件的只读标记。"
        ),
        project_files=["lib/editor/controllers/file_controller.dart"],
        verifier_id="verify_bug_002_readonly_tab",
        fix_hint=(
            "缺陷定位: file_controller.dart 的标签切换处理逻辑里, 只读标记被无条件"
            "写为关闭状态; 正确做法是从该文件自身的打开记录中读取其只读属性并恢复, "
            "而非一律重置。"
        ),
    ),
    BenchmarkSample(
        id="BUG-MKP-003",
        kind=SampleKind.BUG,
        title="短 UTF-16 BOM 文件被误判为 UTF-8",
        objective=(
            "某些带 UTF-16 BOM 的短文件 (只有 2-3 字节) 被错误识别为 UTF-8 编码, "
            "导致内容显示乱码。请修复编码检测逻辑: BOM 检测应优先于长度判断, "
            "即使文件很短也要先检查 BOM。"
        ),
        requirement=(
            "编码检测函数中, BOM 检查 (0xFF 0xFE / 0xFE 0xFF) 必须位于长度守卫 "
            "(bytes.length < 4) 之前。"
        ),
        project_files=["lib/editor/services/encoding_service.dart"],
        verifier_id="verify_bug_003_bom_order",
        fix_hint=(
            "缺陷定位: encoding_service.dart 的编码探测函数中, 长度不足时提前返回"
            "默认编码的守卫写在字节序标记 (BOM) 探测之前; 修复: 将 BOM 探测调整到"
            "该守卫之前, 保证极短文件也先核对字节序标记。"
        ),
    ),
    BenchmarkSample(
        id="BUG-MKP-004",
        kind=SampleKind.BUG,
        title="撤销/重做后表格对齐与列宽丢失",
        objective=(
            "对包含表格的文档执行撤销 (undo) 后, 表格的列对齐方式 (aligns) 与"
            "列宽 (columnWidths) 丢失, 只剩单元格内容 — 撤销一次表格样式就没了。"
            "请修复快照深拷贝逻辑, 保留表格的完整状态。"
        ),
        requirement=(
            "1. DocumentSnapshot 深拷贝 TableBlock 时保留 rows;\n"
            "2. 同时保留 aligns 与 columnWidths (表格样式不因 undo/redo 丢失)。"
        ),
        project_files=["lib/editor/undo/document_snapshot.dart"],
        verifier_id="verify_bug_004_snapshot_fields",
        fix_hint=(
            "缺陷定位: document_snapshot.dart 的深拷贝辅助中, 表格对象分支仅复制了"
            "单元格行数据, 遗漏了列对齐配置与列宽配置; 修复: 表格分支同步复制这两组"
            "样式字段。"
        ),
    ),
    BenchmarkSample(
        id="BUG-MKP-005",
        kind=SampleKind.BUG,
        title="嵌套有序列表序号错误递增",
        objective=(
            "嵌套有序列表 (顶层 `1. a` 下面缩进一层再写 `1. b`) 保存后重新打开, "
            "内层序号错误递增为 `2. b` — 嵌套层级的有序序号没有独立计数。"
            "请修复: 有序列表序号应按缩进层级独立计数, 每级从 1 开始重新编号。"
        ),
        requirement=(
            "列表序列化时, 有序列表的序号按 indent 层级独立计数 "
            "(每级从 1 重新编号), 不跨层级共享同一个计数器。"
        ),
        project_files=["lib/core/document/serializer.dart"],
        verifier_id="verify_bug_005_nested_list_numbering",
        fix_hint=(
            "serializer.dart 的 _serializeList 用全局 i+1 作有序序号 (嵌套项同样递增); "
            "应维护 per-indent-level 计数器, 层级变化时重置。"
        ),
    ),
]
