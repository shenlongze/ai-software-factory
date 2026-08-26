# S10-125 · C-2 产出物契约引擎接线 — 写点枚举 + 改造前后对照（Codex 工程实现记录）

> 日期: 2026-08-26 | Sprint: S10-125 | 交付: C-2 ✅ (引擎写点全部走 `set_artifact`)
> 规格: docs/sprint10/S10-125-c2-plan.md（CTO 设计, 权威）
> ⚠️ 版本: **不 bump 版本文件** — C-2 与 C-3 合并同一版本, 由集成方统一 bump
> 边界: 未碰 fastapi_adapter.py / web/frontend/ / pyproject.toml / CHANGELOG.md /
>   docs/FEATURES.md / 版本断言测试 / artifact_contract.py 本体（只 import）

---

## 1. 写点全量枚举（复核后 — 相对设计 §0 的 12 个, 补全 6 个, 修正 2 个）

`set_artifact` 统一入参（本 Sprint 全部写点）:
`root=<workspace> / project_id=<slug> / producer=<引擎标识> / trace_id=get_trace_id() or None
(K-4 contextvar, 无上下文 → None) / file=<保持现状文件名>; JSON 用 data 传对象,
markdown 用 raw_text 传全文（内容语义零变化, 仅允许合法 JSON 缩进差异）`。
所有 set_artifact 调用包 try/except — 异常 → log + 继续（不阻断引擎, **不写直写回退**）。

### 1.1 actions.py（product pipeline, producer=`product-pipeline`）

| # | 写点 (改造后) | 产出物 | 改造前 | 改造后 | 结果 |
|---|---|---|---|---|---|
| 1 | `create_product` (actions.py:315) | product.json | `product_path.write_text(product.to_json())` | `set_artifact(type=product, data=product.to_dict(), file=product.json)` | ✅ |
| 2 | `generate_prd` (actions.py:530) | PRD.md | `_write_text_file(prd_path, prd_text)` | `set_artifact(type=prd, raw_text=prd_text, file=PRD.md)` | ✅ |
| 3 | `generate_prd` (actions.py:540) | product.json (合并) | `_write_json_file(product_file, {**existing, **product_dict})` | `set_artifact(type=product, data={**existing, **product_dict}, file=product.json)` | ✅ |
| 12→ | `prepare_project` (actions.py:649-696) | PRD.md + engineering.json + tasks.json + execution_plan.json + product.json | `_write_text_file/_write_json_file` ×5 | `set_artifact(type=prd/engineering/tasks/execution_plan/product)` | ✅ 补全 |
| 补 | `rename_project` (actions.py:3882) | product.json (名称同步) | `pfile.write_text(json.dumps(pdata))` | `set_artifact(type=product, data=pdata, file=product.json)` | ✅ 补全 |
| 4 | `_write_plan_quality_files` (actions.py:654) | PRD.quality.json / engineering.quality.json | `_write_json_file` ×2 | **未改造** — 契约能力缺口, 见 §3 | ⚠️ 记录 |

### 1.2 orchestrator.py（执行编排, producer=`orchestrator`）

| # | 写点 (改造后) | 产出物 | 改造前 | 改造后 | 结果 |
|---|---|---|---|---|---|
| 5 | `_save_state` (orchestrator.py:1067) | execution_state.json | `state.save(self._state_file(project_dir))` → `_write_json` | `set_artifact(type=execution_state, data=state.to_dict(), file=execution_state.json)` | ✅ |
| 6 | `_insert_tasks` (orchestrator.py:4087, replan 同步) | tasks.json (存在才写) | `_write_json(tasks_file, data)` | `set_artifact(type=tasks, data=data, file=tasks.json)` | ✅ |
| 7 | `_bump_plan` (orchestrator.py:4124) | execution_plan.json | `_write_json(project_dir/"execution_plan.json", plan)` | `set_artifact(type=execution_plan, data=plan, file=execution_plan.json)` | ✅ |

> 注: 写点 5 改在 `_save_state`（唯一生产写入口, 全部 ~27 处状态落盘收敛）
> 而非 `ExecutionState.save` 方法本体 — `save` 是测试/工具直写点（任意路径,
> 保留原语义）。设计 §0 行号 304 映射的正是 `_save_state` 汇聚面。

### 1.3 change_control.py（变更回流, producer=`change-control`）

