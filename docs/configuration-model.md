# 配置模型审计 (configuration-model)

> 版本: v1.0 | 日期: 2026-08-06 | 状态: 与 v1.0 Release 一致
> 关联文档: [provider-selection-model.md](./provider-selection-model.md) · [extension-model.md](./extension-model.md) · [system-architecture-review.md](./system-architecture-review.md)

本文档审计系统四类配置的**位置 / 结构 / 可发现性 / 可解释性 / 可修改方式**:

- **Provider** — 用什么脑子 (LLM 来源)
- **Runtime** — 谁去干活 (执行方式)
- **Project** — 管什么项目
- **Agent** — 谁来干 (角色 + 技能)

共同铁律: **全部声明式 JSON/YAML, 改配置不改 Core**; 配置变更全部发审计事件, 可追溯。

---

## 0. 工厂根 (所有配置的落盘位置)

```
<root>/                  # 默认 ~/.factory, 可用 --root 覆盖 (验证环境用 $SMOKE_ROOT)
├── factory.db           # SQLite EventStore (events 表, append-only, WAL)
├── tasks/               # 任务 JSON 存储 (task-*.json)
├── agents/agents.json   # Agent 注册表 (运行时实例)
├── skills/skills.json   # Skill 注册表 (运行时实例)
├── workflows/           # 工作流定义 JSON
├── runtimes/runtimes.json  # Runtime 实例可用状态 (Registry)
├── runtimes/catalog.json   # Runtime 能力描述 (Catalog, 用户注册项)
├── providers/catalog.json  # Provider 定义文件库 (用户注册项)
├── checkpoints/         # 断点快照
└── events/              # 事件导出
```

---

## 1. Provider 配置

| 维度 | 内容 |
|:-----|:-----|
| **位置** | `providers/catalog.json` (ProviderFileStore, 独立 `providers/` 目录); 默认定义基线在代码常量 `factory-core/providers/definitions.py` (合并展示, **永不自动写入 catalog.json**) |
| **结构** | `ProviderDefinition`: id / name / provider_type / capabilities / cost (token/request/time/free) / performance (declared vs actual) / 统一输入输出契约; `runtime_preferences` 声明角色偏好 |
| **可发现性** | `factory provider list` (全部) / `provider show <id>` (详情) / `provider test` (连通) / `provider usage` / `provider stats` / `provider compare` / `provider recommend`; Dashboard Providers 视图; Console `/api/providers` |
| **可解释性** | 每次选择发 `provider.selected` 事件, 附四因素 (Capability 0.35 / Cost 0.30 / Performance 0.20 / Experience 0.15) 逐项得分 + 方向 + 原因文本, 可逐项复算 |
| **可修改方式** | ① catalog.json 声明式注册 (新 Provider); ② `runtime_preferences` (project.yaml 可选字段) 声明角色 → `{provider, runtime}` 偏好; ③ CLI `provider add/use`; 选择优先级链: **Project > Agent > Runtime > Default** (ADR-0023) |

```yaml
# project.yaml 中的 Provider 偏好 (Phase 6A 字段, ProviderSelector 路由依据)
runtime_preferences:
  architect:  { provider: claude }   # 架构决策 → Claude
  developer:  { provider: codex }    # 编码 → Codex
  tester:     { provider: hermes }   # 验证/测试 → Hermes
```

---

## 2. Runtime 配置

**三层分离原则** (ADR-0014): 目录不派发、注册不执行 — 有目录不一定已注册, 已注册不一定在执行。

| 层 | 位置 | 结构 | 可发现性 |
|:---|:-----|:-----|:---------|
| **Catalog (能力目录)** | `runtimes/catalog.json` + 内置默认定义 (hermes/echo/mock, **只读不可移除**) | `RuntimeDefinition`: id / type / capabilities / description; `find_by_capability()` 能力搜索 | `factory runtime catalog list` / `catalog show` |
| **Registry (实例状态)** | `runtimes/runtimes.json` | 实例 id / type / status (AVAILABLE/...), 谁可用谁禁用 | `factory runtime list` / `runtime test` |
| **Adapter (执行器)** | `factory-core/runtime/adapters/` (`hermes.py` 默认实跑 / `echo.py` 冒烟) | `RuntimeAdapter` 接口: `execute(request) -> ExecutionResult` | `factory runtime test <id>` 连通性验证 |

