# AI Factory 功能文档（FEATURES）

> **单一事实来源** — 当前系统到底有哪些功能、每个功能是什么、怎么用（CLI / API / 会话命令）、什么状态、从哪个版本开始有。
>
> 版本: **v1.1.48** · 更新: 2026-08-24 · 依据: 实测命令 + 代码核对 + CHANGELOG

## 0. 文档定位（与其他文档的分工）

| 文档 | 角色 | 回答的问题 |
|---|---|---|
| **本文件 FEATURES.md** | 功能说明书 | "有哪些功能、是什么、怎么用、什么状态" |
| [CAPABILITY_MATRIX.md](./CAPABILITY_MATRIX.md) | 能力审计表 | "每个能力完成度多少（Core/CLI/API/Intent/Test）" |
| README.md | 电梯演讲 | "项目是什么、30 秒讲清楚" |
| 完整产品方案书 | 设计蓝图 | "为什么这么设计、未来长什么样" |
| [CLI命令参考文档.md](../CLI命令参考文档.md) | 命令参考 | "每个命令的参数/实测状态" |

> 规则：**新功能落地必须同步本文件**（与 CAPABILITY_MATRIX 同纪律）。

---

## 1. 功能全景（一页看懂）

### 1.1 六大域 × 功能总览

| 域 | 功能 | 入口 | 状态 |
|---|---|---|---|
| **系统域** | 初始化 | `factory init` | ✅ |
| **系统域** | 配置管理 | `factory config show/set/check/path` | ✅ |
| **系统域** | 环境诊断 | `factory doctor` | ✅ |
| **系统域** | 服务生命周期 | `factory start/stop/status` `factory service list` | ✅ |
| **系统域** | 整体/模块更新 | `factory update [--check] [模块]` | ✅ v1.1.43 |
| **系统域** | 版本检查 | `factory --version`（含更新提示） | ✅ v1.1.46 |
| **系统域** | 命令总览 | `factory help`（按域分类） | ✅ v1.1.31 |
| **资源域** | LLM 清单 | `factory llm list` | ✅ v1.1.30 |
| **资源域** | Agent 管理 | `factory agent list` | ✅ 只读 |
| **资源域** | Skill 管理 | `factory skill list` | ✅ 只读 |
| **资源域** | 工具发现 | `factory tools list/doctor` | ✅ |
| **资源域** | 项目管理 | `factory project create/list/rename/status` | ✅ |
| **资源域** | 统一创建入口 | `factory create company/department/project` | ✅ v1.1.17 |
| **数据域** | 主线任务清单 | `factory todo list` | ✅ v1.1.30 |
| **数据域** | 证据包 | `factory evidence list/show` | ✅ |
| **数据域** | 审计查询 | `factory audit` | ✅ |
| **数据域** | 任务清单 | `factory task list` | ✅ 只读 |
| **数据域** | RAG | `factory rag` | 📐 占位 |
| **执行域** | 项目执行 | `factory run` | ✅ |
| **执行域** | 存量仓库模式 | `factory repo` | ✅ M1 |
| **执行域** | 积压清道夫 | `factory workload backlog/status` | ✅ M1b |
| **执行域** | 执行历史 | `factory exec history` | ✅ v1.1.30 域 |
| **执行域** | 结果查询 | `factory run-status` | ✅ |
| **执行域** | 审批门 | `factory approval list/decide/apply` | ✅ M1b |
| **展示域** | 任务监控面板 | `/board` + Web `/api/board` | ✅ v1.1.27 |
| **展示域** | 依赖图/任务链/生命线/汇报 | `/board graph/chain/timeline/report` | ✅ v1.1.32-41 |
| **展示域** | Markdown 预览 | `/preview <文件>` | ✅ v1.1.28 |
| **展示域** | Dashboard | `GET /api/dashboard` | 🚧 聚合未接线 |
| **会话域** | 产品发现（LLM 智能追问） | `factory` → 自然语言 | ✅ v1.1.21-22 |
| **会话域** | 确认门（LLM 理解摘要 + 主动建议） | 会话确认阶段 | ✅ v1.1.23 |
| **会话域** | 自然语言意图理解 | 每轮对话 LLM 介入 + 规则兜底 | ✅ v1.1.20 |
| **会话域** | 组织管理对话 | "建个公司把项目挂财务部" | ✅ v1.1.18 |
| **会话域** | 会话状态/项目切换 | `/status` `/project` | ✅ |
| **会话域** | Markdown 渲染 + 多行输入 | 会话输出 / 行尾 `\` 续行 | ✅ v1.1.28 |

### 1.2 三种使用入口

```
CLI（脚本/运维）:  factory <域> <动词> [参数]        e.g. factory service list
会话（人机交互）:  factory → 自然语言 / /命令         e.g. "做个记账App" / /board
API（Web/集成）:   http://127.0.0.1:8011/api/...      e.g. GET /api/board
```

---

## 2. 系统域（运行与维护）

### 2.1 init — 初始化
- **说明**: 首次运行初始化：环境检测 + workspace 目录 + LLM Provider 引导
- **入口**: `factory init [--non-interactive] [--provider deepseek]`
- **状态**: ✅ · **关联能力**: C01-C03（配置基础）

### 2.2 config — 配置管理
- **说明**: 运行时配置读写：show 查看 / set 修改 / check 校验 / path 路径
- **入口**: `factory config show|set|check|path`
- **状态**: ✅

### 2.3 doctor — 环境诊断
- **说明**: 诊断 环境/Provider/模型/运行时/Router；`--fix` 先修复可自动修复项；`--json` 结构化输出
- **入口**: `factory doctor [checker...] [--fix] [--json] [--verbose]`
- **状态**: ✅

### 2.4 服务生命周期（§2.13）
- **说明**: 内置服务注册/发现/运行/治理；`factory start` 缺省启动 backend+frontend；`factory service list` 显示注册表 + 真实状态 + 访问地址
- **入口**: `factory start [backend|frontend|...]` / `factory stop` / `factory status` / `factory service list`
- **服务清单**:
  | 服务 | 端口 | 说明 | 状态 |
  |---|---|---|---|
  | backend | 8011 | FastAPI 后端（API + board Web） | ✅ |
  | frontend | 5180 | React+TS+Vite SPA（托管 dist） | ✅ |
  | board | 8011 懒加载 | 任务监控面板（backend 内） | ✅ |
  | runtime | 按需 | 执行运行时（无常驻进程） | ✅ 按需调度 |
- **状态**: ✅（服务状态真实化，杜绝假 running）· **起始**: v1.1.28（服务生命周期），v1.1.29（访问地址显示）

### 2.5 update — 整体/模块更新
- **说明**: `factory update` 整体更新（git pull + pip install -e .，带步骤进度条 + 变更 list）；`factory update --check` 只读检查；`factory update <模块>` 指定模块（core/console/exec/org，预留独立版本）
- **入口**: `factory update [模块] [--check]`
- **API**: `GET /api/system/status` · `POST /api/system/update[?module=...]`（v1.1.45）
- **状态**: ✅ · **起始**: v1.1.43（命令）→ v1.1.44（进度条+变更list）→ v1.1.45（API）→ v1.1.46（--version 提示）

### 2.6 help — 命令总览
- **说明**: 按六大域分类展示全部命令（系统/资源/数据/执行/展示/会话）
- **入口**: `factory help`
- **状态**: ✅ · **起始**: v1.1.31

---

## 3. 资源域（资产清单与选择）

### 3.1 llm — LLM 清单
- **说明**: 列出 Provider→Model 两级（provider/models）；命令体系资源域第一落地
- **入口**: `factory llm list`
- **状态**: ✅ · **起始**: v1.1.30 · **关联能力**: C01（Provider 生命周期）/ Router

### 3.2 agent / skill — 员工与技能
- **说明**: 只读列出 7 角色 Agent（id/name/role/skills）与 Skill（id/name/category/version）；写操作走产品管线自动装配
- **入口**: `factory agent list` · `factory skill list`
- **状态**: ✅ 只读 · **关联能力**: C16-C18

### 3.3 tools — 工具发现
- **说明**: 工具发现与注册（增强层 AI CLI + MCP server）
- **入口**: `factory tools list|doctor`
- **状态**: ✅ · **关联能力**: M1 内核

### 3.4 project — 项目
- **说明**: 已有项目接入（create 代理 org CLI / list 只读 / rename / status）
- **入口**: `factory project create|list|rename|status [--json]`
- **状态**: ✅ · **关联能力**: C53

### 3.5 create — 统一创建入口（§1.4.5 便捷铁律）
- **说明**: 一个命令创建 公司/部门/项目，组织树×工作树正交关联（Project.department_ids）
- **入口**: `factory create company|department|project --name <名称>`
- **状态**: ✅ · **起始**: v1.1.17 · **关联能力**: 组织域（org.*）

---

## 4. 数据域（证据与清单）

### 4.1 todo — 主线任务清单
- **说明**: 主线任务（M1-M7 + P0）todolist，与 `/board` 同源（待办清单）
- **入口**: `factory todo list`
- **状态**: ✅ · **起始**: v1.1.30

### 4.2 evidence — 证据包
- **说明**: 可审计变更证据（diff+test+决策链），支持按项目筛选
- **入口**: `factory evidence list|show [--project <slug>]`
- **状态**: ✅ · **起始**: M1a · **关联能力**: C46-C51（审计）

### 4.3 audit — 审计查询
- **说明**: append-only 事件库查询（最近事件 + 按类型计数），52+ 事件类型，hash 防篡改
- **入口**: `factory audit [--limit N]`
- **状态**: ✅ · **关联能力**: C46-C51

### 4.4 task — 任务清单
- **说明**: 只读列出 tasks（id/title/status/project）
- **入口**: `factory task list`
- **状态**: ✅ 只读

### 4.5 rag — RAG 管理骨架
- **说明**: 三级 RAG 规划中，命令占位不实现功能（诚实标注）
- **入口**: `factory rag`
- **状态**: 📐 占位 · **关联能力**: C38-C40（仅测试/未统一）

---

## 5. 执行域（让 Agent 干活）

### 5.1 run — 项目执行（M3 全链）
- **说明**: 复合任务 → 递归原子拆解(M3a) → 关键路径(M3b) → 并行调度(M3c) → 质量评估(M3d) → 动态分配 + 真实执行(M3e) → 证据 → 审计；沙箱副本执行，原仓库零影响
- **入口**: `factory run --project <目录> [--task <id> | --objective <目标>] [--json]`
- **状态**: ✅ · **起始**: v1.1.5（M1）→ v1.1.15（M3e 全链）· **关联能力**: C11-C23

### 5.2 repo — 存量仓库模式
- **说明**: 理解 → 计划 → 改 → 测 → 修（M1 内核；目标可加 --patch 应用）
- **入口**: `factory repo <目标> [--patch <文件>]`
- **状态**: ✅ · **起始**: v1.1.7

### 5.3 workload — 积压清道夫（E3）
- **说明**: 存量代码分诊 → 执行 → 证据包 → 审批 → 报告（首个可售卖工作负载）
- **入口**: `factory workload backlog|status --project <目录>`
- **状态**: ✅ · **起始**: v1.1.7

### 5.4 approval — 审批门
- **说明**: 待审批列表 + 决策（approve/reject + 意见）+ 应用；低/中/高风险分级审批
- **入口**: `factory approval list|decide|apply [--comment]`
- **状态**: ✅ · **起始**: v1.1.6 · **关联能力**: C41-C45

### 5.5 exec / run-status — 执行记录
- **说明**: `factory exec history` 真实执行历史/时间线；`factory run-status` 结果查询
- **入口**: `factory exec history [--limit N]` · `factory run-status [--id <id>] [--json]`
- **状态**: ✅ · **起始**: v1.1.30 域落地

---

## 6. 展示域（看得见）

### 6.1 /board — 任务监控面板（核心）
- **说明**: todolist + 进度条 + 标签；主线（M/P0）vs 周边（长期）分清楚；多源加载：待办清单 + Sprint 验收 + 方案书章节 + 代码证据自动同步
- **入口（会话）**: `/board` `/board graph [项目]` `/board chain [项目]` `/board timeline` `/board report [--save]` `/board done <id>` `/board unmark <id>` `/board sync`
- **入口（Web）**: `GET /api/board`（主面板）`GET /api/board/graph?project=`（依赖图）`GET /api/board/chain?project=`（任务链）`GET /api/board/timeline`（生命线）`GET /api/board?view=report`（汇报）
- **功能明细**:
  | 子功能 | 说明 | 起始版本 |
  |---|---|---|
  | 主线面板 | todolist + 进度条 + 标签（主线 vs 周边） | v1.1.27 |
  | 任务链 + 关键节点 | 关键路径 ★ + 汇聚点 ▲ + 工期 | v1.1.32 |
  | --report 汇报 | 给 Hermes 的 markdown 进度汇报 | v1.1.32 |
  | HTML 可视化 | 进度条/标签/分组卡片响应式 | v1.1.34 |
  | graph/chain HTML | 依赖图/任务链可视化 + 自动刷新 | v1.1.35 |
  | 状态分布图 | 状态分布 + hover/筛选交互 | v1.1.36 |
  | 主线控制 | done/unmark + 汇报落盘 + 状态真实化 | v1.1.37 |
  | 偏离提醒 | 会话启动提示主线未完成（默认关闭, `FACTORY_MAINLINE_ALERT=1` 开启 — 内部开发进度不打扰产品会话） | v1.1.38/v1.1.47 |
  | 自动同步 | 代码证据→主线完成推断（静默维护 /board 数据, 不打印） | v1.1.39/v1.1.47 |
  | 多源加载 | Sprint + 章节 + 待办清单 | v1.1.40 |
  | 图集集成 | 导航 tabs：主线/依赖图/任务链/生命线/汇报 | v1.1.41 |
  | 空态引导 | 无数据时显示真实数据来源 + demo 示例 | v1.1.42 |
  | 单项目管理视图 | `/board project [slug]` 全生命周期 11 段进度（只读, 项目隔离不猜项目） | v1.1.49 |
  | 项目监控聚合 | `/api/board/summary` 项目数/状态分布/生命周期均值/进行中失败任务 + Web 5s 实时刷新 | v1.1.50 |
  | SDK 任务 | §22.3 4 阶段路线第四数据源 + Sprint 判定放宽 (acceptance/completion/final) | v1.1.50 |
- **状态**: ✅（数据真实，空态诚实引导）· **关联**: 待办清单 + docs/sprint10 验收

### 6.2 /preview — Markdown 预览
- **说明**: 渲染显示 markdown 文件（路径解析 cwd→workspace→current_project）
- **入口**: `/preview <文件>`
- **状态**: ✅ · **起始**: v1.1.28

### 6.3 会话 Markdown 渲染 + 多行输入
- **说明**: LLM 回答带 markdown 结构 → rich 渲染可读（启发式判断，纯文本零变化）；行尾 `\` 续行输入长需求
- **入口**: 会话内自动；降级：无 rich → 原样打印不崩
- **状态**: ✅ · **起始**: v1.1.28

### 6.4 Dashboard（API）
- **说明**: `GET /api/dashboard` 实时聚合面板（Collector）
- **入口**: `GET /api/dashboard`
- **状态**: 🚧 端点存在，实时聚合接线待完成 · **关联**: ADR-0012/0017

---

## 7. 会话域（人机交互）

### 7.1 产品发现（两路径 LLM 化）
- **说明**: "我想做个X" / "开始做X" → LLM 智能追问（带"为什么还问"理由）→ 一次产出 problem/user/core_features/name/platform → 理解摘要 → 主动建议（平台/竞品/范围/备注）→ AI 命名；无 LLM 时确定性规则兜底（逐字段，诚实降级）
- **S10-109 修复（v1.1.48）**: 发现阶段回答先做确定性内容归类（user/core_features/problem 模式表）— 答非所问自动填匹配字段、确认词不当字段值提示缺字段（不填）；不依赖 LLM，无 LLM 同样生效；正常回答零变化
- **入口**: `factory` 进入会话 → 自然语言描述
- **状态**: ✅ · **起始**: v1.1.21（DiscoverySession）/ v1.1.22（引导体验）· **关联能力**: C01-C03

### 7.2 确认门（六类智能分流）
- **说明**: 确认阶段理解 "可以，先出prd文档"（确认+下一步）/"改名叫X"（改名）/"？"（澄清不改名）/"没想法"（求助词→建议流）/ 取消 / 委托；LLM 分类 + 确定性规则兜底
- **入口**: 会话确认阶段
- **状态**: ✅ · **起始**: v1.1.23 · **关联能力**: C03

### 7.3 命令分流（slash / exit）
- **说明**: 发现/确认流程中 `/status` 等斜杠命令 → 透传执行（不当字段）；`exit` → 退出会话；"退出" → 取消当前流程（兼容）
- **入口**: 会话任意阶段
- **状态**: ✅ · **起始**: v1.1.24

### 7.4 自然语言意图（LLMIntentParser）
- **说明**: 普通对话也 LLM 理解意图 + 规则兜底（每轮对话 LLM 介入）
- **入口**: 会话内
- **状态**: ✅ · **起始**: v1.1.20

### 7.5 会话命令
| 命令 | 说明 | 状态 |
|---|---|---|
| `/help` | 列出可用命令 | ✅ |
| `/status` | 会话状态（session/workspace/项目/Agent） | ✅ |
| `/project` | 项目列表/切换（`/project <id>`） | ✅ |
| `/cost` | 成本查询 | ✅ |
| `/preview` | Markdown 预览 | ✅ v1.1.28 |
| `/board` | 任务监控面板（见 §6.1） | ✅ v1.1.27 |
| `/exit` | 退出会话 | ✅ |

### 7.6 会话体验增强
- 每轮回复后分割线（v1.1.25）· 进度/生命周期提示（v1.1.22）· 删除/清空字段指令（v1.1.25）· 多轮字段合并边界（v1.1.19）
- 方向键历史/行编辑（v1.1.47, readline 零依赖）+ ANSI 乱码清理兜底

---

## 8. 组织域（公司 OS）

### 8.1 组织数据模型
- **说明**: 六实体 Company/Department/Role/Employee/Authority/Knowledge 全生命周期 + org.* 事件；Project 关联公司/部门（多对多可选，渐进式）
- **入口**: org CLI（`factory create` 代理）· org API
- **状态**: ✅ · **起始**: v1.1.16 · **关联**: §1.4.5 层级流程模型

### 8.2 组织管理对话
- **说明**: "建个公司把项目挂财务部" → LLM 理解 → 调 org CLI；规则兜底
- **入口**: 会话内自然语言
- **状态**: ✅ · **起始**: v1.1.18

### 8.3 组织隔离（设计）
- **说明**: 公司/部门/行业 × 资源可见性隔离规则（§7.2.2⑤）
- **状态**: 📐 规则已入方案书，落地待 P0

---

## 9. API 功能总览（backend :8011）

### 9.1 系统
| 方法 | 路径 | 说明 | 状态 |
|---|---|---|---|
| GET | `/health` `/ready` `/version` | 健康/就绪/版本 | ✅ |
| GET | `/api/system/status` | 系统状态（版本+服务+git） | ✅ v1.1.45 |
| POST | `/api/system/update[?module=]` | 触发更新（git+pip+审计） | ✅ v1.1.45 |

### 9.2 项目与发现
| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/api/projects` | 项目列表/创建 |
| POST | `/api/projects/suggest` | 名称建议 |
| PATCH/DELETE | `/api/projects/{id}` | 更新/删除 |
| POST | `/api/projects/{id}/discovery/answer` | 发现阶段回答 |
| POST | `/api/projects/{id}/discovery/complete` | 完成发现 |
| POST | `/api/projects/{id}/confirm` | 确认门 |
| GET | `/api/projects/{id}/status` `/lifecycle` | 状态/生命周期 |

