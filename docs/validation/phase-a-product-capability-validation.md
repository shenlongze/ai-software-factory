# Phase A++ — Product Capability Validation

> 日期: 2026-08-07 | 状态: 产品能力验证评审 (不编码)
> 复用: ai-enterprise-os-final-architecture.md / phase-a-execution-mvp-design.md / ai-employee-execution-runtime-model.md / ai-organization-learning-improvement-model.md
> 原则: Core/Runtime 冻结; 禁 mock 数据作为能力证明; 诚实报告阻塞

## 0. 目标

```
证明: AI Employee 不是架构, 而是真正可以工作的生产能力
不扩展架构/不新增企业模块/不进入 ERP
```

---

## 1. AI Developer Employee 能力边界（三个真实场景）

### A. Bug Fix（已部分验证 Phase A+）

```
输入: 真实代码问题 (自然语言描述, 禁人工答案)
流程: Task → Requirement Profile → Employee Matching → Agent Runtime
     → Sandbox → Patch → Validation → Approval → Apply → Experience
验证: AI 完成真实修复 (verifier 正例/反例证明修复有效)
状态: 框架已验证 (markpad 搜索修复), 真实 LLM 质量待 key
```

### B. Feature Development（中小型功能）

```
输入: 新功能需求 (多文件修改)
验证 AI 是否可:
  - 理解需求 (需求 → 实现方案)
  - 修改多个文件 (跨文件 patch)
  - 编写测试 (新增/更新测试)
  - 生成报告 (做了什么/为什么/如何验证)
验收: 功能可运行 + 测试通过 + 报告完整
```

### C. New Project Bootstrap（简单软件）

```
输入: 简单软件需求 ("做一个命令行待办工具")
验证 AI 是否可:
  - 分析需求 (功能/边界)
  - 创建基础项目 (结构: 入口/模块/配置)
  - 生成代码结构 (可运行骨架)
  - 提供交付物 (代码 + 说明 + 运行方式)
验收: 交付物可运行 + 结构合理
```

### 能力边界判定

```
三场景 × 五维评分 (1-5): 理解/定位/修改/测试/报告
全部真实 LLM 执行 (禁 mock), 记录证据
```

---

## 2. 真实 LLM Provider 验证方案

### 设计（可替换, Agent 无感知）

```
ProviderInterface (已有) + ProviderRegistry (已有)
支持: anthropic (已有 Adapter) + openai (新增 Adapter, 同接口)

Provider 配置: 项目/员工级 (runtime_preferences) — Agent 不感知具体 Provider
```

### 记录指标（每次真实调用）

```
model / token usage (in+out) / cost (estimated) / latency / success rate
→ ExecutionRecord + ExperienceRecord (已有 8B-3/10A-4)
```

### 铁律

```
禁止: mock 数据作为能力证明
无 key → 真实调用 BLOCKED (响亮错误, 不静默; 诚实报告)
验证条件: 用户提供 ANTHROPIC_API_KEY 或 OPENAI_API_KEY
```

### 真实验证矩阵（待 key 解锁）

```
场景 × Provider × 3 次执行 → 成功率/成本/延迟统计
可替换性: 同一任务跑 Anthropic + OpenAI → 对比 (Agent 零改动)
```

---

## 3. Human User Experience Review

### 模拟用户: Founder / CEO（普通开发者/创始人）

```
流程: 创建 AI 公司 → 创建 Developer Employee → 提交任务
     → 查看执行过程 → 审批结果 → 获得代码交付
```

### 分析维度

```
1. 用户是否理解? (每步有明确反馈? 术语是否友好?)
2. 步骤是否最少? (5 步内从想法到交付?)
3. 困惑点: 审批时机/成本显示/失败原因
4. 优化点: 一键提交/进度可视化/结果对比 (before/after)
```

### 体验验收

```
普通开发者 10 分钟内: 创建员工 → 提任务 → 拿到真实代码 (无文档/无培训)
```

---

## 4. Demo Design（30 分钟产品 Demo）

