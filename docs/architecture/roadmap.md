# AI Software Factory — Architecture Roadmap

> 日期: 2026-08-07 | 状态: v3.0 (Architecture Re-alignment, 终极目标融入)
> 前置: Phase 1-14B + 15A-1 (25371e4, 4217 tests, v1.0.0-rc1)

## 架构层（重新定义）

```
Human Console      Developer Console → CEO/Manager/Operation/Approval/Audit 多中心
Intelligence       Decision + Recommendation + Experience + Planning + Agent
Organization       Company/Department/Role/Employee(Agent)/Authority  (新增)
Extension          行业模板 (Software/Finance/Manufacturing/Commerce/Healthcare/Media)
Core               通用组织运行基础 (Organization/Project/Task/Workflow/Event/Artifact/State)
```

## Phase Roadmap（重新规划）

### Phase 15 — Product Runtime Foundation ✅ (15A-1 完成, 进行中)
```
目标: Factory 成为真正可安装的软件
Desktop Runtime ✅ / Installer / Update / Local Runtime
(15A-1 core 完成 → 15A-2 CLI/watchdog → 15A-3 Tauri Desktop → 15A-4 Installer)
验收: 下载→安装→启动→Console→Demo (无源码)
```

### Phase 16 — AI Organization Foundation
```
目标: Factory 拥有专业 AI 员工
Organization Model: Company/Department/Role/Agent
Agent Registry + Capability Model + Experience Model
验收: 组织建模 + AI 员工注册/分配 (≥120 tests)
```

### Phase 17 — AI Professional Organization MVP
```
目标: 创建第一个完整 AI 团队 (MarkPad AI Software Company)
组织: Company/Department/Role + Employee (Agent Profile/Capability/Authority)
Workflow: Goal → CEO → Product → Project Manager (拆解/规划/分配)
         → Architect → Developer → QA → Review → Experience
原则: 能力 != 角色; Agent 角色化 (Identity/Responsibility/Capability/
      Knowledge/Authority/Experience/Performance); 禁超级 Agent
验收: MarkPad 公司组织实例化 + 全岗位协作链 (≥130 tests)
```

### Phase 18 — Execution & Sandbox
```
目标: 真正执行
Task → Assigned Agent → Sandbox → Artifact → Review Agent → Validation → Human Approval → Merge
原则: 执行权 != 审核权
验收: 沙箱执行 + 全链审计 (≥150 tests)
```

### Phase 19 — Governance
```
目标: 企业级治理
Identity/Permission/Policy/Secret Management/Audit/Compliance
验收: 默认 deny + 高危必经人 + 只追加审计 (≥120 tests)
```

### Phase 20 — Industry Organization Templates
```
目标: 行业组织模板
Software/E-commerce/Finance/Manufacturing/Media 公司模板
每模板: Organization + Workflow + Role + Agent + Policy
验收: 模板实例化 + 校验 (≥100 tests)
```

### Phase 21+ — Enterprise / Global AI Group
```
目标: AI 跨国集团操作系统
Global HQ / Region / Country / Company / Department
验收: 多级组织 + 跨公司协作 (设计先行, 商业模式确认)
```

## 关键转变（vs 旧 Roadmap）

```
旧: Provider 生态 → 执行 → 安全 → 协作 → 模板 → 商业
新: 组织为纲 — Agent 是员工, Factory 是公司操作系统
16 Organization 前置 (Agent 注册/分配) → 17 Planning (项目经理)
→ 18 执行 (员工干活) → 19 治理 (HR/合规) → 20 行业公司 → 21 集团
```

## 不变铁律

```
1. Core 冻结 (Organization 也是 Extension/新层, 不碰既有 Core 原语)
2. 不绑定 LLM/Agent
3. 不替代 Human (授权/批准/负责)
4. 一切行为可见 (Event + Audit)
5. 执行安全 (可暂停/可恢复/可审计)
```
