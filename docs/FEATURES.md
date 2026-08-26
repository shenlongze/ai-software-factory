# AI Factory 功能文档（FEATURES）

> **单一事实来源** — 当前系统到底有哪些功能、每个功能是什么、怎么用（CLI / API / 会话命令）、什么状态、从哪个版本开始有。
>
> 版本: **v1.1.185** · 更新: 2026-08-27 · 依据: 实测命令 + 代码核对 + CHANGELOG

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
| **资源域** | 项目管理 | `factory project create/list/rename/status/reconcile` | ✅ |
| **资源域** | 统一创建入口 | `factory create company/department/project` | ✅ v1.1.17 |
| **数据域** | 主线任务清单 | `factory todo list` | ✅ v1.1.30 |
| **数据域** | 证据包 | `factory evidence list/show` | ✅ |
| **数据域** | 审计查询 | `factory audit` | ✅ |
| **数据域** | 任务清单 | `factory task list` | ✅ 只读 |
| **数据域** | RAG | `factory rag query/index/sources` | ✅ v1.1.96 |
| **执行域** | 项目执行 | `factory run` | ✅ |
| **执行域** | 存量仓库模式 | `factory repo` | ✅ M1 |
| **执行域** | 积压清道夫 | `factory workload backlog/status` | ✅ M1b |
| **执行域** | 执行历史 | `factory exec history` | ✅ v1.1.30 域 |
| **执行域** | 结果查询 | `factory run-status` | ✅ |
| **执行域** | 审批门 | `factory approval list/decide/apply` | ✅ M1b |
| **执行域** | 执行质量分 | `execute_task` 落盘 quality + `/board quality` | ✅ v1.1.86 |
| **执行域** | PRD/工程计划质量评估 | `prepare_project` 落盘 PRD.quality.json / engineering.quality.json | ✅ v1.1.86 |
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

### 1.3 工程保障（防遗漏机制）

> 新增命令/意图/action/事件/API 必须同步注册表, 否则一致性测试红 (S10-112 P0-10);
> 改一个对称实现 (conversation/discovery、CLI/API), 另一个必须同步验证 (S10-112 P0-11)。

| 机制 | 说明 | 状态 |
|---|---|---|
| P0-10 注册表一致性测试套件 | CLI 命令/意图/action/事件/API 5 类注册表从实现动态读取, 断言两两一致 | ✅ v1.1.81 |
| P0-11 对称路径一致性测试 | conversation/discovery 同输入同推进; CLI/API 双入口同数据源同结构 | ✅ v1.1.81 |

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

### 3.4 mcp — MCP 管理 (S10-116 A-3)
- **说明**: MCP 外部工具连接管理 — list 连接/Tool 清单 · connect 创建连接
  (MockMCPClient 诚实标注, transport=mock 不连公网) · remove 移除连接;
  objective 含工具关键词 → 路由选 MCP tool (B-3)
- **入口**: `factory mcp list|connect --name <名> --url <地址>|remove --id <id>`
- **状态**: ✅ · **起始**: v1.1.85 · **关联能力**: M1 内核 / B-3

### 3.4 project — 项目
- **说明**: 已有项目接入（create 代理 org CLI / list 只读 / rename / status /
  reconcile — J-1 生命周期状态单一来源对账）
- **入口**: `factory project create|list|rename|status|reconcile [--json] [--dry-run]`
- **状态**: ✅ · **关联能力**: C53 · reconcile **起始**: v1.1.83
  （对账: canonical=project.json.status; 快照先行 `.status_snapshot_<ts>.json`;
  --dry-run 只读预览; 无法判定项目如实跳过）

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

### 4.5 rag — 项目级 RAG（K-6, v1.1.96 转正）
- **说明**: 项目文档入库 (KnowledgeStore, 复用 board 文档扫描, 索引独立 .factory_rag) +
  三级分档 (raw/summary/knowledge) + 确定性词频检索 (纯规则零依赖, reason 可解释) +
  增量重建 (mtime) + 外挂适配器接口 (M5-3) + E-5 RAG_QUERY 审计溯源
- **入口**: `factory rag query <项目> <问题> [--tiers raw,summary,knowledge] [--top-k N]` ·
  `factory rag index <项目> [--incremental]` · `factory rag sources`
- **状态**: ✅ · **起始**: v1.1.96 · **诚实标注**: 真实 embedding/LLM 未接入 (接口就绪);
  doc/docx 二进制文档暂不索引 (跳过记录) · **关联能力**: C38-C40 · **设计**: docs/sprint10/S10-123-k6-rag-plan.md

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

