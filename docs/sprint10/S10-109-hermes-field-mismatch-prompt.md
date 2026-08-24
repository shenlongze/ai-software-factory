# S10-109 Hermes 提示词 — 需求分析字段错位修复（T9）

> 用途: 复制给 Hermes，让它独立分析根因 → 派 Codex 实现 → 独立验收。
> 对应测试用例: `docs/sprint10/S10-108-需求分析-PRD-测试用例.md` 用例 **T9**。

---

## 任务标题
**S10-109 需求分析字段错位修复（答非所问被强填当前字段 + "可以"被当字段值）**

## 背景（Founder 实测复现, v1.1.47）

产品发现阶段，用户回答"答非所问"时，内容被**无条件填到当前待填字段**，导致字段错位。两次独立实测稳定复现：

```
> 我想做个记账App
> 给大学生用                ← 问"痛点"时，用户答的是"目标用户"
> 支持扫码记账和月度报表      ← 用户提前答"核心功能"
> 可以                      ← 用户确认意图

实际输出（确认门）:
问题: 给大学生用               ❌ 应为"目标用户"
目标用户: 支持扫码记账和月度报表  ❌ 应为"核心功能"
核心功能: 可以                 ❌ "可以"被当字段值
```

另一个复现（markdown 编辑器）: 答"给普通用户用"→problem、"支持实时预览和导出PDF"→user，同样错位。

## 根因（Codex 定位, 请你独立复核）

`factory-console/session/conversation.py` → `handle_product_answer` → LLM 分流
`_handle_llm_analysis` → `_apply_field_answer`:

```python
field = self._product_pending[0]
self._set_product_field(field, text)   # ← 无条件强填当前字段, 无语义校验
```

即: LLM 把回答分类为 `field_answer` 后，**按当前待填字段直接填入**，不做
"这段内容到底属于哪个字段"的语义判断。用户答非所问 / 提前答后续字段 /
输入确认词，都会污染当前字段。

## 修复规格（建议方案, 可优化）

**目标**: 填字段前做**确定性内容匹配校验**（不依赖 LLM，无 LLM 也生效），答非所问
时智能归类到匹配字段；确认词不当字段值。

1. **内容匹配规则**（conversation.py, 模块级常量 + 函数, 可单测）:
   - `user` 模式: `给.*用 / 面向.* / .*用户 / .*人群 / .*学生 / .*白领 / .*开发者` 等
   - `core_features` 模式: `支持.* / 可以.* / 能.* / .*功能 / .*报表 / .*记录` 等
   - `problem` 模式: `解决.* / .*麻烦 / .*痛 / .*难 / .*不便` 等
   - 命中**非当前字段**的模式 → 填到匹配字段（若该字段未填）; 多个命中 → 优先级
     user > core_features > problem（或取最高置信）
2. **确认词不当字段值**: text 为确认词（可以/好/行/ok/y/yes, 复用 discovery_guide
   确认词表）且当前字段未填 → 不填字段, 明确提示"产品定义还不完整, 还缺 X, 请先补充"
   （若必填已齐 → 正常进确认, 但必填齐不会走到 field_answer, 防御即可）
3. **兜底**: 未命中任何模式 → 保持现状（填当前字段, 兼容正常回答）
4. **可选（若实现简单）**: LLM 分析时输出回答归属字段, 规则优先、LLM 补充

**边界**: 只改发现阶段字段填充; 不动确认门/PRD 生成/其他 Action/CLI/board。

## 范围声明（硬边界, 必须遵守）

- ✅ 只改: `factory-console/session/conversation.py`（字段填充逻辑）+ 对应契约测试
- ❌ 不改: 确认门(handle_product_confirm)、PRD 生成(actions.py)、调度、CLI 命令、board
- ❌ 不扩展: 不加新命令、不加新字段、不改产品数据模型
- ❌ 不影响: 正常回答路径（答对字段时行为逐字节不变）、无 LLM 兜底、批量模式
- 统一修改: 修复 + 契约测试 + CHANGELOG + 版本断言 + CAPABILITY_MATRIX（如需）同 Sprint

## 验收标准（Hermes 独立验证, 非 Codex 自报告）

1. **T9 复现脚本 → 修复后字段正确**:
   - 问痛点时答"给大学生用" → user="给大学生用"（非 problem）
   - 答"支持扫码记账和月度报表" → core_features 含"扫码记账""月度报表"（非 user）
   - 答"可以"（字段未齐）→ core_features 不被填"可以", 提示还缺字段
2. **正常回答零变化**: 答对字段（如问 user 答"给大学生用"）→ 行为与 v1.1.47 一致
3. **无 LLM 兜底同生效**: `env -u DEEPSEEK_API_KEY` → 规则路径同样不错位
4. **契约测试**: 新增 ≥3（答非所问归类 / 确认词不当值 / 正常回答不变）
5. **全量回归**: 0 新增失败（重点: test_discovery_*、test_confirmation_intelligence、
   test_session_pipeline、test_session_ux_blockers）
6. **版本**: v1.1.48（pyproject + 断言 + CHANGELOG + FEATURES 同步）

## Codex 指令摘要（可嵌入 Hermes 派单）

> 修复 factory-console/session/conversation.py 的 _apply_field_answer 字段错位:
> 填字段前加确定性内容匹配（user/core_features/problem 模式 + 确认词识别）,
> 答非所问智能归类、确认词不当字段值; 正常回答零变化; 补契约测试;
> 全量回归 0 失败; v1.1.48。不乱改、不扩展、不影响其他功能。

## 诚实纪律

- 修复后如实报告: 哪些场景修好、哪些边界保留（如 LLM 分类仍可能误判 → 如实标注）
- 无 LLM / LLM 失败时规则兜底必须真实生效（不许伪造"修复成功"）
- 若内容匹配规则引入误伤（把正常回答错判到别的字段）→ 必须报告并收敛规则
