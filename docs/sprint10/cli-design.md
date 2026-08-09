# Sprint 10 — Factory CLI Design

> 日期: 2026-08-10 | 状态: 设计 (ONLY DESIGN)
> 目标: 统一 CLI 入口 (一条 `factory` 命令, 安装即用)

## 1. 安装与启动

```
安装:  (项目内)
  pip install -e . 或 ln -s scripts/factory 到 PATH
  → `factory` 全局可用 (零 PYTHONPATH)

factory init      # 初始化 ~/.factory (workspace/org/LLM 配置)
factory start     # 启动本地服务 (后端 8011 + Web 5180) + 打开浏览器
factory status    # 系统状态 (LLM 连接/项目数/运行中 workflow/待审批)
```

## 2. 命令结构（10 核心命令）

```
factory init                    初始化 (幂等; 检测 ~/.hermes/.env 或提示配置)
factory start [--port 8011]     启动服务 + open browser
factory status                  状态摘要
factory project list            项目列表 (id/name/status/progress)
factory project create "<想法>"  创建项目 (Idea → Workflow 自动启动)
factory run <project-id>        执行/继续 Workflow
factory workflow list [--id]    工作流列表/详情 (8 阶段链)
factory artifact list [--project] [--type]   产物列表
factory review [--pending]      等待审批清单 (门 id/stage/摘要)
factory approve <gate-id> [--comment]       批准
factory reject <gate-id> --comment <意见>    驳回+意见
factory logs [--project] [--tail N]         执行日志
```

## 3. 参数与输出规范

```
参数: 子命令 + 位置参数 (id/想法) + 可选 flags (--json 输出 JSON)
输出: 人类可读 (表格/树) + --json 机器可读 (与 API 同构)
退出码: 0 成功 / 1 业务失败 (含原因) / 2 用法错误

示例:
  $ factory project create "开发一个记账 App"
  ✓ 项目 created: P-abc123
  → PM Agent 开始分析 (预计 60s)...
  $ factory review
  ┌────────────┬──────────┬────────────────────────────┐
  │ Gate       │ Stage    │ 摘要                       │
  ├────────────┼──────────┼────────────────────────────┤
  │ AG-xyz     │ product  │ PRD: 记账 App 功能范围      │
  └────────────┴──────────┴────────────────────────────┘
  $ factory approve AG-xyz
  ✓ 已批准 → UX/UI Designer 开始设计...
```

## 4. 与现有系统对接（避免重复建设）

```
复用: cli.main (26 组命令) + org.cli (project/workflow/approval) + exec.cli
包装: factory = 统一入口 → 委托到现有 CLI 函数 (不重写)
状态: ~/.factory 为唯一数据根 (workspace/org/intelligence/providers)
LLM key: 从 ~/.hermes/.env 读 DEEPSEEK_API_KEY (进程内注入, 禁明文)
事件: factory logs = events 流查询 (org.* / org.workflow.* / org.approval.*)
```

## 5. 用户流程示例

```
# 开发者用 CLI 做完整流程
factory init
factory project create "给 DevToolBox 加个颜色转换工具"
factory review          # 等 PRD → 批准
factory review          # 等设计 → 批准
factory run P-xxx       # 继续 Dev→Test→Release
factory artifact list --project P-xxx
```
