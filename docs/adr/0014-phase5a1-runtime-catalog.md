# ADR-0014 — Phase 5A.1: Runtime Catalog (能力目录层)

> 日期: 2026-08-06 | 状态: Accepted

## 背景

Phase 5A 引入 Runtime 能力描述需求: 工厂需统一描述"有哪些 Runtime、各自能力如何",
而既有 runtime/ 层只管理**实例可用状态** (Registry) 与**执行器** (Adapter), 没有能力
目录。设计文档 phase5a1-status.md 明确三层分离: **Catalog=能力描述, Registry=实例可用
状态, Runtime=执行器**; 现有 runtime store 用 `<root>/runtimes/runtimes.json` (实例 +
executions), Catalog 必须独立文件避免冲突。

## 决策

### 1. 独立 runtimes 包 + 独立存储文件
factory-core/runtimes/ (models/catalog/store/definitions) 为 Catalog 层新包; 持久化到
`<root>/runtimes/catalog.json` (原子写), 与实例库 runtimes.json 完全独立 — Catalog 写路径
不产生/不修改 runtimes.json (测试 test_catalog_does_not_touch_registry_store 强制)。

### 2. 三层分离, Catalog 不派发不执行
RuntimeDefinition 只描述能力 (id/name/type/description/capabilities/supported_tasks/
version/status/metadata), RuntimeCatalog 只做 register/get/list/remove/find_by_capability;
无 execute 方法 (测试 test_catalog_does_not_execute 强制)。执行器选择仍是 Registry +
Adapter 的职责; 只读路径经 catalog 查 definition, 不复制状态。

### 3. 读路径合并: 默认定义基线 + 持久化定义
默认定义 hermes/echo/mock (definitions.py, 只描述不执行) 是内建基线; get/list/
find_by_capability/count/ids 看合并视图 (按 id 排序), 已持久化定义按 id 覆盖默认值 —
空 store 也可见 3 个默认定义。

### 4. 内建定义只读
register 在合并视图已存在 (默认 id 保留 + 持久化重复) → RuntimeDefinitionExistsError;
remove 只删持久化记录, 内建默认定义不可移除 → RuntimeCatalogError。默认 id 不可覆盖注册。

### 5. 事件扩展: runtime.catalog.* 三事件
扩 str-Enum EventType 成员 (纯增量, type 列存字符串, 不改表): runtime.catalog.registered
(register) / runtime.catalog.removed (remove) / runtime.catalog.viewed (CLI list/show 与
dashboard 只读查看)。写方法返回 `(对象, Event | None)` 元组 (参照 runtime/registry.py 模式:
Event 经 EventLogger 发, logger 可缺省; 存储先落地、事件后发, 事件失败不回滚已落盘 JSON)。

### 6. CLI 只读子命令 + Dashboard 视图
`factory runtime catalog list|show` (发 runtime.catalog.viewed; show 未找到 → 退出码 7);
`factory dashboard --view catalog` 为第七视图 (Runtime Catalog 面板, 只读不写不发事件)。

### 7. 列表字段 None 归一化为 []
capabilities/supported_tasks 校验器用 Pydantic v2 mode="before" — None 输入归一化为 [],
与缺省默认行为一致 (Pydantic list[str] 类型检查会先于普通 after-validator 拒绝 None)。

## 验证

- pytest 1335 全绿 (1332 + 3 修复回归)
- 冒烟: runtime catalog list (3 默认定义) / show hermes (详情) / show nope (rc 7) /
  dashboard --view catalog (Runtime Catalog 面板) 均正常
