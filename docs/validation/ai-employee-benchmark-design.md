# AI Employee Benchmark — Design（真实生产能力验证标准）

> 日期: 2026-08-07 | 状态: 验证设计评审 (Phase A+++, 不编码)
> 复用: ai-enterprise-os-final-architecture.md / phase-a-execution-mvp-design.md / ai-employee-execution-runtime-model.md / phase-a-product-capability-validation.md
> 原则: Core/Runtime 冻结; 禁 mock 证明; 诚实区分已验证/待验证

## 0. 目标

```
建立 AI Developer Employee 商业能力验证标准:
  架构能力 (已验证) vs 真实生产能力 (待真实 LLM)
  用可复现 Benchmark 证明: AI Employee 是否可替代部分真实软件开发工作
```

---

## 1. Benchmark 目标

### 区分架构能力 vs 真实生产能力

```
已验证 (架构/链路, Phase A+/A):
  ✅ 执行链路 (Task→Sandbox→Patch→Approval→Apply)
  ✅ 安全 (沙箱隔离/审批门禁/审计)
  ✅ 验证框架 (verifier 正/反例有效)

待验证 (真实 LLM 能力, Phase A+++):
  ⛔ Bug 定位准确率 / 修改正确率 / 测试通过率
  ⛔ 多文件修改 / 需求理解 / 架构分析
  ⛔ 成本/延迟/成功率 (真实 Provider)
```

**Benchmark 只测"真实生产价值", 不测架构。**

---

## 2. 三类真实任务 Benchmark

### Benchmark 1: Bug Fix

```
输入: 真实开源项目 Bug (自然语言描述, 禁人工答案)
流程: Task → Requirement Profile → Employee Matching → Agent Runtime
     → Sandbox → Patch → Validation → Approval → Apply
评价指标:
  - Bug 定位准确率 (修复点是否命中根因)
  - 修改正确率 (修复是否有效 — verifier 正/反例)
  - 测试通过率 (回归 + 新增测试)
  - 修改范围 (最小化: 只改必要文件)
  - 回滚风险 (patch 可逆性/影响面)
样本: 5 个真实 Bug (不同难度), 每 Bug 3 次执行
```

### Benchmark 2: Feature Development

```
输入: 真实新增功能 (中等复杂度, 如 markpad 表格增强)
评价指标:
  - 需求理解 (实现是否符合需求语义)
  - 架构分析 (方案是否合理/扩展性)
  - 多文件修改 (跨文件一致性)
  - 测试覆盖 (新增测试是否验证功能)
  - 交付质量 (代码规范/可读/可运行)
样本: 2 个真实功能, 每功能 3 次执行
```

### Benchmark 3: Greenfield Project

```
输入: 产品需求 ("命令行待办工具")
输出: 项目结构 + 核心代码 + 测试 + 文档
评价指标:
  - 可运行性 (交付物能跑)
  - 完整性 (结构/功能/测试/文档齐)
  - 人工修改量 (用户需改多少才能用)
样本: 1 个项目, 3 次执行
```

---

## 3. Provider Benchmark（可替换性证明）

```
同一任务 (三场景各 1 个):
  Provider A: Anthropic (已有 Adapter)
  Provider B: OpenAI (同接口新增 Adapter)
Agent/Employee/Execution 流程零修改 (Provider 无感知)

比较:
  Success Rate / Token Usage / Cost / Latency / Patch Quality

证明: 模型变化不影响组织 (Employee 稳定, 只换 Provider)
```

---

## 4. AI Employee 五维能力评分

```
① Understanding  需求理解能力
② Analysis       问题分析能力
③ Implementation 代码实现能力
④ Validation     测试验证能力
⑤ Communication  结果汇报能力

Level 定义:
  Level 1 辅助    (人主导, AI 协助)
  Level 2 独立完成简单任务 (常见任务无人工干预)
  Level 3 生产级执行 (复杂任务可靠交付)

评分: 每 Benchmark × 每维度 → Level + 证据
达标: 三场景全部 Level 2+ (独立完成), 核心场景 Level 3
```

---

## 5. Human CEO Experience

```
模拟 Founder/CEO:
  创建 AI Company → 创建 Developer Employee → 提交任务
  → 查看执行过程 → 审批 → 获得结果

评估:
  - 是否容易理解 (无术语门槛/每步有反馈)
  - 是否信任 AI (patch 可审/过程可见/成本透明)
  - 是否愿意持续使用 (重复任务价值)

量化: 完成全链时长 / 困惑点计数 / 信任评分 (1-5)
```

---

## 6. 商业价值映射

```
Benchmark 达成 → 用户为什么购买:

个人开发者:  省时间 (Bug 修复/功能开发外包给 AI 员工) → 订阅低
专业开发者:  提产能 (并行多任务/AI 干杂活) → 订阅 + token
小团队:      扩能力 (AI 补岗位缺口, 无招聘成本) → 团队订阅
企业:        降成本 (替代部分外包/初级开发) + 合规审计 → 定制

价值锚点: 初级开发者成本 1/10, 24/7, 经验积累 (越用越懂项目)
```

---

## 7. Demo 标准（30 分钟商业 Demo）

```
禁止: Mock / 预录结果 / 静态截图
必须 (全部真实):
  真实任务 (现场提需求)
  真实 LLM (真实 Provider 调用)
  真实执行 (沙箱内修改)
  真实 Patch (可审阅 diff)
  真实审批 (Human approve)
  真实代码变化 (before/after 展示)

成功 = 观众看到: 需求 → 真实代码 (全程无预演)
```

---

## 8. 风险分析（只列真实风险, 不无限扩展）

```
1. LLM 能力不足: 真实 patch 质量/多文件修改可能不达标 → 最大风险
2. 大项目 Context 限制: 当前最小上下文, 大项目理解不足 → 限制场景
3. 成本: 真实调用成本不可控 (Benchmark 量化后定预算)
4. 稳定性: Provider 网络/限流/延迟波动
5. 用户信任: 首印象 (坏 patch 毁信任) → Demo 必须真实可控

缓解: Benchmark 先小后大 / 每场景有预算 / 失败路径透明
```

---

## 9. Phase B 进入条件（客观标准）

```
仅当全部满足:

1. Benchmark 达标: 三场景全部 Level 2+, 核心场景 (Bug Fix) Level 3
2. Developer Employee 可用: 真实 Provider 成功率 ≥ 80% (5 样本)
3. 用户流程可理解: Founder 全链 ≤ 15 分钟, 困惑点 ≤ 2
4. 成本可接受: 单任务成本 < 替代人力成本 1/10

满足 → Phase B:
  Planning MVP / Communication MVP / Multi Employee Collaboration
不满足 → 继续强化 Developer (只补阻塞项)
```

---

## 10. 执行前置

```
⛔ BLOCKED: 无 API key (ANTHROPIC_API_KEY / OPENAI_API_KEY)
解锁条件: 用户提供 key → 执行 3 Benchmark + Provider 对比 → 输出评分报告
```

## 11. 边界

```
✅ 零编码 | ✅ Core/Runtime 冻结 | ✅ 无新模型
✅ 禁 mock 证明 | ✅ 复用 4 设计文档
```

## 12. 结论

```
AI Employee Benchmark 设计完成:
  3 Benchmark × 5 维 × 3 Provider 对比 = 商业能力验证标准
  客观 Phase B 门禁 (达标→进入, 不达标→强化)
执行等待 API key
```
