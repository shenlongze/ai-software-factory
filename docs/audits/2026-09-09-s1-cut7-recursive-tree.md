# S1 第 7 刀 — 递归任务树 (LLM 主导 · 业务/数据逻辑内聚 · 拆到原子)

> Date: 2026-09-09 | 性质: 实施 (只改 task_decomposition.py + 新测试 + 文档)
> 基线: HEAD=dcf6c98e; cut5/cut6 改动 (6 tracked + 3 untracked) 原封未动, 本刀不 commit
> 本文件是防反工记忆: 下个会话读此文件即可续接。

---

## 1. 模型图 (递归树结构)

```
Node (name/scope/atomic/atomic_reason)
 ├─ atomic=false → subtasks: [Node...]   (递归, 深度由复杂度决定, 不写死)
 └─ atomic=true  → 叶 (task):
      business_rule  做什么(业务行为)
      data_entities  动什么数据 [{entity, ops:[read|write|migrate]}]
      change_type    NEW_FILE|MODIFY
      expected_files 单文件/极小文件集 (≤3)
      verify_hint    怎么验 (命令/测试)

kind 按深度: 0=project, 1..n-2=domain/module/capability, 叶=task
护栏: MAX_DEPTH=8 / MAX_NODES=100 (超限 → 强制收叶/截断 + degraded)
```

## 2. 关键决策

1. **组织原则内建** (提示词 + 校验器, 非口号):
   - A 业务内聚: 下单/支付/状态流转同"订单"子树 (提示词强约束; 测试断言 parent 链)。
   - B 数据所有权: 叶声明 data_entities+ops; 两叶写同一 expected_file → 校验器
     `_serialize_file_deps` 自动注入 depends_on 串行; 成环 → 拒绝该边 + degraded。
2. **LLM 输出截断 → 部分解析**: DeepSeek 长递归树输出被截 (未配平 JSON)。
   `_try_partial_json` 从闭合边界截断 + 补闭合括号, 保留最大可恢复前缀
   (已给完整子树), degraded=True + warning "LLM 输出截断" (诚实, 不整棵丢)。
   实测真实 LLM 电商: 截断仍出 depth=4 部分树。
3. **旧格式兼容**: {domains:[{title,tasks}]} (S1-2 平铺) 归一化为递归同构;
   task-like dict (无 atomic/subtasks 含 title/change_type) → 视为叶。模板路径行为不变。
4. **复用 decomposer 资产**: 引用 session/decomposer 原子判定思路与 cycle 拒绝语义
   (不实例化 legacy 类, 不删不改它)。
5. tree_summary.depth 动态算 (遍历 parent 链), 不再写死 3。

## 3. 验收对照

- A ✅ 小任务 (番茄钟 fake LLM) → 2-3 层, degraded=False, 叶带 verify_hint
  (test_timer_2_3_levels)。
- B ✅ 电商后台 (fake LLM 4 层 JSON) →
  · depth≥4 (test_depth_ge_4: 实际 4);
  · 业务不撕: 下单/支付/状态流转 同"订单"祖先 (test_business_chain_not_torn);
  · 数据强制: 两叶写同一 order.js → 校验器注入 depends_on (test_same_file_write_gets_serialized)。
- C ✅ 诚实降级: LLM 失败/非法 JSON/截断 → degraded=True 非空 (模板兜底形状 /
  部分树保留)。atomic=false 无 subtasks → 强制收叶 + warnings。
- D ✅ Plan.tasks == 全部叶 (test_plan_tasks_equals_leaves); golden_path e2e +
  execution_semantics_s2 全绿 (执行链未破)。
- E ✅ test_task_decomposition 8 个全绿 (模板路径未动)。
- F ✅ 真实 LLM 冒烟 (DEEPSEEK): 电商后台 → **depth=4, decomposer=llm**, 叶带
  business_rule/data_entities (products/users/sessions 表); 输出截断被部分解析
  兜住 → degraded=True + warning (诚实)。

## 4. 真实 LLM 冒烟证据 (F)

```
depth: 4 | degraded: True | leaves: 7 | nodes: 14
decomposer: llm | warnings: ['LLM 输出截断 → 部分解析 (树可能不完整)']
  定义商品Schema并实现建库脚本   | rule: 创建商品数据表 products...   | ents: products表
  商品CRUD业务逻辑与接口实现      | rule: 封装商品数据操作接口...       | ents: products表
  查询单个商品价格与库存接口      | rule: 实现 GET /products/{id}...    | ents: products表
  用户账户创建与登录令牌签署      | rule: 提供用户注册与登录功能...     | ents: users表,sessions表
  用户信息查询(供订单/支付模块)  | rule: 实现 GET /users/{id}...       | ents: users表
```

## 5. 测试与回归

- test_recursive_decomposition_s2.py: 9 passed (A 1 / B 3 / C 4 / D 1)
- test_task_decomposition.py: 8 passed (模板路径回归)
- 全组: 155 passed (18 文件, 第 1-7 刀相关全绿)
- ruff: task_decomposition.py + 新测试 All checks passed

## 6. 改动文件

- factory-console/task_decomposition.py (唯一代码改动: 递归解析 + 校验器 + 截断恢复)
- tests/console/test_recursive_decomposition_s2.py (新)
- docs/audits/2026-09-09-s1-cut7-recursive-tree.md (本文档)

## 7. 遗留/后续

- LLM 输出截断频发 (大递归树超输出预算) → 可加: 提示词要求更紧凑/分批; 或 llm_raw
  长度上限放宽。当前部分解析已兜住, 但截断树 degraded=True (执行仍可用, 但树不全)。
- 中间层节点 (domain/module/capability) 语义未严格区分 (按深度轮转 kind);
  后续可让 LLM 每层给 kind 或完全省略 kind 由深度推导 (当前实现)。

---
*本刀不 commit (用户要求第 5-7 刀一次性 PR)。工作区: cut5/cut6 改动原封未动。*
