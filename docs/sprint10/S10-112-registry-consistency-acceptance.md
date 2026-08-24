# S10-112 — P0-10 注册表一致性 + P0-11 对称路径一致性：独立验收报告

> 日期: 2026-08-25 | 版本: v1.1.81 | 验收人: Hermes (CTO, 独立验证 — 非 Codex 自报告)
> 实现: `b35e7ff` (test(S10-112))
> 前置: v1.1.80 (CHANGELOG) · M3 主线 7/7

---

## 验收矩阵

| # | 验收项 | 结果 | 证据 |
|---|---|---|---|
| P0-10 | 5 类注册表各 ≥1 测试全过 | ✅ | test_s10_112_registry_consistency.py — 我独立跑 17 passed (CLI/意图/action/事件/API 全真断言, 动态读实现) |
| P0-11 | 对称路径各 ≥1 测试 | ✅ | test_s10_112_symmetric_paths.py — conversation/discovery 同输入同字段 (我的抽查: conv==ds 字段一致); CLI/API 双入口 |
| 不一致已修复 (如实报告) | ✅ | 漂移清单 4 项 (见 §2) — 含**事件漂移导致审计丢记录** (真实缺陷) |
| 全量回归 0 新增 | ✅ | console+api: **5246 passed / 1 skipped / 0 failed** (我的环境) |
| v1.1.81 | ✅ | pyproject=1.1.81 + 断言 + CHANGELOG + FEATURES + 待办清单 P0-10/11 ✅ |

## 1. 独立验证实录（我的脚本 9/9 + Codex 17 测试复跑）

```
✅ pyproject==CHANGELOG==1.1.81 (版本漂移已修复)
✅ CLI parser 28 子命令, 含核心命令
✅ 意图规则类型 ⊆ DEFAULT_ROUTES (除文档化例外 current_project/show_cost)
✅ EVENT_TYPES ≥30 (n=63, 含补入的交付链 4 事件)
✅ P0-11 conversation/discovery 同输入同字段
```

## 2. 漂移清单（本 Sprint 的核心价值 — 如实报告, 非 Codex 自报告）

**发现并修复 4 类漂移**:
1. **版本漂移**: pyproject=1.1.79 vs CHANGELOG v1.1.80 (1a8ecee 声称未同步) → 同步 1.1.81
2. **意图注册表漂移**: 37 个关键词意图 (audit_*/debug_*/memory_*/product_*/review_*/discovery_start/
   factory_budget/rename_project/production_session_view) 只靠 S10-082 同名兜底、未显式声明路由
   → DEFAULT_ROUTES 补 37 条显式映射 (路由解析逐字节不变)
3. **Action 敏感注册表漂移**: accept_project/org_manage/repair_task/team_execute 声明 sensitive 未强制
   (与 docstring"确认门"口径漂移) → 补入会话确认门; create_project 被门强制但 registry 未标 → 补标
4. **事件注册表漂移 (真实缺陷)**: delivery.py 实际发射 PATCH_APPLIED/CODE_VALIDATED/
   DELIVERY_COMPLETED/DELIVERY_FAILED 但漏注册 → AuditEmitter 失败安全静默丢弃 (审计缺记录!)
   → 补入 EVENT_TYPES (33→63, 含其它 sprint 已加事件)

**保留 (设计如此, 非漂移 — 测试以文档化例外处理)**:
- current_project (会话内 S10-076 只读特判, 无 action) · show_cost (ChatService 降级) ·
  create_product (conversation 发现流程接管) · execute_task 别名 (与 run_task 共享执行链) ·
  敏感集合粒度 (registry 按 action 名, 门按 intent 类型; 会话级门扩展补平) ·
  CAPABILITY_MATRIX 能力级粒度 (端点级注册表在 FEATURES.md §9; 建议未来补端点级矩阵列)

## 3. 契约测试

- 新增 2 文件 17 用例 (全真断言, 无跳过/空断言): 5 类注册表 + 4 对称路径
- 数据从实现动态读取 (build_parser/DEFAULT_ROUTES/build_default_actions/EVENT_TYPES/app.routes), 无硬编码快照
- 全量: 5246 passed / 1 skipped / 0 failed

## 4. 诚实记录

- 我的脚本 1 处未算文档化例外 (current_project/show_cost) — 修正后 9/9, 实现正确
- Codex 沙箱 60 failed + 5 errors (全仓) 经 unsandboxed 抽查为环境伪失败, 我环境 console+api 0 failed
- 建议: CAPABILITY_MATRIX 补端点级矩阵列 (未来); 该套件为"防遗漏"常驻门禁 — 后续新增命令/意图/action/事件/API
  必须同步注册表否则红

## 5. 结论

- **通过**。Founder 核心担忧 ("改不全、有遗漏") 已机制化: 5 类注册表一致性 + 4 对称路径 = 常驻防遗漏门禁。
  首跑即抓到 4 类真实漂移 (含审计丢记录缺陷) 并修复; 6 类设计例外文档化。
- 价值证明: 若这套测试早存在, pyproject/CHANGELOG 版本漂移、37 意图漏路由、4 审计事件静默丢弃 都不会发生。
