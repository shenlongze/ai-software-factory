# S10-121 — K-5 评测体系渐进：设计文档 + 实现计划（CTO 架构设计 + Codex 指令）

> 日期: 2026-08-25 | 前置: v1.1.94 · K-1~K-4 ✅ (战役第五战役)
> 用途: 三部门循环第 ②→③ 步 — Hermes(CTO) 设计 → Codex(工程) 实现
> 规格来源: docs/sprint10/S10-121 提示词（K-5: P0-1/4/5 + C-1/4/5/6 + H-1 + F-10 + M5-7）

---

## 0. 现状审计（CTO 独立复核）

| 资产 | 现状 | K-5 用途 |
|---|---|---|
| P0-10/11 | 注册表/对称路径门禁 (v1.1.81) | 评测项复用 |
| execution_quality | K-2 (执行质量分 + PRD/工程评分) | C-4 部分已覆盖 |
| eval_loop | K-3 (低分→修复→复评) | 评测基建 |
| trace_context | K-4 (审计可追踪) | P0-9 信赖地基 (并发隔离验证) |
| 错误码 | 无集中表 (分散消息) | M5-7 建表 |
| pytest-cov | **未安装** | F-10 用 stdlib trace (零依赖) |
| E2E 测试 | test_console_lifecycle_acceptance / m3e_full_chain 等 | H-1 复用/编排 |
| 版本四件套 | pyproject+CHANGELOG+FEATURES+断言 手工同步 | P0-5 发布门 |

版本: 1.1.94 → 目标 1.1.95。

## 1. 架构决策

### 1.1 评测核心（新模块 `factory-console/session/eval_suite.py`）

```python
# 7 维评测第一版 — 每维 ≥1 可断言评测项 (复用现有契约/质量分/trace, 不新造业务)
EVAL_DIMENSIONS = [
    ("correctness",    "正确性",   [断言项: 全量测试通过率, E2E 链路, 质量分>=阈值]),
    ("robustness",     "鲁棒性",   [断言项: 异常输入不崩, 失败安全路径]),
    ("consistency",    "一致性",   [断言项: P0-10 注册表一致性, P0-11 对称路径, J-1 状态一致]),
    ("performance",    "性能",     [断言项: 关键操作耗时上限 (宽松)]),
    ("security",       "安全",     [断言项: 审计封存/脱敏路径存在 (未覆盖维度如实标)]),
    ("longevity",      "长期",     [断言项: 并发不串 (trace 隔离), 长跑冒烟]),
    ("user_value",     "用户价值", [断言项: 学习闭环引用存在 (评测口径如实标注)]),
]

class EvalSuite:
    def run(self, workspace, *, gate=None) -> EvalReport
        # 只读跑评测: 每维 通过/失败/未覆盖 + 证据引用 (测试名/文件/数据)
    def level(self, report) -> str  # L0/L1/L2/L3 判定 (第一版至少 L0/L1)
        # L0 = correctness+robustness+consistency 通过
        # L1 = L0 + performance+security 通过 (未定义维度 → 如实"未覆盖")
```

- 入口: `factory eval [--gate patch|minor|major] [--check]` — 只读跑评测不写业务
- 报告: markdown (docs/eval-report-<ts>.md 可选 --save) + stdout

### 1.2 P0-5 发布门自动化

- 等级: patch=L0 · minor=L0+L1 · major=L0+L1+L2 (L2/L3 未定义 → 如实"未覆盖")
- `factory eval --gate patch` → 跑 L0 项 → 失败 → 明确阻断报告 (rc 非 0)
- `--check` 只读模式: 报告等级不阻断 (默认 --check, 门禁不破坏现有版本流程 — 四件套同步照旧)

### 1.3 P0-4 长跑 + 并发（零污染真实数据）

- 并发 fixture: 多项目并发任务 (temp workspace) → 断言不串 (K-4 trace 隔离: 各项目事件 trace_id 独立)
- 长跑冒烟: 30min 可配置脚本 (temp workspace, 每 N 秒心跳断言存活)
- 24h 脚本: 提供 (如 scripts/smoke_24h.py 或测试标记) — **未真跑 24h → 如实标"待长跑"**

### 1.4 H-1 整体流程评测

- 端到端 fixture: 创建→发现→PRD→工程→执行→证据→审批→交付 — 每节点衔接断言
  (J-1 status 单一来源投影校验: project.json.status 按生命周期推进)

### 1.5 F-10 测试覆盖度

- stdlib trace 或 coverage 脚本 → 模块级覆盖率统计 → 报告 (不设达标线, 只报)

### 1.6 M5-7 错误码表

- 集中表 `docs/error-codes.md` (或代码常量): 模块:CODE: 消息: 建议下一步
- 契约测试断言主要错误路径有码 (如 E4xx 统一)

### 1.7 C-4 中间盲区核对

- 对照 K-2 已覆盖 (PRD/工程/执行质量分) → 输出剩余盲区清单 (如实, 不假装全清)

### 1.8 注册表门禁

- `factory eval` 命令 → 同步 CLI 注册表 (P0-10)

## 2. 契约测试（tests/console/test_s10_121_eval_suite.py, ≥10）