| # | 写点 (改造后) | 产出物 | 改造前 | 改造后 | 结果 |
|---|---|---|---|---|---|
| 9 | `_append_prd_v2` (change_control.py:547) | PRD.md (追加场景) | 读全文+合并 → `_write_text(prd_path, updated)` | 读全文+合并 → **整体** `set_artifact(type=prd, raw_text=updated, file=PRD.md)`（归档旧版=历史不丢; 禁止绕过契约 append） | ✅ |
| 10 | `_merge_tasks` (change_control.py:640) | tasks.json | `_write_json(tasks_path, tasks_data)` | `set_artifact(type=tasks, data=tasks_data, file=tasks.json)` | ✅ |
| 补 | `_merge_plan` (change_control.py:691) | plan.json | `_write_json(plan_path, plan_data)` | `set_artifact(type=plan, data=plan_data, file=plan.json)` | ✅ 补全 |
| 补 | `_merge_execution_plan` (change_control.py:732) | execution_plan.json | `_write_json(plan_path, plan_data)` | `set_artifact(type=execution_plan, data=plan_data, file=execution_plan.json)` | ✅ 补全 |
| 8→ | `_save_proposals` (change_control.py:301) | change_control.json | `_write_json` | **未改造** — 非契约资产（不在 ARTIFACT_SCHEMA, 审计/提案注册表） | ⚪ 不改 |

### 1.4 service.py（写点 11 — 核对结果）

| # | 位置 | 产出物 | 核对结论 | 结果 |
|---|---|---|---|---|
| 11 | service.py:1726 (confirm 流程) | product.json | **非直写**: `product_file=new_dir/"product.json"` 仅作为参数传给 `lifecycle_store.set_project_lifecycle`（J-1 统一入口）。service.py 自身无任何标准产出物直写（仅 project.json/discovery/*/org 镜像, 均非契约资产） | ⚪ 无需改动 |

---

## 2. 设计 §0 12 个写点的复核结论

- #1/#2/#3/#5/#6/#7/#9/#10: 确认并完成改造 ✅
- #4: 契约能力缺口（文件名 ≠ schema quality.json; 双文件共享单一 quality 槽位）→ 记录, 不扩契约 ⚠️
- #8: 行 260 实为 `_save_proposals` → change_control.json（非契约资产）; tasks/plan 真实写点为 588/631/664 → 已全部改造 ✅
- #11: 核对为 lifecycle_store 委托, service.py 无需改动 ⚪
- #12: 行 570 是 `prepare_project` 的 `prd_path` 引用（非写点）; 真实写点为 prepare_project PRD.md（行 649）→ 已改造, 并补全该函数的 engineering/tasks/execution_plan/product ✅

**补全新增写点（设计 §0 未列出, 复核发现）**: prepare_project 的 engineering.json/tasks.json/
execution_plan.json/product.json、rename_project 的 product.json、change_control 的
plan.json/execution_plan.json。

---

## 3. 无法改造点 / 契约能力缺口（给集成方 Codex, C-3/集成时处理）

| # | 位置 | 产出物 | 缺口说明 | 建议 |
|---|---|---|---|---|
| G1 | actions.py `_write_plan_quality_files` | PRD.quality.json + engineering.quality.json | 文件名 ≠ schema `quality.json`; 且**两个质量文件共享单一 quality 槽位**, `set_artifact(type=quality, file=...)` 两次调用会互相覆盖 manifest 条目（第二个覆盖第一个）。契约无法无冲突表示 → 本任务不扩契约, 保持现状直写（已有失败安全 try/except） | 集成方决定: 统一为 quality.json / 或扩展契约支持多质量文件 |
| G2 | session/quality.py `Validator.save` | validation_result.json | 直写（文件不在 C-2 允许清单, 未改造）; memory/extraction.py 只读该文件 | C-3/后续 Sprint 接线 `set_artifact(type=validation)` |
| G3 | session/quality.py `RepairManager` | repair_task.json | 直写（同上, 未改造） | 后续接线 `set_artifact(type=repair)` |
| G4 | session/lifecycle_store.py `set_project_lifecycle` | project.json + product.json + execution_state.json | J-1 统一入口三处同步写, 含 product.json/execution_state.json 镜像（文件不在 C-2 允许清单）; actions/orchestrator/service 均委托它 | 后续评估: 契约与 J-1 生命周期入口的职责划分 |
| G5 | 其余非契约资产（team_report.md / execution_records.json / task_proposals.json / change_control.json / handoff_messages.json / schedule.json / decomposition.json / dependencies.json） | — | 不在 ARTIFACT_SCHEMA, 设计 §0 明确"不改" | 保持现状 |

---

## 4. 验收对照

- [x] 写点枚举文档（本文: 改造前后对照 + 补全 + 缺口）
- [x] 引擎写点走 set_artifact, 4 个改造文件 grep 直写归零（测试 `test_no_direct_write_of_standard_files` 断言）
- [x] 契约测试 + 引擎接线测试全过（tests/console/test_s10_125_c2_contract_wiring.py: 19 passed）
- [x] 回归 0 新增失败（A/B 隔离: 9 个预存失败均与 C-2 无关 — 沙箱 ~/.factory 写权限 /
      真实端口探测 / wheel 构建 / WebUI 并行未提交路由改动）
- [x] 边界遵守: 未碰桥文件 / 版本文件 / artifact_contract 本体
- [x] 诚实记录: 无法改造点见 §3
