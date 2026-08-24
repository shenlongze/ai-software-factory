# AI Factory

> **AI Workforce Operating System — 创建、管理、运行和进化 AI 公司的操作系统。**
>
> 让 AI 像软件公司员工一样工作: 理解需求 → 拆解 → 规划 → 受治理执行 → 证据交付 → 经验沉淀。

`v1.1.54` · M3 全链完成 · CLI First · 本地部署 · 全事件审计 · Apache-2.0

---

## AI Factory 是什么

AI Factory 是 **AI 员工操作系统**: 把 AI 从"一问一答的聊天机器人"变成
**有岗位、有职责、有流程、有拆解、有调度、有审批、有审计、有成本账单的员工**。

```
LangChain 创建 AI 员工 · LangGraph 编排 AI 工作流
AI Factory 建立和管理整个 AI 生产组织
```

定位: 不是造单个 Agent, 而是管理 Agent 组织 — "造专家的工厂, 不是某一个专家"。
软件开发只是第一个行业实例（IT 工厂）; 未来: 运维工厂 / 电商工厂 / 自媒体工厂 / 数据分析工厂 / 办公自动化工厂。

## 核心能力（v1.1.46）

| 能力 | 说明 | 状态 |
|---|---|---|
| **多 Provider + Model Catalog** | DeepSeek/OpenAI/Anthropic/Ollama 生命周期 + key 引用安全（不落明文） | ✅ |
| **LLM Router** | 五层决策链: User > Agent/Skill > Project > System > Fallback | ✅ |
| **7 角色专家 + 装配器** | PM/Architect/PRD/UX/QA/Market/Competitive 真 LLM 干活 + 缺 skill 明确报错 | ✅ |
| **递归原子拆解** (M3a) | 复合任务 → 原子叶子（单 Agent/单文件/可验证/≤10min）· 复杂度语义诚实传递 | ✅ |
| **关键路径** (M3b) | 依赖 DAG → CRITICAL 标记 / 总工期 / merge 汇聚点 | ✅ |
| **并行调度** (M3c) | 就绪队列 + 并发上限 + 同文件冲突串行 + 轮次落盘 | ✅ |
| **拆解质量评估** (M3d) | 六维评分（完整性/粒度/依赖/可行/可测/风险）+ 四档行动（adopt/adjust/reject/ask_user）· LLM 门控回退 | ✅ |
| **M3 全链真实执行** (M3e) | 拆解→关键路径→调度→动态分配→真实执行→证据→审计；单任务失败不中断 | ✅ |
| **证据包 + 分级审批** | diff+test+决策链 → 低/中/高风险分级审批（企业敢签字） | ✅ |
| **沙箱执行** | 项目副本沙箱（原仓库零影响）+ patch 白名单 + 证据导出 | ✅ |
| **审计链** | append-only 事件库（52 事件）+ hash 防篡改 + 血缘追溯 | ✅ |
| **组织记忆** | 经验五维标签（域×技术栈×任务类型×项目×通用度）+ 跨项目共享不混淆 | 🚧 M4 |
| **治理** | 预算/熔断/审批门/审计/回滚设计（§5.12 体系） | 🚧 |
| **CLI Control Plane** | 60+ 能力统一入口（六大域命令体系 §11.6）+ `factory help` 按域总览 | ✅ |
| **任务监控面板 board** | todolist + 进度条 + 标签（主线 vs 周边）+ 依赖图/任务链/生命线/汇报；会话 `/board` + Web `/api/board` | ✅ |
| **服务生命周期** | 服务注册/发现/运行（`factory start/stop/status/service list`）+ 懒加载诚实状态 + 访问地址 | ✅ |
| **整体更新** | `factory update [--check] [模块]`（进度条+变更 list）+ HTTP API + `--version` 更新提示 | ✅ |

## 里程碑

```
M1 内核切片 (v1.1.5)      repo 模式 + 工具发现 + 真 MCP
M1a 证据+审批 (v1.1.6)    证据包 + 分级审批
M1b 积压清道夫 (v1.1.6)   分诊→修复→证据→审批→报告
M2 员工内核 (v1.1.10)     7 角色 AgentEntity + HandoffBus + 专家装配 + 真干活
M3 全链 (v1.1.15)         原子拆解 → 关键路径 → 并行调度 → 质量评估 → 真实执行 + 动态分配
```