### 5.7 执行质量分 + 优选（K-2, v1.1.86）
- **说明**: 每次执行产出确定性质量分 (纯规则不调 LLM, 复用 T5.3 五层思路:
  validation 硬条件 + patch/scope/risk/coverage; 失败 → 总分封顶 0.35) —
  落盘 execution_records.json quality 字段 (score/dimensions/evaluator_version/
  scored_at/rules, 可审计); 多候选执行 (T5.3) 评估明细透出 (ranking/selected/
  score_breakdown/rejection_reason); 低分 (score<0.5) 且重试耗尽 → 经能力路由换
  资源再试一次 (resource_switched), 无替代 → 诚实报告 "低分无替代资源"
- **PRD/工程计划质量评估 (B-6)**: score_prd + score_engineering (复用 M3d 六维
  思路, 确定性) — prepare_project 落盘 PRD.quality.json + engineering.quality.json
- **入口**: `/board quality [项目]`（只读, 渲染后 mtime 不变）·
  `execute_task` 审计记录自动带 quality 字段
- **状态**: ✅ · **起始**: v1.1.86


### 5.6 replay — 执行重放（M5-1, v1.1.82）
- **说明**: 执行重放引擎 — dry-run 按时间线重建单次执行 (execution_records +
  audit 事件合并, 步骤/agent/结果/耗时 = 相邻时间戳差) / re-exec 同输入重跑
  (input_snapshot 还原 → 新 exec_id 记录) / compare 两次执行真实 diff
  (步骤/结果/耗时/产物, --save 落盘 docs/sprint10/replay-compare-<id1>-<id2>.md) /
  L4 快照回滚 (项目目录 git 快照, 受限: 需 git 仓库项目目录)
- **入口**: `/board replay <exec_id>`（默认 dry-run）· `--re-exec` ·
  `--compare <exec2_id>`（缺省对比最近一次）· `--save`；自然语言 "重跑 <exec_id>"
- **数据**: 新执行记录含 input_snapshot (intent/action/params/context) — 可重放;
  旧记录无快照 → re-exec 明确报错不瞎跑
- **状态**: ✅ · **起始**: v1.1.82

---

## 6. 展示域（看得见）

### 5.8 K-3 学习闭环（v1.1.89）
- **说明**: 让 Agent 变强且可控 — 执行完自动经验入库 → 下次同类任务引用 (带 reason); 全部学习路径挂护栏 (开关/样本可信度/预算上限/一键回滚); 审批决策落组织记忆; 成本超预算告警/阻断; 画像优先分配 + 负载均衡; L4 非 git 快照; 低分任务评估驱动修复闭环
- **入口**: 执行自动 (execute_task) · `/board cost [项目]` · `/cost` · 学习经验 (`memory_learn`) · 分析Agent (`memory_analyze_agent`) · 搜索经验 (`memory_search`)
- **功能明细**:
  | 子功能 | 说明 | 起始版本 |
  |---|---|---|
  | 经验闭环 (M4-1/B-7/E-1) | `memory/learning_loop.py`: on_execution_complete 自动入库 + resolve_for_task 同类引用 (reason 可解释, 注入执行 prompt) | v1.1.89 |
  | 学习护栏 (M4-2) | `memory/learning_guards.py`: 总开关/样本可信度(n>=3 主导)/低质量不写/预算上限/快照回滚 | v1.1.89 |
  | 决策记忆 (M4-3/E5) | `memory/decision_memory.py`: 审批→DECISION_LEARNED→decision_memory.json→下次同类审批带历史 (N 次/批准率) | v1.1.89 |
  | 成本告警 (M4-4/D-6) | usage→聚合→BudgetEnforcer→超预算 BUDGET_WARNING/BUDGET_BLOCKED 审计 + 执行前阻断 + 回填 task/agent | v1.1.89 |
  | 画像分配 (M4-5) | capability_router 排序: priority → persona (agent_profiles) → load → quality → version → id | v1.1.89 |
  | L4 快照 (M4-6) | execution_replay 非 git 目录级快照/还原 (git 路径沿用) | v1.1.89 |
  | E-2/E-3 评估闭环 | `session/eval_loop.py`: 低分→分类→建议→应用(repair_task)→复评提升断言 | v1.1.89 |
- **状态**: ✅ · **关联**: docs/sprint10/S10-119 设计文档 · 待办清单 K-3/M4-1~6

