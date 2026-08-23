# Hermes 提示词 — M3d Sprint 规格（拆解质量评估 + LLM 深度拆解）

> 用途: 三部门循环第 ② 步 — Hermes(CTO) 产出 M3d Sprint 规格，供 Codex(工程) 实现
> 日期: 2026-08-24 | 前置: v1.1.13 · M3 三部曲完成（拆解/关键路径/并行调度）· 全量基线 0 回归

---

【AI Factory M3d Sprint 规格 — 拆解质量评估 + LLM 深度拆解】

## 角色
Hermes = CTO + 架构委员会。产出可执行 Sprint 规格（架构方案 + 评估器/LLM 拆解设计 + 验收标准 + 边界），不写实现代码。

## 当前状态（已确认事实，非自报告）
- 版本: v1.1.13 · M3 三部曲完成: M3a DecomposeEngine（原子叶子）→ M3b CriticalPathEngine（关键路径）→ M3c TaskScheduler（并行调度），全部独立验证 + 用户实测通过
- §3.7.0 诚实短板 2 个（Founder 确认要做）:
  1. **拆解质量评估缺失**（§3.4 📐）: "这个拆解合理吗"无法评分
  2. **LLM 深度拆解未接**: 确定性技术层模板可靠但机械（M3a 仅 llm_fn 注入点，无质量门控）
- 现有设计: §3.4 六维评分表（完整性 25% / 粒度 20% / 依赖正确性 20% / 可行性 15% / 可测性 10% / 风险标注 10%）+ 评分→行动四档（≥0.9 采用 / 0.7-0.9 调整 / 0.5-0.7 重拆 / <0.5 用户澄清）
- 复用地基:
  - `session/decomposer.py` DecomposeEngine（四条件原子判定 + _split_mode 单向推进 + llm_fn 注入点）
  - `session/critical_path.py`（依赖边/关键路径 — 评估依赖正确性的依据）
  - `session/dependencies.py`（环检测/拓扑 — 依赖验证）
  - `session/evidence.py`（证据包 — 评估记录落盘）

## M3d 目标（两块一起做，闭环）
**拆解质量评估 + LLM 深度拆解** — 让"拆解合理吗"可评分，让 LLM 真正理解任务深度拆解，
质量门控兜底。

```
LLM 深度拆解（理解任务语义 → 产出子任务 + 依赖 + 验收 + 估时）
  → DecompositionEvaluator 六维评分（确定性规则 + LLM 辅助）
  → 评分 ≥ 0.9 → 采用 LLM 拆解
  → 0.7-0.9  → 调整后采用
  → < 0.7    → 回退确定性技术层模板（诚实降级, 不伪造 LLM 质量）
```

## 规格必须包含（8 项）
1. **DecompositionEvaluator 接口**: evaluate(decomposition, task, context) → {score, dims{完整性/粒度/依赖/可行性/可测性/风险}, decision: adopt|adjust|reject|ask_user}
2. **六维评分确定性规则**: 每维怎么算（粒度=原子四条件通过率? 完整性=叶子覆盖 core_features? 依赖=环检测+关键路径合理性? 可测性=verify_cmd 覆盖率? 可行性=agent/tool 匹配? 风险=风险标注存在?）
3. **LLM 深度拆解升级**: llm_fn 增强（产出 {tasks, depends_on, verify_cmd, est, risks} 结构, 非简单 list）→ 质量门控 → 达标采用/不达标回退
4. **评分→行动落地**: 四档行动的确定性规则（adjust 改什么/reject 怎么回退/ask_user 返回什么）
5. **与 DecomposeEngine 集成**: 评估器挂哪（decompose 结果后置评估? 还是 _split 内联门控? 最小改动）
6. **契约测试要点**: 六维评分手算对照 / 好拆解采用 / 差拆解回退 / 无 LLM 确定性 / 评估结果落盘可审计 / 向后兼容（M3a 现有拆解不破坏）
7. **Codex 写 scope**: 明确文件清单（新建 evaluator.py? 扩展 decomposer? 最小改动）
8. **边界声明**: 不做 M3-4 动态分配 / 并行线程化 / 质量评估模板库扩展（§3.3 模板库已存在, 本 Sprint 只做评估器+LLM 门控）

## 验收标准（Codex 完成后，你独立验证）
- 六维评分每维可手算对照（构造已知拆解 → 分数一致）
- 好拆解（LLM 精确原子）→ score ≥0.9 → 采用
- 差拆解（LLM 给的还是复合任务）→ score <0.7 → 回退确定性模板（诚实）
- 无 LLM → 确定性拆解 + 评估照常（不因无 LLM 跳过评估）
- 评估结果落盘（decomposition.json 含 evaluation 字段）+ 审计事件
- 向后兼容: M3a 现有拆解流程零变化
- 定向测试全绿 + 全量回归 0 新增失败 + git clean
- 版本: M3d 完成后 bump v1.1.14

## 输出物
- 规格文档: `docs/sprint10/S10-095-m3d-eval-llm-plan.md`
- 供 Codex 的指令摘要（一条可直接执行）

## 关键纪律（写进规格）
1. 代码存在 ≠ 能力；自报告 ≠ 事实 — 你独立验证（评分手算对照）
2. 禁止 stub/fake；LLM 拆解不达标 → 诚实回退确定性（不伪造 LLM 质量）
3. 复用 decomposer / critical_path / dependencies — 不重造、不修改核心
4. 向后兼容: M3a/M3b/M3c 输出与流程不破坏
5. 版本: v1.1.13 → v1.1.14（每次修复 patch+1）