### 9.3 积压/迭代/里程碑
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/projects/{id}/backlog/epic\|feature\|story\|task` | 分级创建积压项 |
| GET | `/api/projects/{id}/backlog` | 积压清单 |
| GET/PATCH/DELETE | `/api/projects/{id}/backlog/task/{task_id}` | 任务详情/更新/删除 |
| POST/GET | `/api/projects/{id}/sprints` | 创建/列表 Sprint |
| GET/PATCH/DELETE | `/api/projects/{id}/sprints/{sid}` | Sprint 详情/更新/删除 |
| POST | `/api/projects/{id}/sprints/{sid}/plan` | 生成计划（M3 链） |
| POST/GET | `/api/projects/{id}/milestones` | 创建/列表里程碑 |
| GET/PATCH/DELETE | `/api/projects/{id}/milestones/{mid}` | 里程碑详情/更新/删除 |
| GET | `/api/projects/{id}/roadmap` | 路线图 |
| POST | `/api/projects/{id}/roadmap/milestone-ref` | 里程碑引用 |

### 9.4 治理与审计
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/approvals` `/api/approval-gates` | 待审批/审批门 |
| POST | `/api/approvals/{id}/approve\|reject` | 审批决策 |
| GET | `/api/decisions/{id}` `/api/recommendations` | 决策/推荐 |
| GET | `/api/experience` | 经验检索 |
| GET | `/api/events/stream` | 事件流（SSE） |
| GET/POST | `/api/review-feedback` | 评审反馈 |