### 5.9 K-4 trace_id 贯穿（v1.1.90）
- **说明**: 一次请求从入口到执行全程同一 trace_id — 审计/执行/成本可追踪; audit_trace 决策链 (S10-069) 真正可用
- **入口**: 会话每输入自动 · API 每请求自动 (请求头 `X-Trace-ID` 可覆盖, 响应回带) · CLI 命令自动 · exec 执行自动 · 审计追踪/审计决策链 (`审计追踪 <trace_id>` / `审计决策链 <trace_id>`)
- **功能明细**:
  | 子功能 | 说明 | 起始版本 |
  |---|---|---|
  | trace 上下文 | `audit/trace_context.py`: ContextVar (线程安全, with 自动恢复不跨请求泄漏) — new_trace_id (uuid4 hex) / get_trace_id / get_correlation_id (失败安全 "") / trace_context / child_correlation (父子关联 trace:n) | v1.1.90 |
  | emit 自动填充 | AuditEmitter.emit: trace_id/correlation_id 未显式传 → 读 contextvar (64 发射点零改动, 显式优先不覆盖) | v1.1.90 |
  | 入口生成 | session._dispatch 每用户输入 · FastAPI 每请求中间件 · cli_factory 命令入口 · agent_runtime 执行入口 (有上下文继承不分裂) | v1.1.90 |
  | 执行/成本链路 | execution_records += trace_id · CostLedger.record 缺省 trace_id 读 contextvar | v1.1.90 |
  | audit_trace 激活 | 审计事件 trace_id 已填充 → 审计追踪/决策链按 trace 查全链路 (S10-069 action) | v1.1.90 |
  | F-9 最小面 | 关键调试日志带 trace_id (审计发射/会话分发/执行入口 — 不铺开) | v1.1.90 |
- **状态**: ✅ · **关联**: docs/sprint10/S10-120-k4-trace-plan.md · 待办清单 K-4/I-1/F-9

### 6.0 factory eval — 评测体系（K-5）
- **说明**: 7 维评测 + L0-L3 等级 + 发布门 — "可靠"可评测可证明有等级
- **入口（CLI）**: `factory eval [--gate patch|minor|major] [--check] [--save] [--workspace <根>]`（只读跑评测不写业务）
- **功能明细**:
  | 子功能 | 说明 | 起始版本 |
  |---|---|---|
  | 七维评测 | 正确性/鲁棒性/一致性/性能/安全/长期/用户价值 — 每维 ≥1 可断言项 (复用 H-1/K-2/K-3/K-4 数据), 通过/失败/未覆盖 + 证据引用 | v1.1.95 |
  | 发布门 | --gate patch=L0 · minor=L0+L1; 失败 → rc 1 明确阻断 [E4102]; --check 只读不阻断 | v1.1.95 |
  | H-1 端到端 | 创建→发现→PRD→工程→审批→执行→证据→交付 每节点衔接断言 + J-1 状态投影 | v1.1.95 |
  | F-10 覆盖度 | scripts/coverage_report.py (stdlib trace 模块级报告, 不设达标线) | v1.1.95 |
  | M5-7 错误码 | docs/error-codes.md 集中表 (模块:CODE: 消息: 建议下一步) | v1.1.95 |
  | C-4 盲区 | docs/eval-blind-spots.md (K-2 已覆盖 vs 仍盲, 如实) | v1.1.95 |
- **状态**: ✅ · **关联**: docs/sprint10/S10-121-k5-eval-plan.md · 待办清单 K-5/P0-1/4/5/C-1/4/5/6/H-1/F-10/M5-7

### 6.0a K-6 项目级 RAG（v1.1.96）
- **说明**: 项目文档知识可检索可复用 — README/docs/PRD/工程/质量/经验 入库 (片段+元数据索引,
  独立 .factory_rag 零污染) + 三级分档 (raw 原始片段 / summary 章节摘要·目录 / knowledge
  跨文档知识条目) + 确定性词频检索 (纯规则零依赖, reason 可解释) + 增量重建 (mtime) +
  外挂适配器接口 (M5-3) + E-5 检索溯源
- **入口（CLI）**: `factory rag query <项目> <问题> [--tiers raw,summary,knowledge] [--top-k N]` ·
  `factory rag index <项目> [--incremental]` · `factory rag sources`
