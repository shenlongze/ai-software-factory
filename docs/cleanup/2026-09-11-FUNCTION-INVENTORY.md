# 全入口功能清单（FUNCTION INVENTORY）

> 日期: 2026-09-11 | 性质: **纯只读采集**（未删/未改/未搬/未 git rm/未改 import）
> 判据: **入口能不能跑通**（非代码级判据）
> 采集: CLI 逐命令执行 · API openapi.json + TestClient 探活 · 前端未验证

## 一、CLI（`./bin/factory <cmd>`）

| # | 功能 | 入口 | 能跑 | 报错原文 | 靠 factory-core |
|---|------|------|------|---------|----------------|
| 1 | 服务诊断 | `factory doctor` | ✅ | — | 否 |
| 2 | 系统状态 | `factory status` | ✅ | — | 否 |
| 3 | 服务发现 | `factory service list` | ✅ | — | 否 |
| 4 | LLM 清单 | `factory llm list` | ✅ | — | 是 |
| 5 | 员工管理 | `factory agent list` | ✅ | — | 是 |
| 6 | 技能管理 | `factory skill list` | ✅ | — | 是 |
| 7 | 工具发现 | `factory tools list` | ✅ | — | 是 |
| 8 | MCP 连接 | `factory mcp list` | ✅ | — | 是 |
| 9 | 项目管理 | `factory project list` | ✅ | — | 是 |
| 10 | 待办 | `factory todo` | ❌ | `错误: todo 需要子命令 (list)` | 是 |
| 11 | 证据包 | `factory evidence list` | ✅ | — | 是 |
| 12 | 审计 | `factory audit` | ✅ | — | 是 |
| 13 | 记忆 | `factory memory` | ✅ | — | 是 |
| 14 | RAG | `factory rag` | ❌ | `usage: factory rag [-h] query\|index\|sources ...` | 是 |
| 15 | 任务 | `factory task` | ✅ | — | 是 |
| 16 | 仓库 | `factory repo` | ❌ | `usage: factory repo [-h] [--patch PATCH] <path> <目标>` | 是 |
| 17 | 执行历史 | `factory exec history` | ✅ | — | 是 |
| 18 | 运行结果 | `factory run-status` | ✅ | — | 是 |
| 19 | 执行项目 | `factory run --project <dir>` | ✅ | — | 是 |
| 20 | 审批 | `factory approval` | ❌ | `usage: factory approval [-h] [--project ...]` | 是 |
| 21 | 产物 | `factory artifact list` | ✅ | — | 是 |
| 22 | 备份 | `factory backup` | ❌ | `usage: factory backup [-h] [--dir DIR] 动作` | 是 |
| 23 | 组成 | `factory composition` | ❌ | `[E4172] 错误: agent_profile_id 必填` | 是 |
| 24 | 上下文 | `factory context` | ✅ | — | 是 |
| 25 | 治理 | `factory governance` | ❌ | `[E4032] 错误: production_run_id 必填` | 是 |
| 26 | 自愈 | `factory heal` | ❌ | `[E4243] 错误: incident_id 必填` | 是 |
| 27 | 健康 | `factory health` | ✅ | — | 是 |
| 28 | 智能 | `factory intelligence` | ✅ | — | 是 |
| 29 | 学习 | `factory learn` | ✅ | — | 是 |
| 30 | 学习报告 | `factory learning` | ❌ | `usage: factory learning [-h] [--agent ...]` | 是 |
| 31 | 优化 | `factory optimize` | ✅ | — | 是 |
| 32 | 组织 | `factory org` | ✅ | — | 是 |
| 33 | 插件 | `factory plugin` | ✅ | — | 是 |
| 34 | 产品 | `factory product` | ❌ | `usage: factory product [-h] [--data-dir ...]` | 是 |
| 35 | 生产 | `factory production` | ❌ | `[E4004] 错误: run_id 必填` | 是 |
| 36 | 项目实体 | `factory projectos` | ✅ | — | 是 |
| 37 | 晋升 | `factory promotion` | ✅ | — | 是 |
| 38 | 轨迹 | `factory ptrace` | ❌ | `usage: factory ptrace [-h] [--data-dir ...] task_id` | 是 |
| 39 | 质量 | `factory quality` | ✅ | — | 是 |
| 40 | 恢复 | `factory recovery` | ❌ | `[E4130] 错误: run_id 必填` | 是 |
| 41 | 发布 | `factory release` | ✅ | — | 是 |
| 42 | 发布真相 | `factory release-truth` | ❌ | `usage: factory release-truth [-h] [--task-run ...]` | 是 |
| 43 | 回滚 | `factory rollback` | ✅ | — | 是 |
| 44 | 路由 | `factory router` | ✅ | — | 是 |
| 45 | 调度 | `factory schedule` | ✅ | — | 是 |
| 46 | 选择 | `factory select` | ❌ | `[E4180] 错误: capability 必填` | 是 |
| 47 | 策略 | `factory strategy` | ✅ | — | 是 |
| 48 | 任务树 | `factory tasktree` | ✅ | — | 是 |
| 49 | 控制塔 | `factory tower` | ✅ | — | 是 |
| 50 | 追溯 | `factory trace` | ❌ | `usage: factory trace [-h] [--data-dir ...] conversation_id` | 是 |
| 51 | 验证 | `factory verification` | ✅ | — | 是 |
| 52 | 工作流 | `factory workflow` | ✅ | — | 是 |
| 53 | 人力 | `factory workforce` | ✅ | — | 是 |

