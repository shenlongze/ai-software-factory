"""factory-exec/exec/benchmark/features.py — Benchmark Feature 样本集 (3 个真实需求)。

来源: markpad lib/ 只读分析 — 3 个中小功能需求, 均与现状对照核实为未实现:
- FEAT-MKP-001: 最近文件列表只显示文件名, 无修改时间。
- FEAT-MKP-002: 文件大小以裸字节数显示, 无人类可读格式化。
- FEAT-MKP-003: 标签页无未保存修改 (dirty) 指示器。

与已实现功能区分 (避免「零改动即通过」的坏样本):
- Cmd+Shift+F 已被 Focus Mode 占用 → 不选「全局搜索快捷键」;
- HTML 导出已有 <title> → 不选「导出标题」;
- 字数统计/行号开关均已实现 → 不选。
"""

from __future__ import annotations

from .models import BenchmarkSample, SampleKind

#: 3 个真实 Feature 样本 (中小功能, 自然语言需求 + verifier 验收)
FEATURE_SAMPLES: list[BenchmarkSample] = [
    BenchmarkSample(
        id="FEAT-MKP-001",
        kind=SampleKind.FEATURE,
        title="最近文件显示相对修改时间",
        objective=(
            "侧边栏「最近文件」区域目前只显示文件名, 用户无法分辨哪个文件最新。"
            "请新增: 每个最近文件条目显示相对修改时间 (如「3 分钟前」), "
            "并在进入文件时把该文件移到列表顶部。"
        ),
        requirement=(
            "1. 最近文件条目渲染时引用文件的修改时间字段 (modifiedAt);\n"
            "2. 以相对时间格式 (如「3 分钟前」) 显示, 而非裸时间戳。"
        ),
        project_files=["lib", "pubspec.yaml"],
        verifier_id="verify_feat_001_recent_time",
        source_files=["lib/shared/pages/file_tree.dart"],
        fix_hint=(
            "file_tree.dart 的 _buildRecentFiles 条目 itemBuilder 中, "
            "在文件名旁追加显示 file.modifiedAt 的相对时间文本 (新增相对时间辅助函数)。"
        ),
    ),
    BenchmarkSample(
        id="FEAT-MKP-002",
        kind=SampleKind.FEATURE,
        title="文件大小人类可读格式化",
        objective=(
            "文件树与最近文件以裸字节数显示文件大小 (如 123456), 不直观。"
            "请新增人类可读大小格式化: 显示如「12.5 KB」「3.2 MB」。"
        ),
        requirement=(
            "1. 在 MdFile 模型上新增 formatSize 辅助 (按 1024 进制格式化字节数);\n"
            "2. 包含 KB/MB/GB 单位分支 (B 以下返回字节数 + B)。"
        ),
        project_files=["lib", "pubspec.yaml"],
        verifier_id="verify_feat_002_format_size",
        source_files=["lib/shared/models/md_file.dart"],
        fix_hint=(
            "缺陷定位: md_file.dart 中文件模型缺少大小格式化能力, 界面直接展示原始"
            "字节数; 修复: 在模型上新增格式化辅助, 按 2 的 10 次方进位, 不足 1K 显示"
            "字节数加 B 单位, 更大数值分别以 KB、MB、GB 为单位展示并保留一位小数。"
        ),
    ),
    BenchmarkSample(
        id="FEAT-MKP-003",
        kind=SampleKind.FEATURE,
        title="标签页未保存修改指示器",
        objective=(
            "标签页无法直观显示文件是否有未保存修改 — 用户切走再切回容易忘记保存。"
            "请新增: 有未保存修改的文件, 其标签上显示一个修改指示点 (dirty 指示器), "
            "保存后指示点消失。"
        ),
        requirement=(
            "1. 标签栏组件感知 dirty/未保存状态 (接收该状态);\n"
            "2. 未保存的标签上渲染修改指示器 (如小圆点)。"
        ),
        project_files=["lib", "pubspec.yaml"],
        verifier_id="verify_feat_003_tab_dirty",
        source_files=["lib/shared/widgets/tab_bar.dart"],
        fix_hint=(
            "缺陷定位: tab_bar.dart 的标签组件未感知未保存状态; 修复: 为标签组件接入"
            "未保存标记数据 (按文件路径记录的布尔映射或通知回调), 对存在未保存标记的"
            "标签, 在文件名旁绘制一个小圆点, 保存完成后圆点移除。"
        ),
    ),
]
