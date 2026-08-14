# S10-046 Task 005 — Session Context Design

> 日期:2026-08-14 | Sprint: S10-046 CLI Design v2 | 设计, 未修改代码

---

## 1. Terminal Session vs Runtime Execution Session

| 维度 | Terminal Session | Runtime Execution Session |
|---|---|---|
| 定义 | 交互 CLI 会话(用户状态) | 一次任务执行(agent 运行上下文) |
| 生命周期 | 用户进入 `factory` 到 `/exit` | 一次 run 从开始到 artifact |
| 保存内容 | current project/agent/conversation | request/result/events |
| 持久化 | 是(跨会话恢复) | 是(exec store 已有) |
| 存储 | session.json | ~/.factory/exec/(已有) |

**两者独立: Terminal Session 是"用户工作台状态", Runtime Session 是"执行记录"。**

## 2. Terminal Session 保存内容

| 字段 | 说明 | 默认 |
|---|---|---|
| current_project | 当前项目 (id/name/path) | 最近使用 |
| current_agent | 当前 Agent | backend-1 |
| current_provider | 当前 Provider | (Router 决策) |
| recent_tasks | 最近 10 次执行 | 空 |
| conversation | 会话内对话记录 (Intent/结果摘要) | 空 |
| started_at / updated_at | 时间戳 | now |
| session_id | 唯一 ID | uuid |

## 3. 生命周期

```
factory (无参数) → 加载最近 session (若有) → 显示 "欢迎回来, 当前项目: X"
  ├── 用户操作 (slash/intent/命令) → 更新 current_*/recent_tasks
  ├── /session reset → 清空会话状态
  ├── /exit → 保存 session.json → 退出
  └── 超时/崩溃 → 自动保存 (每操作后持久化)
```

## 4. 持久化

| 项 | 决策 |
|---|---|
| 是否持久化 | ✅ 是(跨会话恢复) |
| 存储位置 | `~/.factory/session.json`(demo: `~/.factory-demo/session.json`) |
| 格式 | JSON(与 config.json 同风格) |
| 保存时机 | 每操作后 + 退出时 |
| 恢复 | 进入会话时自动加载 |
| 保留策略 | 1 个活跃 session + 历史归档(最多 5 个) |

## 5. 安全边界

| 风险 | 防护 |
|---|---|
| 敏感信息 (key) | session.json **绝不存 key** (只存 provider_id 引用) |
| 路径注入 | project/agent 值来自 Registry, 非任意字符串 |
| 越权执行 | 恢复的 current_* 仅作参数默认, 执行前 Policy Check |
| 并发冲突 | 单用户本地; 多终端 → 最后写入胜出 (记录 warning) |
| 明文泄露 | conversation 只存摘要不存完整 prompt/response |

## 6. 会话内命令如何用上下文

```
/run --objective "加测试"          → project=current_project, agent=current_agent
"给当前项目加测试" (Intent)         → 同上 + policy 确认
/project my-other-app              → 切换 current_project
/session show                      → 显示全部会话状态
/session reset                     → 清空 (回到默认)
```

## 7. 与 Command Mode 的关系

- Command Mode **不使用** Terminal Session(每次独立, 保持可脚本化)
- 显式参数优先于会话上下文
- 未来可选: `factory run --use-session` 读取会话状态(显式 opt-in)

---

> Task 005 完毕 | Terminal Session(用户状态) vs Runtime Session(执行记录) | session.json 持久化 | 禁存 key
