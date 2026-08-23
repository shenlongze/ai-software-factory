# S10-095 M3d — 拆解质量评估 + LLM 深度拆解 Sprint 规格

> 日期: 2026-08-24 | Hermes CTO → Codex | 目标 v1.1.14 | 两块闭环
> 前提: M3 三部曲完成(v1.1.13) · §3.4 六维评分设计(25/20/20/15/10/10 + 四档行动)

---

## 0. 现状核验(已确认)

- `decomposer.py` DecomposeEngine: 四条件原子判定 + _split_mode 单向推进 + llm_fn 注入点(378)
- `critical_path.py` / `dependencies.py`: 依赖边/环检测/拓扑(依赖正确性评估依据)
- `evidence.py`: 证据包(评估记录落盘)
- **缺口**: 无 DecompositionEvaluator(质量门控缺失); LLM 拆解产出无结构化质量验证

## 1. Evaluator 接口

```
模块: session/decomposition_evaluator.py (新建)

class DecompositionEvaluator:
    def evaluate(self, decomposition: dict, task: dict, context: dict) -> EvalResult
        # 输入: decomposition {tasks[], depends_on, verify_cmd, est, risks?}
        #       task {id,name,requirement,core_features?} + context {capabilities, product}
        # 输出: EvalResult {
        #   score: float (0-1)
        #   dims: {完整性, 粒度, 依赖, 可行性, 可测性, 风险}  # 各 0-1
        #   decision: adopt | adjust | reject | ask_user
        #   reasons: [str]  # 每维失分原因
        # }

    def _score_completeness / _score_granularity / _score_deps / _score_feasibility / _score_testability / _score_risk
```

## 2. 六维确定性规则(每维怎么算)

| 维 | 权重 | 确定性规则 |
|---|---|---|
| 完整性 | 25% | 叶子任务覆盖 core_features 比例(缺失 feature → 失分) |
| 粒度 | 20% | 原子四条件通过率(单Agent/单文件/可验证/≤10min 每条件 0.25) |
| 依赖 | 20% | 环检测(cycle_detect 通过=1, 环=0) + 关键路径合理性(无死节点) |
| 可行性 | 15% | agent_type ∈ capabilities / tool 匹配(不可用 agent → 失分) |
| 可测性 | 10% | verify_cmd 覆盖率(有 verify 的叶子比例) |
| 风险 | 10% | risks 标注存在(每个复合/高风险叶子有 risks → 满分; 无 → 0) |

score = Σ(维度分 × 权重)。

## 3. LLM 深度拆解升级

```
llm_fn 增强: 产出结构化 {tasks: [{id,name,requirement,depends_on,verify_cmd,est,risks}], summary}
  → 非简单 list → 进入质量门控 evaluate()
  → LLM 失败/无 LLM → 确定性技术层模板(现有路径, 不伪造)
```

## 4. 四档行动落地

```
adopt  (≥0.9): 采用 LLM 拆解 → 返回 decomposition
adjust (0.7-0.9): 自动修正 → 缺失 feature 补齐 / verify_cmd 补默认 / 依赖环修剪 → 修正后采用(标注 adjusted)
reject (<0.7): 回退确定性技术层模板(诚实降级, 不伪造 LLM 质量)
ask_user (<0.5): 返回问询 {questions: [缺失信息]} → 用户补充后重评 (REPL 层处理)
```

## 5. 与 DecomposeEngine 集成(最小改动)

```
方案: 后置评估(推荐) — decompose() 产出 leaves 后 → evaluator.evaluate()
  - 侵入最小(不动 _split 内部)
  - LLM 深度拆解路径: llm_fn 结构产出 → evaluate → 四档行动
  - 无 LLM: 确定性 leaves → evaluate(照常评分, 不跳过) → 结果落盘
```

## 6. 契约测试(六维手算对照)

