# Sprint 5 / T5.4 — Model Capability Registry（Completion Report）

> 日期: 2026-08-08 | 状态: 完成
> 目标: 声明式模型能力评分 (0-1 × 7) + 注册表 (JSON 原子写) + Candidate 能力快照 (历史可解释) + Experience 统计 (禁自动改分)
> 设计依据: docs/validation/sprint5-t51-execution-strategy-design.md §5/§6 (T5.1 冻结)
> 约束: 不跑真实 Benchmark / 不自动选模型 / 不改执行流程; Core/Runtime/Desktop = 0; 不落数据库

## 完成内容

```
① ModelCapability (factory-exec/exec/capability.py 新建)
   provider/model 必填 (空白拒绝) + 七项能力评分 (0-1 声明式):
   coding_score / reasoning_score / stability_score / context_score /
   tool_use_score / cost_score / latency_score
   - 校验: 0-1 clamp (越界钳制, 非法输入 → 0.0 中性, 不臆造); extra=forbid
   - 序列化: to_dict (JSON 友好) / from_dict (round-trip 兼容)
   - 通用: 不绑定具体模型 — 内置示例 (deepseek-v4-flash/pro) 是数据文件,
     非代码 (exec/config/model_capabilities.json 声明式配置)

② CapabilityRegistry
   register (唯一评分写入口, upsert 刷新 updated_at 保留 created_at) /
   get / list (排序) / find_by_capability(capability, min_score) /
   remove / count / has
   - 本地存储: JSON 单文件原子写 (tmp + os.replace, 禁数据库);
     损坏 → 空表失败安全, 单条坏 → 跳过 (审计增强数据不破坏执行链)
   - find_by_capability: 评分 ≥ min_score 降序返回; 未知能力名 → ValueError
     (拼写错误即失败); min_score clamp [0,1]
   - seed_defaults(): 灌入内置示例配置 (已有条目不覆盖, 防示例覆盖用户数据;
     force=True 强制)

③ Benchmark Integration (model_capability_snapshot)
   ExecutionCandidate 新增 model_capability_snapshot 字段
   ({"provider","model","scores","captured_at"}) — 候选保存时冻结 registry
   中该模型当前评分; 模型能力后续变化不影响历史候选 (历史结果可解释);
   无 registry / 无该模型 → {} 中性 (不臆造)
   - 接入: candidate_from_result(capability_registry=...) +
     SequentialRunner(capability_registry=...) — 全可选参数, 缺省 None
     行为逐位不变 (不改执行流程); 异常 Run 失败候选同样带快照

④ Experience Integration (ModelExperienceStats)
   成功/失败计数 + 按任务类型细分成功率 (如: 该模型在此任务类型的成功率)
   - record_candidate(): ExecutionCandidate 喂入 (复用 experience_ctx 词汇:
     candidate.to_experience_signals 同源); record_candidates 批量
   - 只统计不评分: 能力评分唯一写入口 = CapabilityRegistry.register
     (人工/Benchmark 更新, 第一阶段) — 测试强断言: 喂任意多失败/成功,
     注册表评分逐位不变; 统计类无任何注册表写 API
   - 复用 experience_ctx (T4.4) 语义, 不重复建库 (内存计数 + 可序列化
     to_dict/from_dict 随审计输出落盘)
```

## 设计要点 (可解释性)

```
快照 vs 评分分离:
  评分 (registry) = 当前事实, 唯一写入口 register (人工/Benchmark)
  快照 (candidate) = 历史冻结, 保存时捕获 — 复盘历史结果不受评分漂移污染
  统计 (stats)    = 事实计数, 只增不改分 — 第一阶段不自动调评分

内置示例配置 (声明式 JSON, 数据不硬编码到代码; T5.1 §5 语义):
  deepseek-v4-flash: coding 0.6 / reasoning 0.8 / stability 0.3 (reasoning
    耗尽风险 — Sprint 4 实测 7/9 空响应的诊断语义) / context 0.7 /
    tool_use 0.5 / cost 0.9 (便宜) / latency 0.8
  deepseek-v4-pro:   coding 0.7 / reasoning 0.9 / stability 0.5 / context 0.8 /
    tool_use 0.6 / cost 0.7 / latency 0.6
  查询示例: find_by_capability("cost_score", 0.85) → [flash];
            find_by_capability("stability_score", 0.4) → [pro]
```

## 测试

