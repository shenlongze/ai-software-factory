# ADR-0026 — Phase 9a: Product Intelligence 基础层

> 日期: 2026-08-06 | 状态: Accepted

## 背景

Factory 需要产品侧智能基础: 从 Idea 到 Workflow 的产物可追溯、可审批、可决策。
本阶段交付 Artifact 抽象 / Approval Gate / Product Workflow 骨架 (9b+ 的 Provider
生成与 9d 编排的上游依赖), 独立数据空间 `.factory/product/`, 不发散既有 Core。

## 决策

### 1. Artifact 抽象 (约束 1)
所有产品阶段产物落在统一模型: id/type/content/status/created_by/provider_id/
agent_id/source_events/version/confidence/created_at。本阶段实现 product_idea +
product_decision 两种; version (重生成递增, ≥1) 与 confidence (0-1) 有模型级校验。

### 2. Idea 即 Artifact
create_idea 同步落 ProductIdea + product_idea Artifact (content.idea_id 锚点),
后续 Approval 联动与 Workflow 推导均经此锚点。

### 3. Approval Gate 抽象 (约束 2, 门不绑定类型)
ApprovalGate/ApprovalRequest/ApprovalDecision 三模型; 默认门 (service.DEFAULT_GATES):
prd/ui mandatory (阻塞推进) + architecture recommended; 门 id == artifact_type。
**任何 Artifact 可申请审批**: 类型在默认门 → 自动注册; 否则须 `--gate` 显式指定或
先 save_gate 注册, 直接申请报 "no approval gate" (设计行为, 非 bug — 冒烟链
approval 步骤须带 `--gate prd`)。

### 4. Approval 状态机 (终态不可逆)
pending → approved|denied, 重复 decide 抛 ProductError; granted → approval.granted
+ Product Decision Artifact 落库 (Lineage: provider_id/confidence 继承, source_events
锚定 granted 事件 event_id) + workflow 推进下一 stage + product_decision 回填;
denied → approval.denied + workflow 回 running 停留当前 stage。

### 5. Product Workflow 解耦 (约束 5)
ProductWorkflow = stages 声明链 + current_stage + status; running ↔ awaiting_approval
(approval.required 进入 / granted|denied 退出); completed/failed 为 9d 编排预留。
不绑定 PRD/UI: 门按 Artifact type 匹配。

### 6. Multi-section JSON store (独立空间 + 原子写)
`<root>/product/{ideas,artifacts,approvals,workflows}.json`, `_SECTIONS` 驱动读路径
按节恢复领域对象; 原子写 tmp + os.replace; 损坏 (JSON 解析失败/结构不符/模型校验
失败) → CorruptProductStoreError 响亮失败 (核心目录数据, 非审计增强); store 零顶层
imports events (Removal Isolation)。

### 7. 事件边界 (ADR-0002)
写路径事件服务层发 (source="product"): idea.created / approval.required|granted|
denied / product.workflow.started; 读命令审计 CLI 层发 (source="cli"):
idea.viewed / approval.viewed / product.workflow.status_viewed。EventType 纯增量
枚举扩展, 不改表不破坏既有测试。

### 8. CLI 新顶层命令 (4 触点)
commands.py 延迟导入辅助 (`_open_product_service`/`_product_last_seq`/`_product_errors`)
+ main.py import/分支/`_dispatch_product`/`_print_product`。**`_print_*` 必须传 args
让叶子命令决定事件名** (idea create → idea.created / show → idea.viewed; workflow
start → started / status → status_viewed — 只传顶层子命令会在 create 时印出错误事件名,
实测修正)。退出码: 未找到 7 / 业务错误 1 / 用法 2。**CLI 动词 approve|deny 映射
服务层终态值 approved|denied** (收尾实测: argparse choices 是 approve|deny, 直接透传
会报 "invalid approval decision" — 修 CLI 命令层映射)。

### 9. Dashboard 第十九视图 (6 触点)
models.ProductSnapshot + FactorySnapshot.product (默认空, 零回归) / collector
include_product 默认关 + 失败安全 (未装配/损坏 → 空快照) / views.build_product
(Ideas/Approvals/Workflows 三表) / renderer VIEWS + _SINGLE / cmd_dashboard 仅
`--view product` 延迟导入 ProductStore。**3 处 VIEWS 精确集合断言 18→19 最小化
更新** (test_dashboard_renderer set(VIEWS) 补 "product" / tests/change + tests/
understanding len==19) — 第六犯先例, 行为观察点非 API, 同 ADR-0014/0017/0018/
0019/0020 冲突消解。

### 10. 收尾裁定 (Phase 9a 收尾实测)
- 实现 bug 2 处: (a) `_make_product_decision` 构造 Product Decision Artifact 后
  未 save_artifact 落库 — granted 只回填了 workflow.product_decision id, Artifact
  抽象不完整; (b) CLI decide 直接透传 approve|deny 与服务层 approved|denied 契约
  不符 (见决策 8)。
- 测试 bug 4 处: mkdir autouse fixture 作用域过宽 (污染 test_dir_created_on_first_
  write 逆断言, Phase 8B-2 同款教训 — 局部化到损坏测试类内) / 未知子命令断言错
  (argparse SystemExit(2) 非返回码) / decide 后断言过期 request 对象 (model_copy
  新实例, 须重取) / 连续两次 main() 调用未排空 capsys (JSON 解析混入首命令输出)。
- tests/understanding 断言 VIEWS[-2]=="understanding" 更新为 VIEWS[16] (product
  追加后 provider 才是倒数第二 — 该测试仅断言观察点, 同 ADR-0014 先例)。

## 验证

- pytest 3063 全绿 (2883 + tests/product 180; 含收尾修复)
- 冒烟链: product idea create → approval request --gate prd → approval decide
  approve → workflow start → workflow status (awaiting_approval 联动) →
  dashboard --view product 有数据
- Removal Isolation: 删 product 包 → 模块加载/其余命令/dashboard 其余视图零影响
- Core (factory-core 非 product/dashboard/cli 部分) 零修改
