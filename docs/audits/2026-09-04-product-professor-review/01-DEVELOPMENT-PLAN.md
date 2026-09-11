# AI Factory — 开发计划 (2026-09-04)

> 来源: Product Professor 审查 2026-09-04 (00-REVIEW-OVERVIEW.md)
> 状态: 提案 (T5), 待 shenlongze 批准后进入实施; 遵循"先审计→计划→人工批准→实施"纪律
> 与既有文档关系: 不取代 backlog/STEP10/fix-sprint-design; 是"从 idea 到产品"的路线整合视图
> 说明: 条目标注 [D]=设计已有(在 fix-sprint-design) / [N]=新计划项 / [V]=需先验证现状

---

## 0. 规划原则

1. **先消不诚实, 再谈功能**: 所有"宣称未兑现"(Requirement/PRD/Model/Router/Artifact/Verify) 优先
2. **Contract 先行**: 任何改动遵守 STEP10 15 Invariants + SSOT 唯一性, 不产生平行 Truth
3. **每 Sprint 独立验收**: 证据矩阵 (11_ACCEPTANCE_EVIDENCE_MATRIX.md 模式), 用户实测才算 CLOSED
4. **Fix 不自动 commit / 不自动 push**: 分阶段独立 commit, 等用户指令
5. **并行安全**: 并发会话共享 git 工作区, 先 stash 隔离再操作; 启动任务前 source 密钥 env
6. **产物 = 真实闭环**: 代码存在 ≠ 完成; 占位 UI / mock 不可接受

---

## 1. 之前没完成的 (承接 STEP11 Fix Sprint — 设计已齐, 等批准实施)

> 依据: docs/audit/fix-sprint-design/ (13 份, 未提交 untracked), AGENTS.md §6, STEP10 Contract
> 状态: "具备进入 Fix Sprint 条件: YES", 阻断项: 无, 只等人工批准

### S-FX0 — FX-08 Verification SSOT 取证 (D 类, 无代码)
- [D] 审计 exec results 与 ExecState.verify 的真实写路径, 冻结 Verification SSOT 归属 (Run/Record)
- 验收: 取证报告 + Contract 更新, 零代码

### S-FX1 — Execution Truth 落地 (地基)
- [D] FX-02: execution_plan 冻结写入 (只读/标记 historical), orchestrator/actions M3 路径改造
- [D] FX-01: exec T00x 记录引用 backlog TASK-* ID (exec store 写路径), 消除平行 Truth
- 验收: 无新 T00x 平行; 记录可回溯 TASK-*; 全量关键测试 ≈1049 绿

### S-FX2 — 需求链上游 (可与 S-FX1 并行)
- [D] FX-03: requirements.json → session_plans 携带 requirement_id 引用 (只读引用)
- [D] FX-07: 产品分析结果持久化落盘 (product_intelligence action, 可审计回看)
- 验收: 需求→计划可追踪; 分析报告落盘 + audit event

### S-FX3 — 产物/Agent 闭环 (依赖 S-FX1)
- [D] FX-04: Run/Record 挂 Artifact/Verify, Task 经 Run 可达 (会话链 Run 记录 + exec results)
- [D] FX-06: 角色 Agent 生产触发入口验证/建立 (gateway router + exec)
- 验收: Task→Run→Artifact 审计链可见; 角色 Agent 调用链有证据

### S-FX4 — Model 控制面 (依赖 S-FX1 + S-FX3)
- [D] FX-05: Task/Agent → Model Policy → Model Selection 进治理链 (llm_fn 装配点 + LLMRouter)
- 验收: 模型选择有 policy + audit; 不再固定默认模型; 无绕过治理链改 provider 路径

---

## 2. 将来要完成的 (产品自标 M3/M4, 非缺陷 — 排期在 Fix 之后)