## 它解决什么问题

| 痛点 | AI Factory 的答案 |
|---|---|
| **不可控** | 原子任务 + 质量门控 + 分级审批 + 证据包（每一步可验证） |
| **一步一个坑** | 拆到原子（§3.7）+ 关键路径 + 调度（8 大失败模式 7/8 有应对） |
| **无审计** | 52 事件 append-only + hash 防篡改 + 血缘（谁/何时/哪个模型/多少钱） |
| **上下文丢失** | 项目级 workspace + 组织记忆（经验标签跨项目共享不混淆） |
| **成本失控** | 预算 + 熔断 + 每任务成本可查 |
| **不敢让 AI 进生产** | 沙箱 + 证据 + 审批 + 回滚（§5.12/5.13 三件套） |

## 架构评测（S-R-U-C-T 五维）

```
当前基线: 安全 S0 · 可靠 L0（12049 测试/0 失败）· 易用 U0 · 完整 C0 · 信赖 T0
升级路线: §22.9-22.10（4 波: M3 收尾 → 证明级 → SDK 化 → 商业化）
发布门:   patch=S0+L0+U0+C0+T0 · minor=S1+L1+U1+C1+T1 · major=认证级
```

## 快速开始

### 1. 安装（2 分钟）

```bash
git clone https://github.com/shenlongze/ai-software-factory.git
cd ai-software-factory
bash scripts/setup.sh        # Python 3.12+ venv + 安装 + 冒烟验证（幂等）
```

### 2. 配置 LLM（1 分钟）

```bash
export DEEPSEEK_API_KEY=sk-xxxx...
factory init --non-interactive --provider deepseek
factory doctor                  # 诊断环境, 全部 PASS 即可开始
```

> Key 只以环境变量引用写入配置（`env:DEEPSEEK_API_KEY`），不落盘不写明文。
> 支持 provider: `deepseek` / `openai` / `anthropic` / `ollama`。

### 3. 体验（5 分钟）

```bash
factory start                  # 启动服务（backend + frontend, 8011/5180）
factory                        # 进入会话: "我想做一个记账 App" → 产品发现
# 或直接: 创建产品 → 开始开发（自动: 拆解 → 调度 → 执行 → 证据 → 审批）
```

## 文档导航

```
README.md                           ← 你在这里（总览）
AI Software Factory — 完整产品方案书.md  ← 22 章完整设计（架构/治理/安全/行业/路线）
CHANGELOG.md                        ← 版本变更（v1.1.46 最新）
docs/MASTER-PLAN-2026-08.md         ← M1-M7 执行主线
docs/FEATURES.md                    ← 功能文档（有哪些功能/怎么用/状态）
```

## 商业定位

开源核心（CLI/Router/Agent/审计）+ 商业增值（治理/合规/分析）· Community 完整可用。
SDK 化与商业化路线见方案书 §22。

## CLI 命令速查（v1.1.46）

```
会话命令（factory 进入后）:
  /board             主线面板（todolist+进度条+标签, 主线vs周边）
  /board graph [项目]  任务依赖图（plan.json, CRITICAL=★）
  /board chain [项目]  任务链（关键路径 ★ 关键节点 ▲ 汇聚点）
  /board timeline     生命线（审计事件时间线）
  /board report      生成给 Hermes 的 markdown 汇报（--save 落盘）
  /preview <文件>     Markdown 预览
  /status /project /cost /help /exit

服务与系统命令:
  factory start               启动全部内置服务（backend+frontend）
  factory start <id>          只启动指定服务（backend/frontend/board...）
  factory service list        服务发现（已注册服务 + 状态 + 访问地址）
  factory update [--check]    整体/模块更新（进度条 + 变更 list）
  factory help                命令总览（按六大域分类）
  factory llm list            LLM 清单 · factory todo list  主线任务
  factory create <type>       统一创建入口（company/department/project）
  factory doctor              环境诊断 · factory --version  版本+更新提示
```

**board 访问**：
```
会话: factory → /board（最简单, 无需启动服务）
Web:  factory start → http://127.0.0.1:8011/api/board（懒加载）
```
