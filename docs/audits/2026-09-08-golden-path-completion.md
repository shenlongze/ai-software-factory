# Cognitive Golden Path — Completion Report

**日期**: 2026-09-08 | **阶段**: S50 / Golden Path | **状态**: ✅ Implemented + Verified (自动化)

> 任务书: "让一个完全不了解 AI Factory OS 内部架构的普通用户, 只通过自然语言,
> 在一个连续的产品认知过程中, 从模糊想法走到经过确认的 PRD、Development Plan,
> 并最终进入现有 Production Runtime 完成真实交付。"

---

## 1. Phase 0 审计结论 (24 问, 4 RED — 全为缺失能力)

| # | 问题 | 结论 |
|---|------|------|
| 1 | Product Understanding 持久化 | ✅ GREEN (S49: conversations/{cid}.json) |
| 2 | 跨 Session | ✅ GREEN |
| 3 | 自然语言增量修改 | ✅ GREEN (语义操作管道) |
| 4 | 修改/否定/延后/替换 | ✅ GREEN (UPDATE/NEGATE/DEFER/REPLACE) |
| 5 | 依赖关键词/固定 Intent | 🔴 RED-1 → **修复**: LLM Semantic Interpreter (生产) |
| 6 | 真正使用 LLM 语义理解 | 🔴 RED-1 → **修复**: llm_semantic_interpreter (DeepSeek llm_raw) |
| 7 | LLM 结果经 Domain 验证 | 🔴 RED-4 → **修复**: validate_proposal → apply_operations |
| 8 | 用户能看到 AI 当前理解 | ✅ YELLOW → **修复**: understanding_statement + API |
| 9 | 自然语言修正理解 | ✅ GREEN (Confirmation Loop) |
| 10 | 上下文驱动主动缺口分析 | ✅ YELLOW → **修复**: analysis_gaps (动态, 非模板) |
| 11 | PRD 结构化对象 | ✅ GREEN (S49) |
| 12 | PRD 来自 Understanding | ✅ GREEN |
| 13 | PRD 可版本化 | ✅ GREEN (v1→v2 单调) |
| 14 | PRD 修改后保持 provenance | ✅ GREEN (source_product_understanding_version) |
| 15 | 存在 Development Plan | 🔴 RED-3 → **修复**: product_truth PLAN-* 经 golden_path 桥 |
| 16 | PRD→Plan 真实连通 | 🔴 RED-3 → **修复**: generate_plan (prd_id/prd_version) |
| 17 | Plan→Production 真实连通 | 🔴 RED-3 → **修复**: execute_approved → execute_task |
| 18 | Intent→Workflow 旧控制路径 | ⚠️ legacy 标记 (conversation_os EXECUTE) + 新域 gate 保护 |
| 19 | WebUI 前端状态作为 Truth | ✅ GREEN (前端无 PU 状态) |
| 20 | API 双 Conversation Runtime | ⚠️ legacy 保留 (新域端点已建) |
| 21 | CLI/WebUI/API 同业务事实 | ✅ GREEN (新域全走 Application Layer) |
| 22 | 第三套 Runtime | ✅ GREEN (无新增) |
| 23 | Session restart 恢复 PU | ✅ GREEN (Test B + Phase 6) |
| 24 | 未确认就进生产 | 🔴 RED-2 → **修复**: Production Gate 强制 |

---

## 2. 实现架构 (Internal Structured, External Natural)

```
User Message
  → Context Assembly (持久化 Understanding, 非猜)
  → LLM Semantic Interpreter (生产; DeepSeek) / deterministic (测试注入)
  → Semantic Proposal {operations: [ADD|UPDATE|NEGATE|DEFER|REPLACE|
    CONFIRM|REJECT|CLARIFY|QUESTION|SUGGEST]}
  → Domain Validation (validate_proposal — LLM 不得直接写 Truth)
  → apply_operations (唯一 Truth 写路径, conflict/supersession)
  → Product Understanding (persistent)
  → [用户可见 statement] → 自然修正 Loop
  → PRD (versioned, provenance) → 用户确认 → Development Plan (PLAN-*)
  → 用户确认 → Production Runtime (NodeRun/Artifact/Verification/Delivery)
```

### 新增文件

| 文件 | 职责 | Commits |
|------|------|---------|
| `semantic_proposal.py` | SemanticOperation 注册表 + validate_proposal + apply_operations | 09adb755 |
| `llm_semantic_interpreter.py` | LLM 语义理解 (context assembly, JSON 解析, 降级) | 09adb755 |
| `golden_path.py` | Understanding→PRD→Approval→Plan→Approval→Production 编排 | bf5f78f8 |
| `product_understanding.py` (扩展) | DEFERRED 状态 + get_fact + snapshot deferred/rejected | 09adb755 |
| `conversation_app.py` (重构) | 统一 Semantic Proposal 管道 + statement/gaps | 09adb755/7c5bd72d |
| `conversation_os.py` (标记) | legacy EXECUTE 明确标记 + 新域 gate 保护 | 25e202de |
| `fastapi_adapter.py` (扩展) | statement + gaps + 既有 PU 端点 | 102d0311 |
| 测试 ×7 | Phase 1-7 全链验证 (96 新测试) | 各 commit |

### Commits (8, 每 Phase 独立)

