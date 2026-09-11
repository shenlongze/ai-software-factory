# AI Factory — Actionable Findings & Issues (2026-09-04)

> Product Professor 审查产物 | 依据见 00-REVIEW-OVERVIEW.md | 每个发现: 证据 + 建议动作
> 不创建 GitHub live issues (未经许可); 作为 Markdown issue 文件供 triage

---

## F-01 [P0] Verification SSOT 归属未冻结 (D 类 UNPROVEN)
- 证据: FX-08; STEP10 §14 CONTRACT-ONLY; exec results + ExecState.verify 并存
- 风险: 验证事实无唯一真源 → 审计链在"验证"环节不可信
- 建议: S-FX0 先取证 (零代码) → Contract 更新 → 实施

## F-02 [P0] execution_plan 仍是可写路径, 三套 Task 真相风险 (INV-012)
- 证据: FX-02; STEP10 C-01/D-9; execution_plan T-* 历史冻结未落地
- 风险: 平行 Task SSOT → 状态语义不可信 (FAILED/BLOCKED 溯源困难)
- 建议: S-FX1 FX-02 冻结写入 + FX-01 exec→backlog 引用 (地基, 优先)

## F-03 [P0] Artifact/Verification 未挂回主链 (D-6 未实施)
- 证据: FX-04; C-019/C-020 M2; exec ART-* 与会话链无关联
- 风险: "代码改完的产物/测试结果"用户不可见 → 产品承诺 (全链可审计) 打折
- 建议: S-FX3 FX-04 Run/Record 挂 Artifact/Verify, Task 经 Run 可达

## F-04 [P1] Requirement 无下游, 需求链 trace 断裂 (G-REQ-01)
- 证据: FX-03; C-004 M0; requirements.json 7 条无引用
- 风险: "idea" 在系统中无归宿 → 从 idea 到产品缺前链
- 建议: S-FX2 FX-03 plan 携带 requirement_id (只读引用) + FX-07 分析落盘

## F-05 [P1] PRD 独立实体 ABSENT (D-5/INV-011, M3 承诺未兑现)
- 证据: CURRENT_SYSTEM_TRUTH §12; MASTER_PRODUCT_TREE 02 层 PRD [M0]
- 风险: 无结构化产品承诺 → 计划质量无锚点, 变更回流无对象
- 建议: 阶段 1 (Fix 之后) PRD Domain SSOT + Req→PRD→Plan 全链稳定 ID

## F-06 [P1] Model Selection 生产消费者 = 0 (宣称 vs 现实)
- 证据: FX-05; C-012 M1; LLMRouter 消费 0; 固定 provider._default_llm_fn
- 风险: "智能路由/多模型"是公开卖点 (LLM智能路由设计说明.md) 但无生产兑现 → 信任受损
- 建议: S-FX4 FX-05 Task/Agent→Policy→Selection 进治理链; 或公开降级标注 (选一, 不可并存)

## F-07 [P1] Skill / Experience 写多读少 (资源闲置)
- 证据: C-014 M1 (skills.json 2.5MB 消费 UNKNOWN); C-026 M1 (experience 84 写 0 读)
- 风险: 高成本积累无产出 → 学习层叙事空洞 (M4 承诺)
- 建议: 阶段 2 Learning 消费端 (B-7 经验回写 → 路由引用); skill 路由 B-1/B-4 统一 Capability Router

## F-08 [P1] 运行态缺失: 服务未监听, 守护/自启未知
- 证据: 8011/5180 无 LISTEN 进程 (2026-09-04 检查); 8-27 计划 P0-X 服务守护/自启 [V 未验证]
- 风险: 交付"可运行产品"叙事 vs 现场无服务 → 演示/验收随时失败
- 建议: 先验证现状; 守护+自启+心跳落地; 500/502 先查服务存活纪律入库

## F-09 [P1] API 认证 / RBAC / 撤销确认 状态不明或缺失
- 证据: 8-27 计划 P1-X API 认证 / P2 RBAC / P1-X 撤销确认 — 现状 [V 需核实]
- 风险: 多用户/企业故事 (AI Organization OS) 无安全地基
- 建议: 审计定案; 最小认证 (无 token→401) 先上; RBAC 排 M3 之后

## F-10 [P1] 发布/分发未开始 (战略风险: "没人知道")
- 证据: docs/release/v0.1.0-release.md 状态=待发布; OPEN-CORE Community v0.1.0; 无种子用户/社区证据
- 风险: 创始人自评"风险从做不出来变没人知道" — 无发布即无验证
- 建议: 阶段 3 v0.1.0 发布门 (wheel/安装包, 见 python-cli-wheel-deployment) + 官网/README 案例 +
       种子用户实测 (报告 Automated/Manual 分离) + 社区反馈闭环

## F-11 [P2] 文档债务: 1050+ 历史文档 vs 真相导航 (已治理, 持续)
- 证据: DOCUMENTATION_MATRIX 1005+ docs; 治理基线已提交但大量 T4 文档易被误读为当前
- 建议: 新 AI/新人入口强制 READ FIRST; 过期文档顶部加 Historical banner (脚本批量);
       引用时必须标 Historical (治理 §6 已立, 执行抽查)

## F-12 [P2] 巨型文件与残留 (可维护性)
- 证据: cli_factory.py 384KB / fastapi_adapter.py 380KB / 884KB 产品方案书; $SMOKE_ROOT 字面量目录;
       812 个 P-* 空项目壳; untracked 堆叠 (fix-sprint-design 13 + git-reality 2 + exec/checkpoints.json + 3 html)
- 风险: 维护成本、新人理解成本、并发工作区误提交 (git add -A 卷走他人文件)
- 建议: 拆分/归档; 空壳清理前确认归属; untracked 先提交正确基线 (Fix 批准后) 再开发

## F-13 [P2] Unknown 清单未清零 (诚实度)
- 证据: CURRENT_SYSTEM_TRUTH §13: factory-core 生产职责 / factory.db 用途 / exec 角色触发 /
       Release-Learning 运行时 / Verification downstream
- 风险: UNKNOWN 不猜纪律下, 后续设计可能踩空
- 建议: 审计逐代码定案 (3.4); 每项给 真实/降级/移除 三选一结论

---

## Triage 建议
- P0 (先做): F-01 F-02 F-03 → = S-FX0/S-FX1/S-FX3 核心, 批准 fix-sprint-design 即启动
- P1 (紧随): F-04 F-05 → 阶段 1 M3; F-06 → 阶段 0 S-FX4 或公开降级; F-07 → 阶段 2 M4;
  F-08 F-09 → 运维安全 (可与 Fix 并行); F-10 → 发布门 (阶段 3)
- P2 (贯穿): F-11 F-12 F-13 随审计/卫生批次消化
