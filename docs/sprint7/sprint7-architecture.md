# Sprint 7 — Architecture Design: Organization → Execution Pipeline

> 日期: 2026-08-08 | 状态: 设计 (ONLY DESIGN, 待审核)
> 目标: AI Software Factory 从 "AI Coding Worker" → "AI Software Organization"

## 1. 目标架构

```
User (想法)
  ↓
Project (生命周期容器)
  ↓
Workflow (多阶段编排)
  ├─ ① Idea → PM Agent → PRD (market/persona/requirement/feature tree/MVP)
  ├─ ② PRD → Architect Agent → Design (system/db/API/task breakdown)
  ├─ ③ Design → Developer Agent → Code (exec 引擎: v4-pro/patch/沙箱)
  ├─ ④ Code → Tester Agent → Test (test/bug report/repair task) ↔ Developer Loop
  ├─ ⑤ Code+Test → Release Agent → Artifact (build/package/release note)
  └─ ⑥ Release → Analytics Agent → Metrics (usage/质量/建议)
       ↓
  Artifact (每阶段产物 = 下一阶段输入)
```

## 2. Agent Organization（角色职责定义）

### PM Agent（execution_kind: planning→executable）
```
输入: 用户想法 (一句话)
输出: market analysis / user persona / requirement / feature tree / MVP scope
实现: roles.py PM prompt 模板 + product 链路复用 (idea→analyze→prd)
产物: PRD artifact (JSON/Markdown)
```

### Architect Agent
```
输入: PRD artifact
输出: system design / database design / API design / task breakdown
实现: Architect prompt 模板 + task breakdown (Core tasks parent/deps)
产物: Design artifact + 任务清单
```

### Developer Agent（已 executable ✅）
```
输入: Design artifact + 任务
输出: code patch + report
实现: 现有 exec 引擎 (v4-pro/沙箱/验证/经验)
产物: Code artifact (patch + 变更文件)
```

### Tester Agent（S7-004 P0）
```
输入: Developer Artifact (patch + 项目)
执行: test → failure analysis → bug report → repair task
实现: Tester prompt + 验证循环升级 (复用 validation/unittest) + 缺陷分类
产物: Test artifact (report + bug list + repair tasks)
```

### Release Agent
```
输入: Code + Test 通过
输出: build / package / release note
实现: 沙箱内 build 命令 (python build/pack) + release note 生成
产物: Release artifact
```

### Analytics Agent
```
输入: Release + 运行数据
输出: metrics / 建议
实现: metrics 复用 (Core metrics) + 分析 prompt
产物: Analytics artifact
```

## 3. Workflow Engine 设计（任务级 → 组织级）

### 生命周期

```
Project: 用户想法的容器 (lifecycle: idea→active→maintained→archived)
  └─ Workflow Run: 一次完整开发 (PM→Analytics 全链)
       ├─ Sprint: 任务批次 (workflow 内阶段分组)
       ├─ Task: 原子工作单元 (owner=Employee, 状态机)
       └─ Artifact: 阶段产物 (PRD/Design/Code/Test/Release — 流转输入)

User → Project → Workflow → Role → Task → Artifact
```

### Task 生命周期（已有扩展）
```
created → assigned (Employee) → in_progress → blocked (人工) → done
  └─ 增加: artifact_ref (产出物引用) / depends_on (阶段依赖)
```

### Agent 协作协议
```
① 前一阶段 Artifact 自动成为下一阶段输入 (workflow context)
② 阶段完成 → 事件 (org.workflow.*) → 下一阶段自动触发 (或人工确认闸门)
③ Developer↔Tester Loop: Code artifact → Tester → bug report → repair task
   → Developer 修 → 再测 (≤N 轮, 禁无限)
④ 每阶段产物: 结构化为 Artifact (可审计/可复用)
⑤ 人工闸门: MVP 边界/架构变更/发布 三挡板保持
```

## 4. Tester Agent 优先级（S7-004, P0）

```
输入: Developer Artifact (patch) + 项目快照
执行:
  test (沙箱内运行测试: unittest/pytest)
  → failure analysis (失败分类: 逻辑/边界/接口/缺失)
  → bug report (结构化: 位置/复现/期望/实际)
  → repair task (回传 Developer, 附上下文)
Developer ↔ Tester Loop:
  Dev 产出 → Tester 测 → 失败 → repair task → Dev 修 → Tester 再测
  ≤2 轮 (防无限); 通过 → Release

复用: validation L1-L4 + 验证循环 (AgentRuntime) + bug 分类 (FailureReason)
新增: Tester prompt + bug_report artifact 类型
```

## 5. 架构边界

```
✅ 复用: EmployeeExecutor (统一入口) / roles.py / Context 智能 / 沙箱 / 经验 / 事件
🆕 新增: Workflow 编排层 (组织级) / Artifact 流转 / PM-Arch-Test-Release-Analytics prompt
✅ 保持: Core 冻结 / 沙箱铁律 / 审批闸门 / 仅 DeepSeek (v4-pro)
❌ 不做: UI / 多行业 / Skill-MCP / 自改进 (后续 Sprint)
```

## 6. 风险

```
1. 编排复杂度: 多阶段自动接力 — 阶段间 Artifact 契约需严格定义 (JSON schema)
2. Tester 循环成本: Loop ≤2 轮保成本 (每轮 ~$0.02)
3. 角色质量: PM/Architect 首次 executable — 输出质量待验证 (小步验证)
4. 双角色体系: org 模板 vs exec roles 统一 (S7-001 先行)
```