```
Unit 78 (tests/exec/test_exec_capability.py):
  ModelCapability 创建/必填/空白拒绝/clamp (高/低/全部/非法/None/边界)/
  extra=forbid/round-trip/JSON 友好/scores 属性/score() 单项查询 (13+)
  Registry CRUD (register dict/upsert/created_at 保留/list 排序/count/remove) (11)
  find_by_capability (命中/阈值/降序/未知名 ValueError/min_score clamp) (6)
  持久化 (save→reload/原子写无 tmp 残留/损坏失败安全/单条坏跳过/缺文件/
  非 list 根/覆盖/删除落盘) (8)
  内置示例配置 (文件存在/声明式加载/flash 评分/缺失损坏失败安全/seed 不覆盖/
  seed force/seed 落盘) (9)
  快照 (已知/未知 {} /registry None {}/duck-typed 无方法 {}/冻结) (5)
  ModelExperienceStats (记录/成功率/无样本 None/按任务类型/汇总/总量/
  keys 排序/空 model 跳过/round-trip/非法计数钳制/record_candidate/批量) (12)
  禁自动改分强断言 (record 不改分/50 失败不改分/无注册表写 API/仅 register
  改分/快照无副作用/key 工具) (6)
Integration 16 (tests/exec/test_exec_capability_integration.py):
  Runner 级快照 (捕获/未知模型 {}/无 registry {}/注册表变更后历史冻结/
  异常 Run 失败候选带快照) (5)
  candidate_from_result 直连快照 / 序列化 round-trip 保留快照 (2)
  Experience 集成 (Runner 统计/按任务类型/全闭环禁自动改分/统计序列化) (4)
  Registry 端到端 (seed 落盘重载/find_by_capability 查询/快照→候选→评估全链/
  信号词汇回归/统计与 registry 解耦) (5)
pytest 全量: 5399 + 94 = 5493 passed  — Core/Runtime/Desktop diff = 0
```

## Commits

```
<commit-1> T5.4 ① ModelCapability + CapabilityRegistry 核心 (Unit 78)
<commit-2> T5.4 ② Candidate 快照 + Experience 统计接线 (Integration 16)
<commit-3> T5.4 ③ Completion Report
```

## 文件变化

```
factory-exec/exec/capability.py                        (新建: ModelCapability + Registry +
                                                        capability_snapshot + ModelExperienceStats)
factory-exec/exec/config/model_capabilities.json       (新建: 内置示例能力配置, 声明式数据)
factory-exec/exec/candidate.py                         (扩展: model_capability_snapshot 字段 +
                                                        candidate_from_result/SequentialRunner 可选接线)
tests/exec/test_exec_capability.py                     (新建, Unit 78)
tests/exec/test_exec_capability_integration.py         (新建, Integration 16)
docs/validation/sprint5-t54-model-capability-report.md (本报告)
```

## 约束遵守

```
✅ 禁真实 Benchmark / 禁自动模型选择 / 禁 Provider 切换 / 不改执行流程
   (接入点全为可选参数, 缺省 None 行为逐位不变; 旧测试零破坏)
✅ Core/Runtime/Desktop = 0 (git diff 验证)
✅ 禁自动改分 (评分唯一写入口 register; 统计类强断言无写 API)
✅ 禁数据库 (JSON 单文件原子写) / 不删测试 / basename 唯一 / 诚实 (无数据 → {} 中性)
✅ 复用 experience_ctx (T4.4) 词汇, 不重复建库
```

## 下一步建议 (T5.5 — Benchmark V3)

```
1. Benchmark V3 设计 (9 样本 × runs N, Feature Flag 开启):
   - 每条 Run 产 Candidate (带 model_capability_snapshot) → 评估选 Best →
     Experience 统计 (ModelExperienceStats) 喂入每模型每任务类型成功率
   - 目标: Bug Fix ≥60% + 连续运行稳定性; 用统计对比 N=1 vs N=3 的边际收益
     (成本 ×3 是否换回成功率 — T5.1 §2 假设的真实验证)
2. Benchmark 数据 → 能力评分更新闭环 (第二阶段):
   - 统计成熟后 (样本量阈值) 才允许 register() 更新评分 — 第一阶段保持
     人工/声明式, 评分与统计分离可审计
3. 产线接线: AgentRuntime 装配 CapabilityRegistry + ModelExperienceStats
   (当前 SequentialRunner 已预留参数, 产线未接 — 不改变执行流程)
4. find_by_capability → 数据驱动选择建议 (任务类型 × 能力匹配, 仅建议不
   自动切换 — Provider 切换仍禁)
```