> 依据: CURRENT_SYSTEM_TRUTH §12/§13, STEP10 §14, capability tree, docs/products/*.md

### M3 — 产品智能链 (idea 段闭环)
- [N] **PRD 实体落地** (STEP10 D-5/INV-011): Requirement → Product-PRD → Plan 的结构化产品承诺
  - Domain SSOT 新建 (PRD domain), 遵守 SSOT-01, 挂 Req 引用
- [N] Requirement → Product 演进引用语义 (D-4, INV-010): 需求保留、变更回流
- [N] Replan + 变更回流 (orchestrator replanner 会话链集成, C-028 M0→M3)
- 验收: idea→PRD→Plan 全链有稳定 ID 可审计; 变更后计划可重规划且不丢历史

### M4 — 学习/发布闭环 (产品段闭环)
- [N] Experience → Learning (C-026/C-027 M1/M0→M4): 执行完 → 经验入库 → 画像 → 下次路由引用
  (B-7 经验回写; experience_store 84 条已有, 缺消费端)
- [N] Release (C-029 M0): v0.1.0 正式发布门 + 产物 (CLI wheel/安装包, 见 python-cli-wheel-deployment)
- 验收: 一次完整产品循环 (idea→发布→学习改进) 可演示、可审计

### 产品线 (docs/products/*.md — 企业 OS 愿景, 排期靠后)
- governance-platform / learning-platform / knowledge-base / agent-orchestration / industry-factory /
  backlog-sweeper / channel-platform / audit-evidence-chain — 均为 [N] 方向性, 洋葱式开源入口
  (OPEN-CORE.md: 开源外层获客 → 闭源内层变现: Governance/RBAC/Compliance/RAG/Analytics)

---

## 3. 需要优化的点 (贯穿性改进, 非独立 Sprint)

### 3.1 诚实度/宣称一致性 (最高优先)
- [V][N] 全库扫"宣称已 ✅ 但无消费"模式: LLMRouter(0)、Skill(2.5MB 消费 UNKNOWN)、
  Experience(84 写 0 读)、learning/release 端点 (runtime UNKNOWN) — 逐一收敛为 真实/降级标注/移除
- [V] CLI命令参考文档.md 逐命令核对 (标记 NEEDS HUMAN), 修 BROKEN_REFERENCE

### 3.2 运维可靠性 (8-27 计划遗留, 需先验证现状)
- [V] API 认证最小化: 无 token → 401 (历史 P1, 需查是否已实施)
- [V] 服务守护/自启 + 心跳 (8011/5180; 当前无监听进程 — 需恢复环境或守护)
- [V] 数据备份/恢复: factory backup 已存在 (cli_factory.py:1789), 验证 backup restore 一致性
- [V] 数据结构版本化迁移 / 崩溃恢复演练 (checkpoint 恢复, exec/checkpoints.json)
- [V] 操作撤销/确认 + 回收站 (删除/推送二次确认)
- [N] provider 故障切换 (deepseek 宕机 → 备用 + 告警)

### 3.3 质量体系 (C 系列: 完整/可靠/可信)
- [N] 执行结果质量分 + 多候选优选 (B-5; T5.3 优选默认关 → 评估后开)
- [N] PRD/工程计划质量评估器 (B-6, 复用 M3d 六维)
- [N] skill 路由 (B-1) + agent 能力路由/负载均衡 (B-2) + 统一 Capability Router (B-4)
- [N] 项目级 RAG (B-8, KnowledgeStore + 向量检索; 索引已就绪)
- [V] 长跑并发测试 / 稳定性基准 (C-5); 发布门 CI 稳定 (ci.yml 存在, 验证生效)

### 3.4 代码/架构卫生
- [N] 消灭 Unknown: factory-core 生产职责 / factory.db(3.3MB) 用途 / exec 角色触发 /
      Release-Learning 运行时 — 审计定案 (审计逐代码, UNKNOWN 不猜)
- [N] 巨型文件治理: cli_factory.py 384KB、fastapi_adapter.py 380KB、884KB 产品方案书 —
      拆分/归档为可维护单元 (历史保留但导航收敛)
- [N] 测试分层提速: console 全量 5700+ 慢 → 关键 ≈1049 门禁 + 全量 nightly
- [V] 仓库卫生: $SMOKE_ROOT/unused/demo 残留、项目空壳 812 个 (P-* 空目录)、untracked 堆叠
      (fix-sprint-design 13 份 + git-reality 2 份 + exec/checkpoints.json + 3 个 html) — 先确认归属再提交

### 3.5 前端/UX 产品化 (K-7 延续; UI 铁律)
- [V] WebUI 三入口 (任务/刷新/停止已 E2E) → 扩展: 审计查看、产物查看、审批流全 UI 化
- [N] UI Gate: build + 测试 + 联调 + 浏览器验证 (非 mock 非占位; 前端只调 API 不"加戏")
- [N] 真实用户实测 (中文 IME/浏览器) — 报告分 Automated/Manual
- [N] 帮助中心/入门: 非全技术型用户可用 (快捷键 + 引导) — 借鉴 MarkPad 验收标准

---

## 4. 建议排期 (依赖关系)

```
阶段 0 (Fix, 待批准): S-FX0 → S-FX1 → (S-FX2 并行) → S-FX3 → S-FX4     ~1-2 周
阶段 1 (M3 产品智能): PRD 实体 → Req 演进 → Replan+变更回流                 ~1-2 周
阶段 2 (M4 学习/发布): Learning 消费端 → Release v0.1.0 发布门 + wheel      ~1-2 周
阶段 3 (产品化/增长): 公开分发/种子用户/案例 → WebUI 实测 → 社区            持续
阶段 4 (企业 OS 线): docs/products 产品线按洋葱式逐个开源入口              远期
贯穿: 3.1 诚实度 → 3.2 运维 → 3.3 质量 → 3.4 卫生 → 3.5 UX
```

**关键路径**: Fix 地基 (S-FX1) → PRD/需求链 (M3) → 发布门 (M4) → 分发/种子用户。
**阶段 0 前置**: 用户批准 fix-sprint-design (当前 13 份文档 untracked 未提交, 建议批准后先 commit 基线)。
**阶段 1+ 前置**: 每项先出设计文档 → 用户批准 → 实施 (架构破坏/产品转向需人工批准, 记录风险)。

---

## 5. 从 idea 到产品 — 是否完整 (答复)

**否, 尚未完整。** 当前 = "计划→执行→审计" 纵向闭环 (M4 E2E PROVEN) + 治理契约冻结 (STEP10),
但 **产品闭环缺两端**:
- 前端: idea → Requirement(无下游) → PRD(ABSENT) → Plan — 只有 Plan 真实
- 后端: Run → Artifact/Verify(未挂链) → Learning(0 消费) → Release(未发布) — 只有 Run 真实

补齐路径 = 本计划阶段 0 (Fix 8 项) + 阶段 1-2 (M3/M4) + 阶段 3 (分发增长)。
全部完成且用户实测通过后, "从 idea 到产品" 才成立。