**可解释性**: 注册/移除/查看均发 `runtime.catalog.*` / `runtime.*` 事件; Dashboard Runtime Usage 视图。
**可修改方式**: 新 Runtime = 新 Adapter 文件 (实现接口) + `runtime add` 注册 + (可选) catalog.json 能力声明; **Core 零改动**。生产接入: `runtime add --id hermes-runtime --type agent` + `FACTORY_HERMES_CMD` 指向 hermes CLI。

---

## 3. Project 配置

| 维度 | 内容 |
|:-----|:-----|
| **位置** | `examples/markpad/project.yaml` (加载器: `factory-core/project/loader.py`); 多项目挂载: workspace/ 层 |
| **结构** | `name` (唯一 id) / `language` / `repository` (本地路径或远程 URL) / `description` / `tech_stack` (对应 skills 的 id) / `runtime_preferences` (可选) |
| **可发现性** | `factory project list` / `project show <name>`; Dashboard Projects 视图; Console `/api/projects` + `/api/projects/{id}/lifecycle` |
| **可解释性** | 加载解析只读展示; 项目相关事件 (workspace.* / project.*) 全量审计; 生命周期状态 (8 阶段链) 可在 Console 查看 |
| **可修改方式** | **只读声明**: 改 YAML 换项目 (换项目只改 4 个 YAML: project/agents/skills/workflows, 不动 factory-core); 任务/执行等运行时数据仍走 CLI 与引擎 API |

```yaml
# examples/markpad/project.yaml (完整示例)
name: markpad
language: dart
repository: /Users/Shared/work/markpad
description: "MarkPad — 跨平台 Markdown 编辑器 (Flutter/Dart, Typora-like)"
tech_stack: [flutter, dart]
```

---

## 4. Agent + Skill 配置

| 维度 | Agent | Skill |
|:-----|:------|:------|
| **位置** | `examples/markpad/agents.yaml` (只读声明) + 运行时 `agents/agents.json` | `examples/markpad/skills.yaml` (能力目录) + 运行时 `skills/skills.json`; 自定义 Skill = SKILL.md + meta.json |
| **结构** | `id` / `name` / `role` / `skills[]` / `description`; Agent = 角色 + skill 集 + runtime 偏好 | `id` / `name` / `category` / `version` / `capabilities[]` / `description` (内置集: flutter/frontend/backend/testing/validation) |
| **可发现性** | `factory agent list` / `agent assignments`; Dashboard Agents/Utilization 视图 | `factory skill list`; Skill 经 Agent 匹配展示 |
| **可解释性** | 匹配语义透明 (role 精确 + skills 命中≥1, ADR-0008); 每次分配发 `agent.assignment.*` 事件, 含匹配依据 | 技能引用关系可查 (agents.yaml ↔ skills.yaml token 一致校验) |
| **可修改方式** | `agent add/assign/release` (CLI) 或改 agents.yaml 声明后经引擎 API 注册 | `skill add` (CLI) 或新增 SKILL.md + meta.json 登记 |

```yaml
# examples/markpad/agents.yaml (摘录)
agents:
  flutter-developer:
    name: Flutter 开发者
    role: developer
    skills: [flutter, dart]
  tester:
    name: 测试工程师
    role: test-engineer
    skills: [testing, dart]
```

---

## 5. 审计结论

1. **四类配置全部声明式**, 位于工厂根 JSON stores 或 examples YAML 声明; 换工具/换模型/换项目 = 改配置, Core 零改动。
2. **可发现性完整**: 每类配置均有对应 CLI 命令 (`provider list` / `runtime catalog list` / `project show` / `agent list` / `skill list`)、Dashboard 视图与 Console 只读 API。
3. **可解释性完整**: 配置变更与使用全部发审计事件; 选择类决策 (Provider 推荐) 附可复算的四因素得分与原因文本。
4. **修改路径清晰**: 声明式文件 (新定义) + CLI (运行时实例) 双通道, 互不冲突; 默认定义 (runtime hermes/echo/mock、provider 基线) 只读不可覆盖删除。