- **入口（Web API）**: `POST /api/rag/query` · `GET /api/rag/sources`
- **功能明细**:
  | 子功能 | 说明 | 起始版本 |
  |---|---|---|
  | KnowledgeStore 入库 | `retrieval/knowledge_store.py`: 复用 board read_docs_config 扫描 → 片段+元数据索引 (workspace/.factory_rag/<slug>/index.json, 零污染); 失败安全 (坏文件跳过) | v1.1.96 |
  | 三级分档 | raw (文档片段) / summary (章节摘要·目录) / knowledge (跨文档知识条目: json 键值 + 经验类文档) | v1.1.96 |
  | 确定性检索 | 词频/TF 打分 (ASCII 词 + CJK 二元子词, 纯规则零依赖, 同输入同输出); embedding/LLM 仅可选 (scorer 注入点, 诚实标注) | v1.1.96 |
  | 增量重建 | mtime/size 变更文件只重扫; 删除文件块移除; 索引缺失退化全量 | v1.1.96 |
  | 外挂适配器 | `retrieval/external_source.py`: ExternalKnowledgeSource Protocol + Mock + 注册表 + providers.external_rag (未配置 → 空不崩) | v1.1.96 |
  | E-5 检索回路 | RAG_QUERY 审计事件带 trace_id (K-4 contextvar 自动填充, 检索动作可溯源) | v1.1.96 |
- **状态**: ✅ · **诚实标注**: 真实 embedding/LLM 未接入 (接口就绪); doc/docx 二进制文档暂不索引 (跳过记录) · **关联**: docs/sprint10/S10-123-k6-rag-plan.md · 待办清单 K-6/M5-2/M5-3/B-8/F-11/E-5

