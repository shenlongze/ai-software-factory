# Sprint 10 — Product Vision: AI Factory User Experience Layer

> 日期: 2026-08-10 | 状态: 设计 (ONLY DESIGN)
> 定位: AI Software Factory 的用户入口系统 — 让"不是程序员"的用户能用 AI Factory

## 1. 产品定位

```
一句话: "我想开发一个 App" → AI Factory 完成产品 + 设计 + 代码 + 测试 + 发布

AI Factory 是: 用户可操作系统 (不是开发者工具集)
用户是: 有想法的普通人 (不是程序员)
价值: 把"想法"变成"可下载的软件" — 全程 AI 员工干活, 用户只做决定
```

## 2. 现状 vs 目标

```
现状 (Sprint 9 后):
  ✅ 生产引擎完整: PM→UX/UI→Arch→Dev→Test→Release 全链真实 (6 Agent)
  ✅ Artifact/Workflow/Approval/Project Adoption 全就绪
  ❌ 用户入口碎片化: CLI 需 PYTHONPATH 手动跑 (91 命令分散)
  ❌ Console 是内部管理台 (只读为主, 无任务提交/LLM 配置)
  ❌ 无"一句话发任务"的产品体验

目标 (Sprint 10):
  ✅ 统一 CLI: 一条 `factory` 命令 (安装即用)
  ✅ 产品 Web 工作台: Dashboard/建项目/看流程/审设计/下结果
  ✅ 用户流程: 打开 → 说想法 → 批准 → 下载
```

## 3. 架构

```
User
 ├── CLI (factory 命令, 终端用户/开发者)
 └── Web Console (产品工作台, 普通用户)
        ↓
    API Layer (fastapi 8011 扩展: 任务提交/审批/配置)
        ↓
    AI Factory Core (Workflow/Artifact/Approval/Agent Executor — Sprint 1-9 全复用)
```

## 4. 原则

```
1. 不重复建设: 全部复用 Sprint 1-9 (Workflow/Artifact/Approval/Agent)
2. 用户零配置: factory init 一键装好 (key 从 ~/.hermes/.env 或 .factory/.env)
3. 人工控制: 每个关键节点 (PRD/设计/发布) 用户批准 (审批门已有)
4. 诚实展示: 每阶段 Agent/状态/成本/耗时 (Build Monitor)
5. 中文优先: 界面与反馈面向中文普通用户
```
