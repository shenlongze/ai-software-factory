# S9-004 — Existing Project Adoption（Completion Report）

> 日期: 2026-08-09 | 状态: 完成 (待人工审核) | pytest 6456 (6416 + 40)
> 目标: AI Factory 支持已有软件项目 (注册→分析→基线→快照)

## 实现说明

```
1. Project Registration (org.projects 扩展):
   Project 新增 repo_path/language/framework/build_command/test_command/project_type
   (+ analysis_ref/baseline_ref/snapshot_ref) — 全带默认值向后兼容
   CLI: org CLI project register 子命令

2. Repository Analyzer (exec/project_adoption.py 新建):
   detect_language (清单强信号 + 扩展名统计, 跳噪声目录)
   detect_framework (pubspec/pyproject/package.json 等)
   analyze_project (复用 repo_intelligence L2/L3/L6/L7)
   → project_analysis Artifact (6 字段契约)

3. Baseline Validation:
   注册后自动 build (build_command 或 ast.parse 语法检查) + test (pytest 风格计数)
   + analyze → baseline Artifact {build, test, analysis_ref}
   失败安全: 命令缺失 → unavailable (注册永不失败)

4. Context Snapshot:
   浅层目录树 + File Importance 排序 + 架构摘要 → snapshot Artifact (供 Agent)

5. 事件 +4 (182→186): org.project.registered/analyzed/baseline_recorded/context_snapshotted
```

## 数据流

```
register(repo_path, language, build_cmd, test_cmd)
  → Project 创建 → analyze (project_analysis) → baseline (build/test)
  → snapshot (tree/important files) → refs 回写 → 4 事件
```

## 测试（40 新增）

```
analyzer: 语言/框架检测/结构/依赖/空仓库回退
registration: 全链 (register→analyze→baseline→artifact)/失败安全/向后兼容
```

## 限制（诚实）

```
1. 未接入真实 MarkPad (通用能力先行 — 用户约束)
2. build/test 命令为显式配置或语法级检查 (无包管理器完整构建)
3. repo_intelligence 复用 (Python/Dart/JS 已支持语言集)
```

## S9-005 接入说明

```
后续: 注册项目 → Workflow Run 直接用 snapshot/analysis 作为 Agent 输入上下文
     (已有项目 bug/feature 任务闭环)
     S9-006 真实试点: 注册 DevToolBox/MarkPad lib 子集 → 小任务验证
```