```
tests/console/test_m3d_evaluator.py:
1. 六维手算: 构造已知拆分 → 每维分可断言 (如 4 叶子全单文件全verify → 粒度=1.0)
2. 好拆解: 评分≥0.9 → adopt
3. 差拆解: <0.7 → reject(回退确定性)
4. 无 LLM: 确定性 leaves 照常评估(不跳过)
5. 落盘: evaluation 字段(score/dims/decision)进 evidence + 审计
6. 向后兼容: M3a decompose 零变化(评估器可选)
```

## 7. Codex Scope

| 文件 | 动作 |
|---|---|
| `factory-console/session/decomposition_evaluator.py` | ★新建(六维评分 + 四档行动) |
| `factory-console/session/decomposer.py` | 最小: decompose 后置调 evaluator(可注入, 默认开) + llm_fn 结构产出支持 |
| `factory-console/session/evidence.py` | 最小: evaluation 字段落盘(或 metadata) |
| `factory-console/audit/audit_event.py` | 新增 2 事件: EVAL_COMPLETED / EVAL_REJECTED_FALLBACK |
| `tests/console/test_m3d_evaluator.py` | ★新建 |
| 版本文件 | → v1.1.14 |

## 8. 边界(不做)

- ❌ M3-4 动态 Agent 分配
- ❌ 并行执行线程化
- ❌ 模板库扩展
- ✅ 向后兼容: M3a decompose 零变化(评估器可选注入)

## 验收标准(Hermes 独立验证, 评分手算对照)

```
1. 六维可手算(构造已知拆分 → 各维分可断言)
2. 好拆解 ≥0.9 → adopt
3. 差拆解 <0.7 → 诚实回退确定性模板
4. 无 LLM → 照常评估(不跳过)
5. evaluation 字段落盘(evidence + 审计事件)
6. M3a 零变化 + 全量回归 0 新增 + git clean + v1.1.14
```

---

# Codex 指令摘要(一条可直接执行)

```
你是 AI Factory Senior Engineer。实现 M3d 拆解质量评估 + LLM 深度拆解:
1) 新建 factory-console/session/decomposition_evaluator.py — DecompositionEvaluator.evaluate(decomposition, task, context) → {score, dims{完整性25/粒度20/依赖20/可行性15/可测性10/风险10}, decision: adopt|adjust|reject|ask_user, reasons}; 六维确定性规则(完整性=core_features覆盖/粒度=四条件通过率/依赖=cycle_detect+关键路径/可行性=agent∈capabilities/可测性=verify_cmd覆盖/风险=risks标注存在); score=Σ(维×权重)。
2) 四档行动: ≥0.9 adopt; 0.7-0.9 adjust(补feature/补verify/修剪环 → 标注 adjusted); <0.7 reject(回退确定性技术层模板, 诚实不伪造); <0.5 ask_user(questions 返回)。
3) decomposer.py 最小集成: decompose 后置评估(可注入, 默认开); llm_fn 产出结构化 {tasks[{id,name,requirement,depends_on,verify_cmd,est,risks}]} → 质量门控; 无 LLM → 确定性 leaves 照常评估。
4) 落盘: evaluation(score/dims/decision)进 evidence + 审计 2 事件 EVAL_COMPLETED/EVAL_REJECTED_FALLBACK。
5) 测试 tests/console/test_m3d_evaluator.py: 六维手算对照/好拆解adopt/差拆解reject回退/无LLM照常/落盘/向后兼容。
6) 版本 1.1.13→1.1.14 同步 pyproject/install.sh/docs/CHANGELOG/版本断言。
7) 全量回归 0 failed (runtime flaky 除外)。Completion Report: 修改文件/测试/六维手算对照表/风险/下一步。
禁止: stub/fake, 超前范围 (M3-4动态分配/并行线程化/模板库扩展不做), M3a decompose 行为零变化。
```

规格: docs/sprint10/S10-095-m3d-evaluator-plan.md
