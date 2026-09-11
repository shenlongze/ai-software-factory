# AI Factory — Product Professor Review & Development Plan

> 日期: 2026-09-04 | 审查人: Product Professor (Hermes)
> 范围: ai-software-factory @ /Users/Shared/work/ai-software-factory (HEAD 1e993dec, v1.1.364)
> 性质: T4/T5 (只读审查 + 提案), 不修改任何 Canonical Truth / 不碰代码 / 未执行 git 操作
> 依据: AGENTS.md 必读链 → README → docs/00-index/* → STEP10_DOMAIN_FREEZE →
>       PROJECT_PROGRESS_SNAPSHOT → capability-maturity → fix-sprint-design

---

## 0. 审查方法与限制 (声明, 不猜测)

- 本次只读仓库文档层 (权威 = 代码 + 运行时 + STEP10 Contract; 本次未启动服务、
  未读取 ~/.factory 运行时数据 — 环境上下文不允许)。所有"当前"陈述来自
  docs/00-index/CURRENT_SYSTEM_TRUTH.md 与 STEP10 Contract (2026-09-02, HEAD 一致)。
- WebUI/前端观感未做浏览器实测 (8011/5180 无监听进程), UI 评分标注 UNVERIFIED, 不猜。
- 2026-08-27 以前计划的完成状态一律标"待代码验证", 不默认已完成/未完成。
- 本目录全部文件 = 审查证据 + 提案, 不形成平行 Truth; 实施须经人工批准。

---

## 1. 当前情况快照 (2026-09-02 冻结事实)

| 维度 | 状态 |
|---|---|
| 身份 | AI Software Factory v1.1.364 — 已拥有真实生产执行内核 (M4) 的 AI 软件开发平台 |
| 方向 | AI Software Factory → AI Organization Factory → AI Enterprise OS |
| 运行时 | factory-console (Web 8011/会话/编排) + factory-org (领域 SSOT) + factory-exec (执行域) |
| 独立模块 | factory-core / factory-runtime (无生产证据, INV-015) |
| 成熟度 (STEP7 历史评估) | Reality 85.2 / Fulfillment 75.0 / Closure 49.8 |
| 能力分布 (29 Atomic) | M4×11 / M3×7 / M2×3 / M1×4 / M0×4 |
| 主链 (E2E PROVEN) | Session → Plan → Task+依赖 → ExecState 门控 → Run → 回写 → recover → reconcile → Audit |
| 真实执行 | execution_records 100+ (backend-1×48/flutter-dev×17…), audit 5160 events |
| 架构冻结 | STEP10 Contract D-1~D-10, 15 Invariants, 12 Domain, 唯一 SSOT (人工批准 2026-09-02) |
| 文档治理 | 00-index Canonical 导航; 历史 docs 1050+ = 证据非真相 (治理基线已提交) |

## 2. 分数卡 (2026-09-04)

| 分数 | 值 | 依据 / 为什么不是更高 |
|---|---|---|
| Overall Product Professor | **62 / 100** | 架构治理纪律罕见地好 (STEP1-11 forensic 诚实、SSOT 冻结、零代码人工批准), 但产品闭环只完成"计划→执行→审计"中段; 前端 idea 链与后端学习/发布链均未闭合; 交付物对种子用户价值未验证。不是更高: Closure 49.8、PRD 实体 ABSENT、Model Selection 0 消费。 |
| Launch Readiness | **45 / 100** | 可安装可运行 (setup/doctor/start, 8148 tests 历史), 但: v0.1.0 release notes 状态=待发布; 服务当前未运行; 无公开分发/种子用户/社区证据 (战略重心=增长, 尚无行动证据); auth/RBAC/守护/发布门状态未知或缺失。 |
| True Score (真实产品 vs demo) | **70 / 100** | 执行内核真实 (100+ 外部执行记录 + 5160 audit + E2E 测试 + 崩溃恢复), 不是 demo; 历史自夸已由 STEP1-11 全面纠偏。不是更高: 产品智能层 (Requirement 无下游/PRD 缺失/分析不落盘) 与产物验证层 (Artifact/Verify 未挂会话链) 仍是"半真"。 |
| AI-Generated Feel Badness | **5 / 10** | 扣分: 1050+ 历史文档堆积、884KB 巨型产品方案书、内部命名过密 (console/org/exec/core/runtime 五模块+三套 task 真相历史)、大量早期"宣称式"文档需靠治理基线压住。加分: 治理后诚实度高, README/真相导航清晰。UI 观感 UNVERIFIED 不计入。 |
| Expected User Complaint Severity | **6 / 10** | 新用户"我要做一个 X"路径: 会话→计划→执行真实可用, 但模型固定默认、无 PRD/需求归档感、产物/验证不回到会话链、无学习成长; 外部 Agent CLI (claude/codex) + DeepSeek key 装配门槛高; 多人组织故事 (RBAC/认证) 未落地。 |

## 3. Idea → Product 完整性判定 (本次核心问题)

**结论: 纵向执行闭环 (M4) 完整; 横向产品闭环 (Idea→Plan→…→Release→Learn) 不完整。**

```
[完整, M4]  Plan → Task → Run → Record → Audit
[断裂/缺失] User Intent → Requirement(无下游,M2) → PRD(ABSENT,M3 承诺) → …
[缺失/未接] Artifact/Verify (exec 域真实, 会话链无关联) → Learning(M0) → Release(M0)
[治理已冻] 12 Domain SSOT / 15 Invariants / Execution Truth Contract (D-9)
```

- "从 idea 到产品" 纵向只在 **计划→执行→审计** 段闭环且 E2E PROVEN。
- 前链 (idea→可执行计划): Requirement 捕获 M2 但零下游 (G-REQ-01);
  产品分析不落盘 (FX-07); PRD 独立实体缺失 (D-5/INV-011, M3 承诺);
  → **计划质量来自对话, 不来自结构化产品承诺**。
- 后链 (产物→验收→成长→发布): Artifact M2 / Verification M2 且不挂 Run→Task (D-6 未实施);
  Verification SSOT 未定 (FX-08, D 类); Learning M0 (experience 84 写 0 读);
  Release M0; v0.1.0 待发布。
- 因此 Closure 49.8 不是统计误差, 是真实的"产物/验证/发布未闭合"。
- **完整性缺口排序 (P0→P2)**: 见 02-FINDINGS-ISSUES.md F-01~F-06 (产品闭环),
  F-08~F-09 (可运行/多人), F-13 (分发/增长)。

## 4. 用户 POV / 预期投诉

1. "我提了个需求, 它给我做了任务拆解, 但我的需求原文和产品决策去哪了?" → 需求链 trace ❌
2. "PRD 呢? 说好的 M3?" → 实体 ABSENT
3. "为什么总是同一个模型? 说好的智能路由?" → LLMRouter 消费 0
4. "代码改完的产物/测试结果我看不到完整链路" → Artifact/Verify 未挂会话链
5. "服务挂了谁拉起? 多个人用怎么分权限?" → 守护/auth/RBAC 未知或缺失
6. "东西这么好, 我在哪能下载/试用/看案例?" → 无发布/无分发证据 (创始人自己也知道: 风险=没人知道)

## 5. 后续文档

- 01-DEVELOPMENT-PLAN.md — 分阶段开发计划 (之前未完成 / 将来 / 优化)
- 02-FINDINGS-ISSUES.md — 可行动问题清单 (P0/P1/P2, 证据+建议动作)