### 6.1 /board — 任务监控面板（核心）
- **说明**: todolist + 进度条 + 标签；主线（M/P0）vs 周边（长期）分清楚；多源加载：待办清单 + Sprint 验收 + 方案书章节 + 代码证据自动同步
- **入口（会话）**: `/board` `/board graph [项目]` `/board chain [项目]` `/board timeline` `/board report [--save]` `/board done <id>` `/board unmark <id>` `/board sync` `/board replay <exec_id> [--re-exec|--compare <id2>|--save]`
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
  | 任务树视图 | `/api/board/tasks?project=` epic→feature→task 层级 + 任务状态汇总 + 全页统一返回导航 | v1.1.51 |
  | 项目选择器 | 全页导航 select 切换项目 + 单项目/任务树 15s 自动刷新 + 会话当前项目标记（准确/实时/同步） | v1.1.52 |
  | 刷新间隔可选 | 全页导航 select: 5s/15s/30s/60s/关闭 (?refresh=N, 0=关闭) | v1.1.53 |
  | 项目优先架构 | 默认首页=当前项目视图 + 大项目选择器置顶 (第一步) + AI 主线面板降级为显式 ?view=mainline | v1.1.54 |
  | 生命线可读化 | 事件中文标签 + 对象名解析 + 需求确认折叠 ×N + 同秒聚合 | v1.1.55 |
  | 无项目引导 | 未选项目时面板 tab 指向项目列表; 示例项目(仅 plan.json)显示'暂无任务'不误报 | v1.1.56 |
  | 选择器/URL 一致 | URL 项目未注册时选择器显式选中并标注(示例/未注册), 不再误选首个项目 | v1.1.57 |
  | 生命线/汇报项目化 | timeline?project= 项目事件过滤; view=report&project= 项目汇报; 导航跟随所选项目 | v1.1.58 |
  | 全页面可选项目 | AI 主线面板/汇报页也带项目选择器 (缺省选中会话当前项目), 7 个 tab 全部可切项目 | v1.1.59 |
  | 文档管理 | 📚 文档 tab: 9 类文档资产清单/查看 (md 渲染/JSON, 白名单防穿越) | v1.1.60 |
  | 任务逻辑 | 任务树不堆: 依赖标记 + 关键路径★ + 项目任务时间线 (audit 事件) | v1.1.60 |
  | 默认项目 | /board default <slug> + 列表⭐设为默认 + 首页优先打开 (默认>当前>列表) | v1.1.61 |
  | 任务链格式 | 名称清洗(去**) + 完整显示 + 状态色 (done绿/failed红/running蓝) + P0 自然序 | v1.1.62 |
  | 递归任务树 | L1-L4+ 层级 + 展开折叠 + 细化按钮 (/board task split, L 层+1) | v1.1.63 |
  | 模块分隔 | L1 模块卡片(标题栏+边框+间距) + 组标题(待办清单解析, 如'M2 员工内核') | v1.1.64 |
  | 数据来源标注 | 各视图显示数据来源(meta source/note), 区分执行记录 vs 待办清单解析; 剔除臆造估时/依赖 | v1.1.65 |
  | 文档扫描 | 文档管理扫描 README/docs 等真实文件, 分组展示, 路径组件级安全校验 | v1.1.66 |
  | 文档文件夹 | 文档按目录结构分组展示 (📁 根目录/docs/specs 区块) | v1.1.67 |
  | 完整目录树 | 文档管理显示项目全部文件按目录分组 (根目录含核心资产+README, docs/specs 各区块) | v1.1.68 |
  | 全类型文档 | 显示全部文件类型 (png/yaml/py 等), 非文本标记—, 文本可预览 | v1.1.69 |
  | 文档指向实际目录 | product.json workspace_dir/repo_url; 文档管理扫真实仓库文档 (排除源码/垃圾), 显示目录+git | v1.1.70 |
  | 文件树+搜索 | 文档目录树(展开折叠) + 搜索框即时过滤 + 隐藏文件(.开头)不显示 | v1.1.71 |
  | 文档树设计 | 目录默认折叠+紧凑行+类型筛选(文档/数据/配置/文本), 搜索筛选联动 | v1.1.72 |
  | 文档配置 | 多文档目录+可配扩展名(默认 md/json/doc/docx)+设置页/CLI 管理 | v1.1.73 |
  | 配置保存修复 | 保存按钮 JS 转义修复 + 保存后自动刷新 + 🔄刷新/↻重置按钮 | v1.1.74 |
  | 树去重排序 | 修复渲染重复(dkids) + 排除 demo/examples + 目录上文件下 A-Z | v1.1.75 |
  | 项目删除 | 删除项目(自然语言+/project delete)+确认门审批+PROJECT_DELETED审计 | v1.1.76 |
  | AI 执行记录 | 单项目视图显示执行记录(execution_records 按项目过滤) | v1.1.76 |
  | 清单多维度 | /project 列升级: 生命周期/任务进度/最近更新 (替代管线/状态) | v1.1.77 |
  | Agent/Skill 管理 | factory agent/skill list|add|remove + /api/agents + /api/skills + help 补全 | v1.1.78 |
  | 员工管理计划 | 待办清单 A-1~A-4 (补skill/管理面板/MCP/流程) 进 board 周边; 解析支持任意章节 | v1.1.79 |
  | Skill 资产补齐 | A-1: 11 个 skill 补齐, 7 角色装配全成功 (不再缺 skill 兜底) | v1.1.80 |
  | Skill 真调用 | 外部注册 skill 装配生效 + 执行注入 prompt (不再只是标签) | v1.1.82 |
  | 执行质量视图 | `/board quality [项目]` 最近执行质量分 + PRD/工程计划质量 (K-2, 只读) | v1.1.88 |
  | 成本可视化 | `/board cost [项目]` 每项目/每任务/每 Agent 实际成本 + 预算等级 (K-3 M4-4/D-6, 只读) | v1.1.89 |
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
| `/cost` | 成本查询 (CostLedger 只读聚合 + 预算等级, K-3 M4-4) | ✅ v1.1.89 |
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

### 9.7 检索与知识（RAG, v1.1.96）
| 方法 | 路径 | 说明 | 状态 |
|---|---|---|---|
| POST | `/api/rag/query` | 项目级 RAG 检索问答 (确定性片段+引用源+reason; E-5 审计带 trace_id) | ✅ v1.1.96 |
| GET | `/api/rag/sources` | 外部知识源清单 (M5-3 接口就绪; 未配置 → 空不崩) | ✅ v1.1.96 |

---

## 10. 版本对照表（v1.1.5 → v1.1.46）

> 每个版本核心新增（详见 [CHANGELOG](../CHANGELOG.md)）。

