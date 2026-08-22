# S10-088 专家真干活 — Completion Report

> 日期: 2026-08-22 | v1.1.10 | 依据: Claude M2 评估 (骨架诚实/产出未兑现) → 裁决: 专家真干活 (消费上一产出 + 接真实 LLM + M2→M1 消费链打通)

---

## 交付 (T1-T5 + 版本)

| 任务 | 模块 | 内容 |
|---|---|---|
| T1 | `actions.py` product_pipeline | 生产路径装配 `ReasoningProvider()._default_llm_fn()` (有 providers.json + key → 真调 7 专家); 无 LLM → `llm_fn=None` → pipeline 确定性兜底非空; `llm_fn` 注入点保留 (测试/生产同路径, 无特判) |
| T2 | `handoff_bus.py` + `pipeline_runner.py` + `artifact_registry.py` | `route` 每步经 `ArtifactRegistry.read` (新增) 读上一资产正文, 作 produce 第 4 参传入; `_produce` prompt 嵌 `上一资产内容: <前 2000 字>` (PARENT_CONTENT_LIMIT=2000); 血缘双字段 (parent_artifact + parent_event_id) 保留 |
| T3 | `actions.py` prepare_project | 项目存在专家 `prd` 资产 (created_by=agt-*) → 用专家产出生成 PRD.md (M2→M1 打通); 无专家资产/非 agt-* → 规则兜底 (向后兼容) |
| T4 | `expert_factory.py` build_team + `pipeline_runner.py` | build_team 装配后 `registry.add` 落盘 agents.json (persist=True 默认, 含 7 个 agt-*); `persist=False` 保留不自动落盘选项; ProductPipeline 工厂注册表指向项目内 agents.json (隔离 ~/.factory 默认空间) |
| T5 | `tests/console/test_m2_agent_core.py` | 注入 fake llm_fn → market 资产含 LLM 真实内容 (≥1 条非 "待补充/规则占位" 段落); 全 7 资产含 LLM 内容断言 |
| 版本 | pyproject/install.sh/docs/CHANGELOG/断言 | v1.1.9 → v1.1.10 全同步 |

## 验收断言实测 (单次跑: 我要做CRM → 让PM分析 → 准备开发, fake LLM 注入生产路径)

| # | 断言 | 实测 |
|---|---|---|
| 1 | 配置 LLM → 7 资产含 LLM 内容 (非规则占位) | ✅ 7 次 LLM 调用 (pm/market/competitive/ux/architect/qa/prd), 7 资产全部含 `LLM-EXPERT` 内容 |
| 2 | 后一角色 produce 收到前一资产正文 (prompt 含 content) | ✅ 测试断言 produce 第 4 参含上一环落盘正文 (MARKER-<prev_role>-); prompt 含 `上一资产内容:` (根环 `(无 — 根资产)`) |
| 3 | 让PM分析 → prepare_project → PRD.md 含专家产出 | ✅ PRD.md 首行 = 专家 prd LLM 产出 (`# LLM-EXPERT prd`); 无专家资产 → 规则模板兜底 (回归 304 passed) |
| 4 | build_team → agents.json 含 7 个 agt-* | ✅ 项目内 agents.json 含 7 个 agt-* (agt-it-pm-1 … agt-it-prd-1) |
| 5 | M1 零回归; 全量 0 failed (runtime flaky 除外) | ✅ 见下 "回归" |
| 6 | 版本 v1.1.10 同步 | ✅ pyproject/install.sh/USER_GUIDE/DEPLOYMENT/README/CHANGELOG/完整方案书/版本断言测试 |

## 回归

- **定向**: `test_m2_agent_core.py` + `test_s10_084_pipeline.py` → 48 passed; `test_session_orchestrator` + `test_session_agents` + `test_s10_070_e2e` → 304 passed; `test_s10_074_deployment` → passed (wheel 构建需网络, 已实测通过)
- **全量**: 11918 passed + 1 skipped, 64 failed + 5 errors (沙箱环境) — **与 base commit (38d48c7) 对照: base 72 failed, 本分支 64 failed, 失败集为严格子集 (零新增失败)**; 8 个 base 失败 (版本断言/init/packaging/demo smoke) 因版本同步转绿
- **剩余失败全部为沙箱环境限制 (base 同现, 非本 Sprint 引入)**: `tests/factory_runtime/*` (53 failed + 5 errors — 进程/端口 `Operation not permitted`); `tests/console/test_session_team_decision.py` (写真实 `~/.factory` 被沙箱拦截); `tests/llm/test_llm_router_*` (3 个全量运行串扰) — **沙箱外实测全部通过** (135 passed)

## Git

```
81c017d T1 product_pipeline 接 LLM → 506c84f T2 交接消费上一产出 → eaab304 T3 prepare_project 消费专家 PRD
76c59ff T4 build_team 落盘 → a276804 T5 真实产出断言 → 4961d7c 版本 v1.1.10
clean (仅历史遗留 untracked: capability-audit/audits/unused 等, 非本 Sprint 产物)
```

## 风险

1. **真实 LLM 环境**: 配置 providers.json + key 后 "让PM分析" 走真实 API (7 次调用/趟), 成本/延迟随趟数线性; 失败自动确定性兜底 (诚实, 不静默) — 建议生产调用加缓存/预算护栏 (后续 A6/记忆)
2. **build_team persist 副作用**: 默认落盘到项目内 agents.json, 重跑管线 agent id 递增 (agt-it-pm-2 等) — 已隔离项目空间, 不污染 ~/.factory; 多趟重跑会累积专家 (去重/回收待后续)
3. **交接内容截断 2000 字**: 长资产正文只嵌前 2000 字, 后环可能丢失尾部细节 (M3 递归拆解可解决)
4. **prepare_project 消费最新 prd 资产**: 若后续有新管线覆盖旧 prd, PRD.md 取最新版 (版本递增保留历史, 可取 v1/v2 对比)

## 下一步 (backlog, 本 Sprint 明确不做)

1. M3 递归原子拆解 (PRD 消费链已铺路)
2. 审批→PR 真实链路 (E4) / 真实 issue 源
3. 记忆回流 (E5)
4. A6 多 LLM 路由 / 真 MCP 工具进循环
5. `expert build` CLI 命令包装
