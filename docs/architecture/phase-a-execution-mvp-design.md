# Phase A — Execution MVP Design（最小执行边界冻结）

> 状态: IMPLEMENTED (已实现 — 见 ../audit/architecture-reality-audit.md)

> 日期: 2026-08-07 | 状态: 实施准备评审 (Phase A-0)
> 目标: 个人 AI Software Company MVP — 真实 LLM Developer Agent 闭环
> 原则: Core/Runtime 冻结; 零新顶层架构; 复用已有模型

## 1. Phase A 最小范围

### 实现
```
P0-1  真实 LLM Provider Adapter (1 家: Anthropic 优先, OpenAI 备选)
P0-2  Developer Agent 最小执行 (Task→LLM→Patch)
P0-3  Sandbox 最小 (临时副本 + patch 导出)
P0-4  Validation 最小 (语法/简单测试)
P0-5  Human Approval Gate (应用补丁前)
P0-6  Experience 记录 (复用 10A-4, 零新模型)
P0-7  Desktop/CLI 全链 (Goal→Task→执行→审批→汇报)
```

### 不实现（禁止提前）
```
❌ 企业治理完整 (Policy/Risk/Cost — 17A 延后, 只用 Default Deny + Approval)
❌ 完整多 Agent 协作 (单 Developer Agent)
❌ Communication 完整系统 (最小记录)
❌ 自动 Planning (手工/简单规则)
❌ ERP/商业/多租户
```

---

## 2. Execution Interface 冻结

### 数据流

```
Task (描述: objective/input/output) 
  → ExecutionRequest (执行请求: task + context_refs)
  → Developer Agent (Employee→Agent Instance→Provider)
  → Sandbox (副本 + 修改追踪)
  → Artifact (patch + test_result + report)
  → Validation (检查)
  → Human Approval (确认)
  → Apply (合并 patch) 
  → Experience (记录)
```

### 执行权归属

```
拥有执行权: Agent Runtime (执行模块 — 调用 Provider/沙箱/产补丁)
只负责描述: Task/ExecutionRequest (声明意图, 不执行)
只负责检查: Validation/Approval (门禁, 无执行)
只负责记录: Experience (沉淀, 无执行)

铁律: 执行权 != 审核权 (Runtime 执行, Human 批准)
```

---

## 3. Provider Adapter

### LLM Provider Interface（Agent 不知道 Provider 细节）

```python
class ProviderRequest(Pydantic):    # 最小输入
    task_context: str               # 任务 + 上下文
    sandbox_path: str               # 工作副本路径
    max_tokens: int

class ProviderResponse(Pydantic):   # 最小输出
    content: str                    # 模型回复 (代码/说明)
    usage: dict                     # token/成本
    error: str | None

# 接口: generate(request) → response
# Adapter 实现: anthropic.py / openai.py / local.py (8A 已有抽象, Phase A 实现 1 个真实)
```

### 要求

```
Agent 只调 generate(), 不知 Provider 细节 (模型/API/格式)
usage → 成本记录 (8B-3)
error → 失败处理 (重试/降级)
```

---

## 4. Developer Agent MVP

### 第一个 AI Employee: Developer

```
能力: 读取项目 / 理解任务 / 修改代码 / 运行测试 / 生成 Patch
```

### 允许范围
```
✅ 读取项目文件 (沙箱副本内)
✅ 修改代码 (沙箱内)
✅ 运行简单测试 (沙箱内)
✅ 生成 patch (git diff 格式)
✅ 输出执行报告 (做了什么/为什么/结果)
```

### 禁止范围
```
❌ 修改沙箱外任何文件
❌ 访问网络 (沙箱默认禁网, 配置化)
❌ 直接应用补丁 (需 Approval)
❌ 访问 secret/生产数据
❌ 执行危险命令 (rm 系统文件等 — Policy 默认 deny)
```

---

## 5. Sandbox MVP

### 最小方案

```
workspace clone:  项目副本 → 临时目录 (git clone/copy)
change tracking:  git status/diff 追踪修改
patch export:     git diff → patch 文件
```

