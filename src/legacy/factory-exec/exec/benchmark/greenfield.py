"""factory-exec/exec/benchmark/greenfield.py — Benchmark Greenfield 样本 (1 个小项目)。

GREENFIELD-001: 命令行待办管理工具 (todo.py) — 从零构建。
- 空沙箱 (无项目文件): Agent 产出整个项目 (todo.py + 行为契约)。
- verifier 真实运行 CLI (subprocess 调 todo.py, 断言 add/list/done/remove
  /list --all 行为 + JSON 持久化) — 不依赖 LLM, 不 mock。
"""

from __future__ import annotations

from .models import BenchmarkSample, SampleKind

#: 1 个 Greenfield 样本 (小项目, 行为契约由 verifier 真实运行验证)
GREENFIELD_SAMPLES: list[BenchmarkSample] = [
    BenchmarkSample(
        id="GREENFIELD-001",
        kind=SampleKind.GREENFIELD,
        title="命令行待办管理工具 (todo.py)",
        objective=(
            "从零构建一个命令行待办事项管理工具 todo.py "
            "(Python 3, 仅标准库, 零第三方依赖), 要求:\n"
            "1. `python3 todo.py add \"任务描述\"` — 添加任务, 输出分配的任务 id;\n"
            "2. `python3 todo.py list` — 列出未完成任务 (含 id 与描述);\n"
            "3. `python3 todo.py done <id>` — 按 id 标记完成;\n"
            "4. `python3 todo.py remove <id>` — 按 id 删除任务;\n"
            "5. `python3 todo.py list --all` — 列出全部任务 (含已完成);\n"
            "6. 数据以 JSON 持久化到当前目录 (todo.json), 重启后不丢失。"
        ),
        requirement=(
            "1. todo.py 位于交付物根目录, 可被 `python3 todo.py ...` 直接执行;\n"
            "2. add/list/done/remove/list --all 五个命令行为符合上述契约;\n"
            "3. 任务数据 JSON 持久化 (todo.json 落在运行目录)。"
        ),
        project_files=[],
        verifier_id="verify_greenfield_todo_cli",
        fix_hint="",  # 无隐藏答案 — 从零构建
    ),
]
