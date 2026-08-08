# AI Software Factory — Composable Capability Architecture

> 状态: DESIGN ONLY (蓝图, 未实现或部分实现: 能力架构蓝图, 大部分未落地 — 见 ./audit/architecture-reality-audit.md)

> 日期: 2026-08-06 | 状态: 架构约束 (Architecture Freeze 补充)
> 关联: architecture-freeze-2026-08.md / design-principles.md

## 核心定位

AI Software Factory 的最终目标不是包含所有功能的大程序, 而是:

**AI Capability Operating System** — 所有能力都是可组合积木 (Building Block)。

```
Capability = Building Block
- 独立存在 / 明确输入 / 明确输出 / 能力描述 / 可发现 / 可组合 / 可替换
```

类似硬件 (CPU/GPU/内存/硬盘) 对应软件 (Skill/MCP/Runtime/Agent/Workflow/Provider)。

## 一、Modular Independence Principle

### 1. 独立目录
```
factory-core/
├── understanding/     (Phase 7)
├── product/           (未来)
├── operations/        (未来)
├── marketing/         (未来)
└── automation/        (未来)
每模块: models.py + service.py + events.py + README.md + tests/
```

### 2. 独立生命周期
```
install / enable / disable / remove
例: 关闭 Git 模块 → Core 不受影响; 关闭 Product Intelligence → 开发流程仍运行
```

### 3. 独立依赖 (禁止业务模块互 import)
```
❌ product/service.py import git.service
✅ product/service.py 调用 ChangeProvider Interface
```

### 4. 声明式注册
```yaml
# module.yaml
name: product-intelligence
version: 1.0
capabilities: [idea-analysis, prd-generation]
dependencies: [core]
```

### 5. Event 通信 (模块不知道谁消费事件)
```
idea.completed → prd.generator
prd.approved → workflow.create
workflow.completed → deployment.start
```

### 6. 数据隔离
```
.factory/
├── core/  ├── understanding/  ├── product/  ├── operations/  └── automation/
禁止: 模块修改其他模块数据文件
```

### 7. 独立测试
每模块独立测试 (内部 + 接口契约 + Event); 禁止大量跨模块测试作为唯一保障。

### 8. 最终判断标准
```
删除一个模块 → 系统还能启动, Core 还能运行, 其他模块不受影响
```

## 二、Composable Capability

### 组合示例
```
App Creation Workflow:    Market Research + PRD + UI + Architecture + Coding Agent + Testing Agent + Deployment Runtime
Social Media Automation:  Market Analysis + Content Generator + Image MCP + Scheduler Runtime
Operation Automation:     Monitor Skill + Alert MCP + Incident Workflow + Operation Agent
```

### Factory 职责 (不拥有所有能力)
```
1. 发现能力    Capability Registry
2. 理解能力    Metadata
3. 组合能力    Workflow
4. 调度能力    Agent / Runtime
5. 审计能力    Event
```

### Capability Contract
```yaml
# capability.yaml
name: prd-generator
type: skill
input: idea
output: prd_document
requires: llm-provider
approval: required
```

### 禁止事项
```
禁止: 一个模块内部包含完整业务流程 (marketing 模块里写文章+发布+统计+用户管理)
正确: 拆成 content-generator + publish-runtime + analytics-skill
```

## 三、Capability Extension 统一模型

未来能力统一为 Capability Extension, 不全部写入 Factory:
```
Skill (能力)      wechat-operation / flutter-development
MCP (工具)        database-access / github
Runtime (执行)    hermes / codex
Provider (LLM)    claude / openai / local
Plugin (第三方)    code-review / openclaw skill
```
Factory 只负责: 发现 / 注册 / 调度 / 审计。

## 四、UI 独立原则

```
Web UI 不是 Core — UI 是 Human Layer (React/Vue/Mobile/Desktop 可替换)
Core 提供: API + Event + State
```

## 五、对 Phase 7 的约束 (立即生效)

```
1. understanding 模块独立目录 + 独立测试 + 独立数据空间 (.factory/understanding/)
2. 禁止 import 其他业务模块 (只可调 Core Interface: project/workspace/git 经接口)
3. Event 通信 (understanding.started/completed/failed)
4. 删除 understanding → 系统仍运行 (零 Core 依赖)
5. capability.yaml 声明 (understanding: 输入=项目路径, 输出=Understanding Report)
```

## 六、未来生态

```
第三方开发 Skill/Plugin/MCP/Agent → Factory Marketplace
用户: 安装积木 → 拖拽组合 → 生成自己的 AI 工作流
最终愿景: 用户选择"我要完成什么事情" → Factory 自动组合 (能力积木→Workflow→Agent→执行)
```