### 为什么不用直接修改？

```
1. 安全: Agent 错误/恶意行为不伤真实环境
2. 可审计: 修改前后 diff 全记录
3. 可回滚: 不应用 = 无影响; 应用后也可 revert
4. 可批准: Human 看 patch 再决定
5. 可隔离: 多任务并行不冲突
```

---

## 6. Human Approval Gate

### 必须人工批准

```
✅ 应用代码修改 (patch apply)
✅ 删除文件 (patch 含 deletion)
✅ 依赖升级 (lock 文件变更)
✅ 测试失败仍提交 (例外放行)
✅ 任何超出允许范围的动作
```

### 可自动

```
沙箱内测试执行 / 分析 / 报告生成 (不改外部状态)
```

### 规则

```
Approval 后 Apply; 拒绝 → 反馈给 Agent 修复循环 (记录)
高风险动作 = 硬拒绝 + 审计 (Default Deny)
```

---

## 7. Artifact Model

### 最小产物

```
Patch         (代码变更: git diff)
Test Result   (验证结果: pass/fail + 输出)
Execution Report (执行报告: 任务/做了什么/结果/成本/耗时)
```

### 关联

```
Artifact.task_id → Task
Artifact.employee_id → Employee (组织身份)
Artifact.agent_id → Agent Instance (执行身份)
Artifact.event_refs → 执行事件链
```

---

## 8. Learning Integration

### 第一次闭环执行完成后记录

```
成功/失败 (result)
耗时 (duration)
成本 (usage → estimated_cost)
问题原因 (failure_reason: 结构化)
经验摘要 (summary: 供未来推荐)

→ ExperienceRecord (复用 10A-4, 五域/半衰期/正负信号)
→ 未来任务匹配加权 (高绩效 Agent 优先)
```

### 不实现

```
❌ 自动修改系统 (Self Improvement 只留 Proposal 接口)
❌ 自动调优 (只记录, 不自动改)
```

---

## 9. Demo 场景（30 分钟）

```
场景: AI Developer 修复一个真实 Bug

0:00  启动 Desktop → 创建 AI Company (software_company)
0:03  雇佣 Developer Agent (真实 LLM Provider, 公司知识绑定)
0:06  提 Goal: "markpad 表格编辑器存在单元格无法编辑的 bug, 修复它"
0:08  Task 创建 → Agent Runtime 执行
0:12  Sandbox 副本 → LLM 分析/修改代码 → 生成 patch
0:18  自动测试 (简单验证) → Test Result
0:22  生成 Execution Report (修改了什么/为什么/成本)
0:25  Human Review patch → Approval
0:28  Apply → 展示真实代码变更 + Experience 记录
0:30  总结: AI Factory 真实生产闭环
```

---

## 10. Phase A 成功标准

```
不是代码量。是:

一个真实用户是否可以:
  1. 创建 AI Employee (Developer)
  2. 给任务 (Goal → Task)
  3. 获得真实代码交付 (LLM 真实执行 → patch → 应用)

附加验证:
  ✅ 沙箱外零修改 (环境安全)
  ✅ 每步可审计 (Event/Artifact/Report)
  ✅ 经验已记录 (下次推荐加权)
  ✅ 4433+ 测试全绿 | Core/Runtime 零修改
```

---

## 11. 边界冻结声明

```
Phase A 执行边界:
  1 Agent (Developer) | 1 Provider (真实) | 1 Sandbox (最小)
  1 Approval Gate | 1 Learning 闭环
  禁止: 企业治理完整/多 Agent/Communication 完整/自动 Planning

新增 (Extension 内, 零顶层架构):
  factory-exec/ (ExecutionRequest/Sandbox/Patch) — 或并入 factory-org 执行模块
  Provider Adapter 真实实现 (8A 抽象内)
  org.execution.* 事件
```

## 12. 结论

```
Phase A MVP 边界冻结: 真实 LLM Developer Agent 最小闭环
成功 = 用户获得真实代码交付 (非 Mock)
等待确认后进入实现
```