### 9.5 资源与运行时
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/providers` | Provider 清单 |
| GET | `/api/workflows` `/api/workflows/{id}` `/stages` | 工作流 |
| GET | `/api/artifacts` `/api/artifacts/{id}` `/content` | 产物 |
| POST/GET | `/api/projects/{id}/runtimes` | 运行时注册/列表 |
| POST | `/api/runtimes/{id}/start\|stop\|screenshot` | 运行时控制 |

### 9.6 展示
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/board` `?view=report` | 主面板/汇报 HTML |
| GET | `/api/board/graph?project=` `/chain?project=` `/timeline` | 图/链/生命线 |
| GET | `/api/dashboard` | 实时聚合（🚧） |
| GET | `/api/projects/{id}/timeline` `/workflow` | 项目时间线/工作流 |

---

## 10. 版本对照表（v1.1.5 → v1.1.46）

> 每个版本核心新增（详见 [CHANGELOG](../CHANGELOG.md)）。

| 版本 | 核心功能 | 里程碑 |
|---|---|---|
| v1.1.5 | M1 内核切片：存量仓库模式 + 工具发现 + 真 MCP | M1 |
| v1.1.6 | M1a 证据包 + 分级审批 + M1b 积压清道夫（分诊→修复→证据→审批→报告） | M1a/M1b |
| v1.1.7-8 | 产品方案书 v3.0 终极版合并 + 产品情报管线 + M1 闭环补全（approve 后落地） | M1 |
| v1.1.9-10 | M2 员工内核：7 角色 AgentEntity + HandoffBus + 专家装配 + 真干活 | M2 |
| v1.1.11 | M3a 递归原子拆解引擎 | M3a |
| v1.1.12 | M3b 关键路径标注 + 依赖汇聚 | M3b |
| v1.1.13 | M3c 并行调度（就绪队列+冲突串行+轮次） | M3c |
| v1.1.14 | M3d 拆解质量评估（六维 + 四档行动）+ LLM 深度拆解 | M3d |
| v1.1.15 | M3e 全链真实执行 + 动态分配（模式切换 + 失败降级） | M3e |
| v1.1.16 | 组织树数据模型（Company/Department/Project） | 组织 |
| v1.1.18 | 统一 create 入口（company/department/project） | 组织 |
| v1.1.19 | 组织管理对话接入 | 组织 |
| v1.1.20 | 发现多轮字段合并边界修复 | 发现 |
| v1.1.21 | LLMIntentParser（普通对话 LLM 理解意图） | 会话 |
| v1.1.22 | DiscoverySession 同步 LLM 化 | 发现 |
| v1.1.23 | 产品发现引导体验（进度/生命周期 + 智能追问 + 求助建议） | 发现 |
| v1.1.24 | 确认门六类智能分流 + 求助词全覆盖 | 会话 |
| v1.1.25 | 命令分流（slash 透传 / exit 退出）+ CLI 小修 | CLI |
| v1.1.26 | 确认 next_action 全覆盖 + 会话分割线 + 删除/清空字段 | 会话 |
| v1.1.27 | 任务监控面板 /board（todolist+进度条+标签） | 展示 |
| v1.1.28 | CLI Markdown 渲染 + /preview + 多行输入；服务生命周期管理 | CLI/展示 |
| v1.1.29 | service list 访问地址 + 懒加载诚实显示 | 服务 |
| v1.1.30 | §11.6 命令体系总纲 + factory llm list / todo list | 命令体系 |
| v1.1.31 | factory help 按域分类 | 命令体系 |
| v1.1.32 | board 任务链 + 关键节点 + --report 汇报 | 展示 |
| v1.1.33 | backend 启动 2 bug 修复（__version__ 别名包） | 修复 |
| v1.1.34 | /api/board HTML 可视化面板 | 展示 |
| v1.1.35 | board graph/chain HTML + 自动刷新 | 展示 |
| v1.1.36 | board 状态分布图 + hover/筛选 | 展示 |
| v1.1.37 | 主线控制机制（done/unmark + 汇报落盘 + 状态真实化） | 展示 |
| v1.1.38 | 偏离提醒（会话启动提示主线未完成） | 展示 |
| v1.1.39 | 自动钩子（代码证据同步主线 + 会话启动自动 sync） | 展示 |
| v1.1.40 | board 多源加载（Sprint + 章节 + 待办） | 展示 |
| v1.1.41 | board 图集集成（导航 tabs + 生命线 HTML + 汇报视图） | 展示 |
| v1.1.42 | board 空态引导 + demo 示例 | 展示 |
| v1.1.43 | factory update 整体/模块更新 | 系统 |
| v1.1.44 | update 进度条 + 变更 list | 系统 |
| v1.1.45 | update HTTP API（/api/system/status + /update） | API |
| v1.1.46 | factory --version 更新提示（ahead/behind） | 系统 |
| v1.1.48 | 需求分析字段错位修复（确定性内容归类 user/features/problem + 确认词不当字段值, 正常回答零变化） | 修复 |
| v1.1.47 | CLI 方向键历史/行编辑 + 发现阶段确认短语修复 + PRD 写错项目修复 + 主线提醒默认关闭 | CLI/修复 |
| v1.1.49 | Board 单项目管理视图（全生命周期 11 段, 只读, 项目隔离） | 展示 |