1. **七维评测**: 每维 ≥1 断言项存在且可跑 (报告含 通过/失败/未覆盖 + 证据)
2. **L0/L1 判定**: 全绿 → L0/L1; 有失败 → 对应等级不过
3. **发布门**: --gate patch 跑 L0 (失败 → rc 非 0 阻断); --gate minor 跑 L0+L1; --check 只读不阻断
4. **并发不串**: 多项目并发 fixture → 各项目 trace_id 独立 (K-4 隔离断言)
5. **长跑冒烟**: 短时长冒烟可跑 (可配置); 24h 脚本存在 (标待长跑)
6. **H-1**: 端到端 fixture 每节点衔接断言 (J-1 状态投影)
7. **F-10**: 覆盖率报告生成 (模块级)
8. **M5-7**: 错误码表存在 + 主要错误路径有码
9. **C-4**: 盲区清单文件存在 (K-2 已覆盖 vs 仍盲)
10. **注册表**: eval 命令在 build_parser 可见
11. 全量回归 0 新增失败

## 3. 版本与发布

- pyproject `1.1.94` → `1.1.95`; CHANGELOG v1.1.95; 版本断言同步; docs/FEATURES.md;
  docs/sprint10/待办清单-已发现未落地.md: K-5 L20 ✅ + P0-1 L100 ✅ + P0-4 L103 ✅ + P0-5 L104 ✅ +
  C-1 L145 ✅ + C-4 L148 ✅ + C-5 L149 ✅ + C-6 L150 ✅ + H-1 L221 ✅ + F-10 L196 ✅ + M5-7 L77 ✅

## 4. Codex 实施范围

**Allowed/Files**:
- NEW `factory-console/session/eval_suite.py` (EVAL_DIMENSIONS + EvalSuite.run + level)
- NEW `docs/error-codes.md` (M5-7 错误码表)
- NEW `docs/eval-blind-spots.md` 或并入 (C-4 盲区清单)
- MOD `factory-console/cli_factory.py` (factory eval 命令 — 注册表同步)
- NEW `tests/console/test_s10_121_eval_suite.py` (≥10 契约)
- NEW scripts/smoke_longrun.py (长跑冒烟可配置) + 24h 脚本 (标待长跑)
- NEW tests/console/test_s10_121_concurrency.py 或并入 (并发不串 fixture)
- NEW tests/console/test_s10_121_e2e_fullchain.py 或并入 (H-1)
- MOD pyproject.toml / CHANGELOG.md / 版本断言 / docs/FEATURES.md / docs/sprint10/待办清单-已发现未落地.md

**Forbidden（硬边界）**:
- 只做 7 维第一版 + 发布门 + 长跑并发冒烟 + 覆盖度 + 错误码表; 不做 P0-2 故障注入 / P0-3 一致性校验器 /
  P0-6 安全 / P0-7 易用 / P0-8 完整度 / P0-9 信赖 全量 (后续战役)
- 评测 = 跑 + 出报告, 不改业务逻辑 (评测驱动修复 = E-2/E-3 已做, 不并入)
- 长跑/评测零污染真实数据 (临时 workspace); 不调 LLM; 纯确定性
- 发布门不破坏现有版本流程 (四件套同步照旧; --check 默认只读)
- 禁 git add -A; 禁新增第三方依赖 (F-10 用 stdlib trace)

**Validation**:
- `pytest tests/console/test_s10_121_eval_suite.py -q` 全绿
- env -u 聚焦 (cli/session + 既有测试) 全绿
- env -u 全量 console+api 0 新增失败 (并发未提交改动隔离验证)
- 实测: factory eval 报告 7 维; --gate patch/minor 阻断; 并发 trace 隔离; 覆盖度报告; 错误码表
- commit: `feat(S10-121): K-5 评测体系 — 7维评测+发布门+长跑并发+H-1端到端+覆盖度+错误码表, v1.1.95`

## 5. 验收标准（Hermes 独立验证）

- [ ] 1. 七维评测: 每维 ≥1 断言项 + 报告 (L0-L3 判定, 未覆盖如实标)
- [ ] 2. 发布门: --gate patch 跑 L0; --gate minor 跑 L0+L1; 失败明确阻断
- [ ] 3. 并发不串 (trace 隔离) + 长跑冒烟可跑 + 24h 如实标注
- [ ] 4. H-1: 端到端 fixture 每节点衔接断言
- [ ] 5. F-10: 覆盖率报告 (模块级)
- [ ] 6. M5-7: 错误码表 + 主要错误路径有码
- [ ] 7. C-4: 盲区清单
- [ ] 8. 契约测试 ≥10 全绿
- [ ] 9. 全量回归 0 新增失败
- [ ] 10. v1.1.95 + K-5/P0-1/4/5/C-1/4/5/6/H-1/F-10/M5-7 ✅
- [ ] 11. 设计文档落盘

## 6. 诚实记录要求

- 任何维度无法确定性评测 (用户价值/长期) → 如实标注评测口径, 不伪造分数
- 24h 未真跑 → 标"待长跑"; 波及面超预期 → 列出征询
