# Repository Intelligence 报告 (Phase A++++++-2a)

真实数据来源: [MarkPad](https://github.com/shenlongze/markpad) Flutter 项目
(`/Users/Shared/work/markpad`, 2026-08)。分析器: `factory-exec/exec/
repo_intelligence.py` (L1-L7 全正则级启发式, 零 LLM, 零第三方静态分析库,
零数据库 — KISS 边界)。

## 1. 规模数据

### 1.1 沙箱副本过滤分析 (Benchmark 视角, `project_files=['lib', 'pubspec.yaml']`)

Benchmark 沙箱只复制 `lib/` + `pubspec.yaml` (样本 `project_files` 约束),
Intelligence 分析同口径 — 这是 Developer Agent 实际看到的仓库视图:

| 指标 | 值 |
|---|---|
| 文件数 (files) | **76** |
| 模块数 (modules) | **6** (`(root)` / `lib` / `lib/core` / `lib/editor` / `lib/platform` / `lib/shared`) |
| 依赖边 (dependencies) | **160** (修复后; 见 §3 差异说明) |
| Call Graph 边 (call edges) | **15,723** (修复后) |
| 风险区域 (risk areas) | **39** |
| 入口文件 (entry points) | `lib/app.dart`, `lib/main.dart` |
| 技术栈 (tech stack) | Dart, yaml, Flutter (Dart + flutter) |

### 1.2 全量仓库分析 (Test Map 视角)

沙箱过滤会把 `test/` 目录滤掉 (project_files 副作用, 非 bug — 见
repository-intelligence-pattern.md 陷阱 7), 因此 Test Map 与风险区统计用
全量 528 文件口径:

| 指标 | 值 |
|---|---|
| 文件数 | 528 (含 iOS/Android/桌面平台层 + 测试) |
| Test Map 条目 | 435 条源文件记录, **40 条有测试映射** |
| 风险区域 | 43 (含全量 untested 标注) |

## 2. 风险区域分布 (沙箱口径, 39 处)

| 风险类型 | 数量 | 代表文件 |
|---|---|---|
| `large_file` (>500 行) | 10 | `lib/editor/block_editor.dart` (3451 行), `lib/editor/core/editor_core.dart`, `lib/shared/pages/editor_page.dart`, `lib/shared/widgets/markdown_editor.dart` |
| `complex_module` (被 ≥8 文件依赖) | 5 | `lib/core/document/block.dart` (37 依赖), `lib/core/parser/markdown_parser.dart` (20), `lib/core/document/document.dart` (22), `lib/core/document/serializer.dart` (17) |
| `untested` (high importance 无测试映射) | 24 | `lib/main.dart`, `lib/app.dart`, `lib/editor/editor_view.dart` 等 |

核心风险结论: MarkPad 的**文档模型层** (`lib/core/document/*`) 是最大耦合
区 — `block.dart` 被 37 个文件依赖, 修改它影响面最大; 编辑器层大文件密集
(block_editor 3451 行 / editor_core / markdown_editor), 上下文预算与 diff
冲突风险高。

## 3. 依赖/调用图规模差异说明 (115 → 160, 14931 → 15723)

任务上下文引用的早期数字 (115 deps / 14931 edges) 来自修复前的分析器快照。
本阶段收尾修复了 `resolve_import_target` 的三处解析缺陷 (见
test_exec_repo_intelligence.py 14 failed 修复), 使仓库内依赖边解析更全:

1. **python 单段模块名** (`import b` → `b.py`, `pkg` → `pkg/__init__.py`);
2. **python 相对导入** (`.util` / `..util` 无斜杠形式);
3. **dart 相对裸路径** (`import 'services/b.dart'` 相对源文件目录) +
   **c/cpp include 裸名** (相对源目录)。

dart 是 MarkPad 唯一源码语言, 修复 #3 (dart 相对导入相对源目录解析) 直接
放大 dart 依赖与调用边命中 — 边数增加是**解析能力增强的诚实结果**, 不是
回归。Call Graph 跨文件边仍受「必须 A import B 才建边」约束, 防同名误报。

## 4. 失败样本分析 (Benchmark 失败归因)

数据来源: Phase A++++++-1 真实 Benchmark (5/9 通过, 55.6%) 与 product-proof
报告 §4.1。Repository Intelligence 用 `symbol_definition` + `format_call_graph`
把失败样本定位到 (文件, 行号) 级真实锚点。

### 4.1 超长文件空内容样本 (FEAT-001 类, empty content)

**样本**: 修改 `lib/shared/pages/file_tree.dart` (789 行)。
**Intelligence 定位**:

```
symbol_definition: 文件 789 行 → Architecture 风险区 large_file (789 > 500)
Call Graph: lib/shared/pages/file_tree.dart 被 desktop_layout.dart 调用
           (_DesktopLayoutState/_buildEditorArea @ line 618)
```

**根因精确命中**: 789 行文件全文内联进 prompt 会占满上下文预算
(max_tokens 16384), 模型在超长输入下输出空内容 (empty content 失败样本根因)。
**修复方向** (-2b Context Assembly): 大文件不全文内联, 用 symbol 索引 +
目标符号定义行替换; 本报告 §2 large_file 风险区即该样本的自动标注。

### 4.2 Operation Error 样本 (BUG-003/004, symbol 锚点未命中)

**样本**: 修改 `detect` 与 `_cloneBlock` 两个符号, 早期 Benchmark 报
`operation error` (symbol 锚点定位失败)。
**Intelligence 定位** (真实定义行):

```
symbol_definition("detect")     → [('lib/editor/services/encoding_service.dart', 17)]
symbol_definition("_cloneBlock") → [('lib/editor/undo/document_snapshot.dart', 30)]
```

**Call Graph 归因** (detect 的调用方):

```
called by lib/editor/services/encoding_service.dart::EncodingDetector @ line 17
```

**根因**: 失败发生在 symbol 锚点**未命中定义行** — 静态启发式的定义行索引
与模型猜测的锚点不一致。Intelligence 报告给出 (文件, 行号) 精确锚点,
-2b 上下文组装据此把「符号名 → 真实定义行 + 调用方」注入 prompt, 模型不再
回忆行号。

**结论**: 两个失败样本 (789 行空内容 / operation error) 均可由 Intelligence
定位到真实根因, 归因工具链闭环 (symbol_definition + Call Graph + 风险区)。

## 5. 与 -2b Context Assembly 的衔接

本报告是 -2b Context Engine 的输入数据底座:

- **Architecture Summary** → prompt 顶层「仓库结构」段 (已接入
  `agent_runtime._repo_intelligence_context`: Architecture 摘要 + Call Graph
  摘要段, 失败安全 → 空);
- **Call Graph 段** → 修改目标文件的影响面 (谁调用被改符号 / 被改符号调用谁);
- **symbol_definition** → 失败样本精确锚点 (operation error 修复);
- **large_file 风险区** → 上下文预算控制 (789 行文件不全文内联)。

## 6. 统计口径备注

- 所有数字由 `analyze_repository()` 确定性产出, 同口径可复现;
- Test Map 沙箱口径恒空是 project_files 过滤副作用 (pattern 陷阱 7),
  全量口径 40 条映射;
- Call Graph 为正则级近似, 允许误报/漏报 (KISS 边界, 非编译器级精确图)。