---

## 11. 与 CAPABILITY_MATRIX 双向索引

- **能力矩阵**（[CAPABILITY_MATRIX.md](./CAPABILITY_MATRIX.md)）：58 能力 × Core/CLI/API/Intent/-h/Test 完成度 —— 回答"完成没有"
- **本文件**：功能是什么 + 怎么用 + 从哪版开始 —— 回答"是什么/怎么用"
- 对应关系：§2-§8 的功能条目已标注关联能力 ID（C01-C58）；能力矩阵 22 领域功能树与 §1.1 六大域映射：

| 六大域（本文件） | 能力矩阵领域 |
|---|---|
| 系统域 | 20 CLI / 18 Operations |
| 资源域 | 20 CLI / 21 API |
| 数据域 | 15 Audit / 11-13 Memory |
| 执行域 | 06-10 Agent Team/Execution/Debug |
| 展示域 | 22 User Experience / Dashboard |
| 会话域 | 01-03 Discovery / 22 UX |

---

## 12. 已知缺口（诚实清单）

| 缺口 | 状态 | 见 |
|---|---|---|
| RAG 管理 | 📐 命令占位 | §4.5 |
| Dashboard 实时聚合接线 | 🚧 端点存在未聚合 | §6.4 |
| 前端 SPA 与内核全链路 | 🚧 React 壳待打通 | M5-6 |
| 消息平台渠道 | 📐 设计（P0 5 渠道待做） | 产品 6 |
| 组织隔离落地 | 📐 规则已设计 | §8.3 |
| M3-5/6/7（PRD 深化/变更控制/架构审批门） | 🚧 待办 | 待办清单 |

> 维护规则：功能状态变化（新增/完成/降级）时，同步更新本文件 + CAPABILITY_MATRIX + CHANGELOG 三处。