| 版本 | 核心功能 | 里程碑 |
|---|---|---|
| v1.1.185 | T-8 执行链续跑 + T-9 执行溯源 (exec_ref→记录→证据包; 任务详情) | WebUI/后端 |
| v1.1.184 | T-4 任务↔会话双向追溯 (任务详情附关联会话; 会话列表 task_id 过滤+task_title) | WebUI/后端 |
| v1.1.183 | T-5 端到端实测 (会话A建任务→B继续→完成→C审计); 意图优先级修复 | 后端/测试 |
| v1.1.182 | 任务树默认显示已完成任务 + 「隐藏已完成」开关 (纯前端) | WebUI |
| v1.1.181 | 主任务子任务未全完成不归档 (legacy 层级保留, 树内聚合) | WebUI/后端 |
| v1.1.180 | 任务树父行 N/M 完成计数 (含归档, 百分比可对账) | WebUI |
| v1.1.179 | 任务链进度按同一任务链逐行 (S/T/U/V/X 系列, 非P0) | WebUI |
| v1.1.178 | 项目头任务链进度 (按系列非P0) | WebUI |
| v1.1.177 | 项目头布局: P0 摘要独占一行 | WebUI |
| v1.1.176 | 项目头 P0 进度摘要 + 排序切换 (更新时间⇄优先级) | WebUI |
| v1.1.175 | 任务树多维筛选: 状态+优先级+更新时间 | WebUI |
| v1.1.174 | 任务时间显示 + 按更新时间排序 (最后更新最前) | WebUI |
| v1.1.173 | T-3 跨会话恢复: 新会话继续→找到上次会话接进展 | 平台 |
| v1.1.172 | T-2 任务上下文注入: 锚定后每条消息带状态/历史/下一步 | 平台 |
| v1.1.171 | T-1 会话任务连续: 定位任务+锚定 (跨会话继续) | 平台 |
| v1.1.170 | U-5 三端工具页统一: CLI/WebUI/会话 同源发现/调用 | WebUI/平台 |
| v1.1.169 | U-2 统一工具执行链: Registry→Permission→Schema→Execute | 平台 |
| v1.1.168 | U-1 统一工具注册表: 39 内置工具全量注册 (CLI/API) | 平台 |
| v1.1.167 | X-1 数据保护: factory backup + factory git (备份/恢复/推送) | 平台 |
| v1.1.166 | 会话工具调用: 分析自动调 扫描/任务/仓库/代码/文档 (可溯源) | 平台 |
| v1.1.165 | 会话能力自我认知: persona 列出真实执行能力 | 平台 |
| v1.1.164 | 会话按优先级查任务 (P0 任务清单) | 平台 |
| v1.1.163 | S 会话×软件打通: 任务操作/建想法/产出物/监控/设置/项目操作 | 平台 |
| v1.1.162 | 会话仓库能力: 查 git remote + 真实推送 | 平台 |
| v1.1.161 | 项目扫描器 (多源聚合+判断/风险/建议) + 会话任务统计修复 | 平台 |
| v1.1.160 | 会话项目状态: 真实任务统计+进度+史诗摘要 | 平台 |
| v1.1.159 | 任务页头部 sticky 固定 (工具栏+项目头) | WebUI |
| v1.1.158 | 布局: 分隔条拖拽调宽 (侧栏/会话栏, 中间自适应) | WebUI |
| v1.1.157 | 想法→待办链路: 会话"细化/拆解"触发建任务 (绑定模块) | 平台/WebUI |
| v1.1.156 | 修复: 收藏项目关注区不显示 (收藏必显示 + last_activity 兜底) | 平台/WebUI |
| v1.1.155 | 任务树: 折叠摘要钻取真实任务名 (legacy 同名结构) | WebUI |
| v1.1.154 | 任务树: 折叠摘要 (子节点名 + 等N个) | WebUI |
| v1.1.153 | 任务树: 进度百分比去重 | WebUI |
| v1.1.152 | 任务树: 优先级徽标(聚合) + 每行进度条(折叠可见) | WebUI |
| v1.1.151 | 任务树史诗层按名称排序 (有章法) | 平台 |
| v1.1.150 | 修复深色主题 --c-* 语义色未定义 (主题统一管理) | WebUI |
| v1.1.149 | 文档目录默认全部收起 (点开展开) | WebUI |
| v1.1.148 | 文档页分组: 只显示真文档 + 关键目录优先 + 杂项折叠 | WebUI |
| v1.1.147 | Markdown 渲染: 表格/引用/链接 (会话+文档页) | WebUI |
| v1.1.146 | 会话文档查看/检索: 读指定文档内容 + RAG 检索全部文档 | 平台 |
| v1.1.145 | 会话文档查询: docs/products 完成状态 (子目录+状态行解析) | 平台 |
| v1.1.144 | 想法→细化→待办链路 (想法模块/会话锚定/任务绑定/成熟度) | 平台/WebUI |
| v1.1.143 | 任务排序: 主树按优先级(依赖感知) + 归档按完成时间 | WebUI |
| v1.1.142 | W-3: Todo 编辑/优先级/归档/审计溯源 (WebUI 敏捷管理) | WebUI |
| v1.1.141 | 方案A: 执行绑定+回写 (任务状态自动更新) | 平台 |
| v1.1.140 | 计划/债务全量导入 backlog (seed 工具, 幂等) | WebUI/平台 |
| v1.1.139 | 任务树填充: legacy 并入 backlog (四层树, 不再空) | WebUI/平台 |
| v1.1.138 | 运维页快照分页 + 版本说明 | WebUI/平台 |
| v1.1.137 | 会话答 webUI 状态: 直接下结论, 不再'未查询到' | 平台/WebUI |
| v1.1.136 | 监控告警 (端口/失败/质量) + 运维页趋势条 | 平台/WebUI |
| v1.1.135 | 运维页 + 概览健康条统一读 Monitor | WebUI/平台 |
| v1.1.134 | 统一监控运维 Monitor (系统+项目采集+快照+API+CLI) | 平台 |
| v1.1.133 | 系统状态含真实前端/后端端口探测 | 平台/WebUI |
| v1.1.132 | 会话意图修复: 确定性关键词优先, LLM 不覆写意图 | 平台/WebUI |
| v1.1.131 | 会话答系统/WebUI运行状态 (执行会话自建任务 TASK-774d9036) | 平台/WebUI |
| v1.1.130 | 会话作用域自动跟随视图 (去掉手动公司/项目选择) | WebUI |
| v1.1.129 | 会话栏紧凑化 (归档折叠/hover操作/列表收紧) | WebUI |
| v1.1.128 | CLI/WebUI 任务同源 (task list 并入 backlog) | 平台 |
| v1.1.127 | P2b: 任务→执行链桥 (factory task prompt|run 走 exec CLI) | 平台 |
| v1.1.126 | 会话发起开发任务 P2a: 会话建任务进任务系统 | 平台/WebUI |
| v1.1.125 | 会话创建修复: 创建意图确定性优先 (不被LLM覆写) | 平台/WebUI |
| v1.1.124 | 会话操作软件 P1: 会话创建项目 (真实执行 + 跳转) | 平台/WebUI |
| v1.1.123 | 会话跳转: 查看后直达对应功能页 (meta.target + 跳转按钮) | WebUI/平台 |
| v1.1.122 | 去掉子页顶部重复项目详情块 (子页直渲内容) | WebUI |
| v1.1.121 | 概览 Todo 摘要化 (未完成前5+查看全部), 完整任务归任务页 | WebUI |
| v1.1.120 | 概览 Todo 实时化 (默认15s轮询) + 聚焦未完成/完成折叠 | WebUI |
| v1.1.119 | 会话完整链路: LLM 转意图 → 本地查真实数据 → 标准输出 | WebUI/平台 |
| v1.1.118 | 会话栏实事求是: 事实卡带阶段, 禁止编造分类/结论 | WebUI |
| v1.1.117 | 会话栏真实数据注入: AI 直接答项目列表/重点/模型 | WebUI |
| v1.1.116 | 会话栏: AI 回复接上下文 (Web 感知) + Markdown 渲染 | WebUI |
| v1.1.115 | 概览重构: 健康信号条 (运行/质量/失败→跳转) + 移除底部运维块 | WebUI |
| v1.1.114 | 项目导航 6 项路由落地 + C-2 白名单/注册表同步 | 平台/WebUI |
| v1.1.113 | 修复浅色主题强对比 (硬编码深色变量化, 全覆盖) | WebUI |
| v1.1.112 | 主题 (深色/浅色) + 自定义背景图 (透明化/模糊) | WebUI |
| v1.1.111 | 系统级中英文切换 (i18n 基础设施 + 主界面双语 + 语言选择器) | WebUI |
| v1.1.110 | C-3: 产出物实时查看 (版本轮询+历史链) + 轻量版本端点 | 平台/WebUI |
| v1.1.109 | 产出物契约 C-1 (平台级): 统一 schema + set_artifact + 版本信号 + artifacts 校验 | 平台 |
| v1.1.108 | 项目文档管理 (左树右看: PRD/工程/任务拆分 + 目录扫描) | 产品/WebUI |
| v1.1.107 | 页面适配窗口: 固定 100vh + 内部滚动 (页面/会话栏不再超长) | 产品/WebUI |
| v1.1.106 | 去掉侧栏重复 ◆ 品牌标记 | 产品/WebUI |
| v1.1.105 | 预览默认收起+不记忆状态 (中间默认显示页面) | 产品/WebUI |
| v1.1.104 | AI 员工/技能人话标签 (角色中文+职责+分组, 普通人可读) | 产品/WebUI |
| v1.1.103 | 设置表格化 + LLM 新增/编辑 (POST/PATCH /api/config/llm) | 产品/WebUI |
| v1.1.102 | 设置页全管理面: LLM 配置 + Agent/Skill/MCP 注册移除 | 产品/WebUI |
| v1.1.101 | 工作区导航方案 A: 7 项 → 我的公司/项目/设置 (占位页移 board) | 产品/WebUI |
| v1.1.100 | 修复: 目录项目收藏 404 (惰性注册 org, 单一事实源) | 产品/WebUI |
| v1.1.99 | 布局 v4 三栏 A|B|C: AI 会话栏 (多会话/真实对话) + 预览入 B + 状态栏 | 产品/WebUI |
| v1.1.98 | WebUI 工作台主页面: 我的公司首页 (关注项目+待办聚合/过滤, 信息量小) | 产品/WebUI |
| v1.1.97 | 项目收藏/关注 + 左栏收藏/最近3/全部 + K-7b 累积 (OS树/预览/首页/对话分域/刷新) | 产品/WebUI |
| v1.1.96 | K-6 项目级 RAG (S10-123): KnowledgeStore 三级分档 + 确定性词频检索 + factory rag 问答 + 外挂适配器接口 + E-5 RAG_QUERY 溯源 | K-6 战役 |
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
| v1.1.78 | M3 收尾三件套: ux/qa 真引擎+PRD 深度化 / ChangeControl 变更回流 / 架构审批门 · Agent/Skill 管理 | M3 (7/7) |
| v1.1.81 | P0-10 注册表一致性 + P0-11 对称路径一致性（防遗漏机制） | 测试/工程保障 |
| v1.1.94 | /help CLI 区逐命令树 + 组内对齐 (v1.1.93 补) | 易用/CLI |
| v1.1.93 | /help 树形分层 (自然语言/系统/CLI 三区 tree) | 易用/CLI |
| v1.1.92 | /help CLI 组标签对齐 (v1.1.91 补) | 易用/CLI |
| v1.1.91 | /help 完整化 (命令全/分组/对齐 CJK) | 易用/CLI |
| v1.1.90 | K-4 trace_id 贯穿 (S10-120): contextvar 入口生成 + emit 自动填充 + audit_trace 可用 + 执行/成本链路 | K-4 战役 |
| v1.1.89 | K-3 学习闭环 (S10-119): M4-1 经验闭环 + M4-2 学习护栏 + M4-3 决策记忆 + M4-4 成本告警 + M4-5 画像分配 + M4-6 L4 快照 + E-2/E-3 评估闭环 | K-3 战役 |
| v1.1.88 | Web board 质量视图接线 (view=quality + 📊 导航) — K-2 补 | 监控/质量 |
| v1.1.87 | 发现对话上下文保持 (逃生挂起) + 委托/求助口语全覆盖 + LLM 失败响亮报错 (网络/超时/限流/5xx) | 会话/可信度 |
| v1.1.86 | K-2 执行质量分+优选: C-2 质量分落盘 + C-3 多候选启用 + B-5 低分换资源 + B-6 PRD/工程评分 | K-2 战役 |
| v1.1.85 | K-1 能力路由+员工管理: B-1~B-4 统一路由层 + A-2 员工 tab + A-3 mcp 管理 + F-4 提示词版本化 | K-1 战役 |
| v1.1.84 | 战役规划 K 系列（A~J+主线合并统一路线, board 可见） | 规划/防遗漏 |
| v1.1.83 | J-1 生命周期状态单一来源: set_project_lifecycle 统一写入口 + 防回退 + 存量对账 (factory project reconcile) · Board 三轨只读对账漂移可见 | 生命周期/可信度 |
| v1.1.82 | M5-1 执行重放引擎 (dry-run/re-exec/对比报告 + input_snapshot) · Skill 真调用 | 执行/工程保障 |

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
| M3-5/6/7（PRD 深化/变更控制/架构审批门） | ✅ v1.1.78 | 待办清单 · S10-111 |

> 维护规则：功能状态变化（新增/完成/降级）时，同步更新本文件 + CAPABILITY_MATRIX + CHANGELOG 三处。