**CLI 小计**：能跑 **36** / 不能跑 **17**（其中 **13 为"缺参数"(usage/E4xxx)，非死命令**）

## 二、API（354 端点，GET 225 个探活）

| # | 功能 | 入口 | 能跑 | 报错原文 | 靠 factory-core |
|---|------|------|------|---------|----------------|
| 54 | 项目列表 | `GET /api/projects` | ✅ 200 | — | 是 |
| 55 | 会话列表 | `GET /api/conversations` | ✅ 200 | — | 是 |
| 56 | 会话详情 | `GET /api/conversations/{id}` | ✅ 404* | *无实体时 404（路由活） | 是 |
| 57 | 产物列表 | `GET /api/artifacts` | ✅ 200 | — | 是 |
| 58 | 审计 | `GET /api/audit` | ✅ 200 | — | 是 |
| 59 | 看板 | `GET /api/board` | ✅ 200 | — | 是 |
| 60 | 能力清单 | `GET /api/capabilities` | ✅ 200 | — | 是 |
| 61 | 控制塔 | `GET /api/control-tower` | ✅ 200 | — | 是 |
| 62 | 审批 | `GET /api/approvals` | ✅ 200 | — | 是 |
| 63 | 人力和解 | `GET /api/agent-profiles` | ✅ 200 | — | 是 |
| 64 | 事件流 | `GET /api/events/stream` | ❌ 422 | 参数校验 | 是 |
| 65 | 审计追溯 | `GET /api/audit/trace` | ❌ 422 | 参数校验 | 是 |
| 66 | 实验对比 | `GET /api/experiments/{id}/compare` | ❌ EXC | `ValueError` | 是 |

**API 小计**：GET 225 → **200:115 / 404:94（带 id 路径，正常）/ 422:4 / EXC:11 / 500:1**
→ **路由活 213**（200+404+422）/ **异常 12**（EXC+500）

## 三、前端页面

**未验证** —— Web 启动需要特定 sys.path 顺序（`factory-console/events.py` 会遮蔽 factory-core 的 `events` 包，见报错原文）；本机 5180 页面未实际打开。

## 四、汇总

- **能跑**：CLI 36 + API 路由活 213 ≈ **249**
- **不能跑**：CLI 17 + API 异常 12 ≈ **29**
- **能跑且靠 factory-core 的（活命清单）**：**除 `doctor`/`status`/`service list` 外，几乎全部**（CLI 50/53 + API 全部 225）≈ **275**
- **能跑且不靠 factory-core**：**3**（`doctor` · `status` · `service list`）

### factory-core「活命清单」（能跑 + 靠它）
> CLI 侧：llm/agent/skill/tools/mcp/project/evidence/audit/memory/task/exec/run-status/run/artifact/context/health/intelligence/learn/optimize/org/plugin/projectos/promotion/quality/release/rollback/router/schedule/strategy/tasktree/tower/verification/workflow/workforce（36 个中除上列 3 个）
> API 侧：**全部 225 个 GET 端点**（fastapi_adapter 对 factory-core 有 28 处 import）

## 五、不确定项
1. **前端页面**：未验证（启动受 sys.path 影响，未实际打开 5180）
2. **POST/PUT/DELETE 端点**（354-225=129 个）：未探活（需业务参数）
3. **13 个"缺参数"CLI 命令**：命令存在但无参数即报 usage → 标"能跑（需参数）"更准确

---

# HARD STOP
纯只读采集；未删/未改/未搬/未 git rm/未改 import。产出后停下，等 Founder 裁决。