```
09adb755  Phase 1+2: semantic proposal pipeline + LLM interpreter
922db280  ruff cleanup
bab3250f  ruff cleanup part 2
7c5bd72d  Phase 3: understanding confirmation loop + adaptive gap analysis
bf5f78f8  Phase 4+5: PRD approval -> development plan -> production gate
25e202de  Phase 5: legacy EXECUTE marked + new-domain gate guard
82ced221  Phase 6+7: session restart continuity + full E2E
102d0311  API: expose statement + gaps
```

---

## 3. 验收证据 (真实执行)

### Golden Path E2E (test_golden_path_e2e.py — 3 passed)

21 步全链真实走通:
模糊想法 → 自然讨论 (4 facts) → 用户可见 statement → 手机端→网页端 REPLACE →
不要登录 CONSTRAINT → 排行榜先不做 DEFER → 按键→摇杆 REPLACE → 主动缺口分析 →
Session close → 新 Session 恢复 → 继续修改 (暂停) → PRD v1 → "简单一点" →
PRD v2 (provenance 单调) → 用户确认 PRD → Development Plan (prd_id 溯源) →
用户确认 Plan → Production Runtime → **NodeRun COMPLETED ×4 + verification PASS
+ artifact 生成 + 交付物 delivered**。

### 生产 Gate (test_golden_path_gates.py — 15 passed)

- 无 approved PRD → 拒绝执行
- PRD 确认但 Plan 未确认 → 拒绝执行
- 全门通过 → execute_approved 真实经 production_runtime (NodeRun/Artifact/Verification)
- Plan 存 product_truth/plans.json (正式域), conversation 无第二份 (No Second Truth)

### 语义操作 (test_semantic_proposal.py — 20 passed)

ADD/UPDATE/NEGATE/DEFER/REPLACE/CONFIRM/REJECT/QUESTION/CLARIFY 全部到 Truth
mutation 正确; CONFIRM 无对象 → 拒绝幻觉确认; DEFERRED 恢复不新增重复。

### LLM Interpreter (test_llm_semantic_interpreter.py — 11 passed)

LLM 输出 (fenced/raw JSON) 解析 → validate → apply; 非法输出/LLM 不可用 →
**显式降级 CLARIFY (不猜事实, 不部分写 Truth)**; prompt 含持久化 Understanding。

### Confirmation Loop (test_understanding_confirmation.py — 20 passed)

statement 可见 (含 confirmed/pending/deferred/rejected/gaps); 自然修正
("不是, 改成网页"→ REPLACE); "排行榜还是保留只做本地最高分" → 恢复 + 精化;
简化语义 5 变体; 延后语义 5 变体 (语义等价, 非关键词特例)。

### Session Restart (test_session_restart_golden_path.py — 4 passed)

Session A 建理解 → close → Session B 恢复 (新实例); 继续修改 supersede;
PRD→Plan 链跨 session; provenance version 稳定。

### 回归

- 全部 Golden Path 测试: **123 passed**
- conversation_os legacy 测试: 16 passed (无回归)
- product_truth / requirement_node / node_loop: 41 passed
- 无 attributable regression (改动文件相关测试全绿)

---

## 4. 已知限制 (诚实声明)

1. **LLM 真实调用未在本机冒烟**: 环境无 DEEPSEEK_API_KEY, llm_raw 返回 None。
   LLM 路径经 fake-LLM 测试验证 (同一 validate/apply 管道); 降级逻辑已测。
   真实 DeepSeek 语义冒烟需配置 key 后人工验证。
2. **Deterministic interpreter (测试用) 不等于生产**: 生产理解走 LLM
   (llm_semantic_interpreter); 测试 fake interpreter 仅为语义能力验证,
   经与生产完全相同的 Domain Validation/Mutation 管道。
3. **WebUI 未接新域**: 新 Conversation Domain API 已就绪, 前端未迁移
   (S50 范围: 不强制 UI 迁移; Golden Path 域/API/CLI 层能力已闭环)。
4. **conversation_os legacy EXECUTE 保留**: 明确标记 LEGACY + 新域 gate 保护;
   旧 WebUI conv_* 路径行为不变 (其生产触发靠显式 trigger_work)。
5. **历史 pre-existing 失败** (非本阶段引入): m3c_scheduler ×2 /
   release_packaging ×1 / s10_109 ×1 / s10_112 ×3 / s10_116 ×1 /
   web_adapter 白名单 ×1 (85 历史路由漏登记)。

---

## 5. 最终判断

> 本阶段验收标准 (Golden Path §28): 一个完全不了解 AI Factory OS 内部架构的
> 普通人, 可以只通过自然语言从模糊想法一路走到确认后的 PRD、Development Plan,
> 并真正进入现有 Production Runtime 完成交付。

**自动化验证 COMPLETE**: 全链真实执行 (NodeRun COMPLETED + verification PASS +
Artifact + Delivery); 用户可见理解 + 自然修正; Session restart 连续; 语义等价
表达 (非关键词覆盖); Production Gate 强制 (未确认绝不进生产); 未创建第二套
Task/Plan/Production Truth; Intent 不在 Golden Path 主链。

**人工验收待用户**: 真实 LLM (DeepSeek) 中文自然语言会话 + WebUI/CLI 实机走查 —
自动化通过 ≠ 人工验收通过 (用户铁律)。建议按 E2E 步骤人工复现一次。