```
主题: Human CEO + AI Employee 完成真实软件开发任务
不展示: 复杂架构 (事件流/扩展模型/治理)
重点: 结果 (真实代码交付)

时间轴:
 0:00  开场: "AI Software Company — 你 + 你的 AI 员工团队"
 0:03  创建 AI Company (software_company) — 1 步
 0:05  雇佣 Developer Employee (真实 LLM Provider) — 1 步
 0:08  提交真实任务: "修复 markpad 搜索 bug" (自然语言)
 0:15  AI 执行: 沙箱内分析/修改/测试 → Patch + Report (屏幕展示过程)
 0:22  Human 审阅 patch → Approve
 0:25  Apply → 真实代码变更展示 (before/after diff)
 0:28  成本/耗时展示 (model/token/cost) + Experience 已记录
 0:30  收尾: "明天它会更了解你的项目"

演示成功 = 观众看到真实代码变化 (非 mock/非预录)
```

---

## 5. 商业价值验证

### 用户是谁

```
个人开发者/独立创始人 (Solo) → 专业开发者 (Team) → 小团队 → 企业
```

### 为什么购买（价值主张）

```
替代: 雇佣初级开发者成本 / 外包沟通成本 / 等待时间
提供: 24/7 AI 员工 (按需/可扩展/经验积累)
```

### 替代成本对照

```
初级开发者: 年薪 ~¥20-40 万 (管理/招聘/离职成本更高)
AI Developer Employee: 订阅 (每月) + token 成本 (按用)
价值锚点: 1 个 AI 员工 = 初级开发者的产能 (任务级), 成本 1/10
```

### 收费模式（设计, 不实现）

```
Personal:  单用户, 1-2 员工, 订阅低
Professional: 开发者, 多员工 + 真实 LLM, 订阅 + token
Team:      多人协作, 治理/审计, 订阅高
Enterprise: 多租户/合规/私有部署, 定制
```

---

## 6. 当前技术缺口（只列真实阻塞）

```
1. Provider 接入: ⛔ 无 API key — 真实调用未验证 (最大阻塞)
2. Agent 质量: 真实 LLM 下 patch 质量/多文件修改未验证 (待 key)
3. Context 管理: 大项目上下文组装 (当前最小, 无检索) — 小项目够用, 大项目阻塞
4. Tool 能力: 仅 filesystem; 无 git 远程/测试框架集成 — MVP 够用
5. Sandbox 限制: 单副本单任务; 多任务并行未做 — MVP 够用
6. UI 体验: CLI 为主; Desktop 未接执行链 (Phase B)
```

```
不扩展: 不为完整性加功能 (只列影响真实使用的阻塞)
```

---

## 7. 下一阶段建议

### 判定: 先强化 Developer Employee, 后 Phase B

```
理由 (数据驱动):
  1. 最大阻塞 = 真实 Provider 验证 (key) — 未验证就扩展 = 放大风险
  2. Developer 能力是产品核心 (用户唯一关心的: 代码质量)
  3. Phase B (Planning/Communication/多员工) 依赖已验证的单一员工质量

建议顺序:
  1. 用户提供 API key → 三场景真实验证 (A/B/C) + 双 Provider 对比
  2. 按验证结果强化 Developer (Context 检索/多文件/测试集成 — 只补阻塞项)
  3. 能力达标后 → Phase B (Planning MVP + Communication MVP + 多员工)
```

### 明确不做

```
❌ 扩展架构 | ❌ 新增企业模块 | ❌ ERP/CRM/行业模板
❌ 为完整性加功能 | ❌ mock 当能力证明
```

---

## 8. 结论

```
Phase A++ 验证设计完成:
  三场景能力边界 + 真实 Provider 方案 (双 Adapter) + 用户体验 + 30min Demo
  + 商业价值 + 真实缺口 (key 是最大阻塞) + Phase B 判定 (先强化后扩展)
执行条件: 用户提供 API key → 真实验证 → 数据驱动下一步
```
