# S10-109 — 需求分析字段错位修复（T9）：实现计划（CTO 架构设计 + Codex 指令）

> 日期: 2026-08-24 | 前置: v1.1.47 · S10-108 已标注字段错位 bug
> 用途: 三部门循环第 ②→③ 步 — Hermes(CTO) 架构设计 → Codex(工程) 实现
> 规格来源: docs/sprint10/S10-109 提示词（T9, Founder 实测复现）

---

## 0. 现状审计（CTO 独立复核 — 非 Codex 自报告）

**Bug 复现（v1.1.47, 我的脚本）**:
```
我想做个记账App → 给大学生用 → 支持扫码记账和月度报表 → 可以
确认门: problem='给大学生用' ❌ | user='支持扫码记账和月度报表' ❌ | core_features=['可以'] ❌
```

**根因确认**: `conversation.py _apply_field_answer` (L782-784):
```python
field = self._product_pending[0]
self._set_product_field(field, text)   # ← 无条件强填当前字段
```
机械路径同样: L575-576 (批量) / L585-586 (单字段) 无条件填当前字段。
LLM 分类为 field_answer 后无"内容归属字段"语义校验; 答非所问/提前答/确认词 → 污染当前字段。

**可复用**: discovery_guide.APPROVE_WORDS (确认词表, L134) · FIELD_LABELS (字段中文名) · parse_core_features。
**同步点**: pyproject 1.1.47→1.1.48 · CHANGELOG · 版本断言 (test_s10_074_deployment 等) · **docs/FEATURES.md** (头版本 v1.1.47, L5)。
**测试面**: test_discovery_* / test_confirmation_intelligence / test_session_pipeline / test_session_ux_blockers 存在。

## 1. 架构决策：确定性字段归属判定（不依赖 LLM, 两路径共用）

### 1.1 模块级模式表 + 解析函数（conversation.py, 可单测）

```python
#: 字段内容模式 (确定性归类 — 答非所问智能填匹配字段; 模块级常量)
_FIELD_PATTERNS: dict[str, tuple[str, ...]] = {
    "user":          (r"给.{1,12}用", r"面向.{1,12}", r".{1,12}用户", r".{1,12}人群",
                      r".{1,12}学生", r".{1,12}白领", r".{1,12}开发者", r".{1,12}团队", r".{1,12}企业"),
    "core_features": (r"支持.{1,20}", r"可以.{1,20}", r"能.{1,20}", r".{1,12}功能",
                      r".{1,12}报表", r".{1,12}记录", r".{1,12}统计", r".{1,12}导出", r".{1,12}提醒"),
    "problem":       (r"解决.{1,20}", r".{1,12}麻烦", r".{1,12}痛点", r".{1,12}痛苦",
                      r".{1,12}难", r".{1,12}不便", r".{1,12}费时", r".{1,12}低效"),
}
#: 字段归属优先级 (多个命中 — 规格: user > core_features > problem)
_FIELD_MATCH_PRIORITY: tuple[str, ...] = ("user", "core_features", "problem")

def _resolve_answer_field(text: str, pending: list[str]) -> Optional[str]:
    """字段归属判定: 确认词 → None (不当字段值, 调用方提示缺字段);
    命中非当前字段模式且该字段未填 → 匹配字段; 未命中 → 当前字段 (正常回答零变化)。"""
    norm = str(text or "").strip()
    if not norm or not pending:
        return pending[0] if pending else None
    # 1. 确认词整句匹配 (复用 APPROVE_WORDS; 整句才触发 — "做报表"不误判)
    if norm.lower() in APPROVE_WORDS or norm.lower() in ("y", "yes"):
        return None
    # 2. 模式匹配 (优先级 user > core_features > problem; 只填未填字段)
    for field in _FIELD_MATCH_PRIORITY:
        if field not in pending:
            continue
        if any(re.search(p, norm) for p in _FIELD_PATTERNS.get(field, ())):
            return field
    # 3. 未命中 → 当前字段 (兼容正常回答, 逐字节不变)
    return pending[0]
```

### 1.2 接入点（三个填充路径, 批量模式不动 — 边界）

1. **LLM field_answer 路径** `_apply_field_answer`: `field = _resolve_answer_field(text, self._product_pending)`
   - None (确认词且缺字段) → 不填, 返回: "产品定义还不完整, 还缺 {FIELD_LABELS[当前字段]}, 请先补充"
     (guide 前缀 + needs_input=True, state 保持 DISCOVERY)
   - 命中其它字段 → 填该字段 (从 pending 移除), 继续下一问
   - 当前字段 → 既有逻辑 (零变化)
2. **机械单字段路径** (L585-586): 同样走 _resolve_answer_field — 无 LLM 同生效 (验收 3)
3. **批量模式** (L575-576): 不动 (规格边界: 不影响批量模式 — 多部分回答按顺序填)

### 1.3 确认词提示文案

```
"产品定义还不完整, 还缺 {字段中文标签}, 请先补充"
```

## 2. 契约测试要点（新增 ≥4, 附 test_session_ux_blockers 回归）

1. **T9 复现**: 问痛点答"给大学生用" → user 填 (非 problem); 答"支持扫码记账和月度报表" →
   core_features (非 user); 答"可以" (缺字段) → core_features 不被填, 消息含"还缺 问题"
2. **答非所问归类**: 问 user 答"支持扫码" → core_features; 问 core_features 答"记账很麻烦" → problem
3. **确认词不当值**: "可以"/"好"/"y" 缺字段 → 不填 + 提示; 全字段齐 → 正常进入确认 (防御)
4. **正常回答零变化**: 问 problem 答"记账麻烦, 月底对不上" → problem; 问 user 答"给大学生用" → user;
   问 core_features 答"扫码记账、报表" → core_features (逐字节同 v1.1.47)
5. **多命中优先级**: "给大学生用, 支持扫码" → user (user > core_features)
6. **无 LLM 同生效**: env -u → 机械路径归类一致
7. **批量模式不受影响**: 分号批量回答仍按顺序填
8. **误伤收敛**: 问 core_features 答"做报表" → core_features (非确认词 — 整句匹配); 问 problem 答
   "现在很痛苦" → problem

## 3. 版本与发布

- pyproject `1.1.47` → `1.1.48`; CHANGELOG v1.1.48 条目 (Fixed); 版本断言同步;
  **docs/FEATURES.md** 头版本 → v1.1.48 (+ 若功能表有发现/需求分析行 → 标注本修复)

## 4. Codex 实施范围

**Allowed/Files**:
- MOD `factory-console/session/conversation.py` (_FIELD_PATTERNS + _resolve_answer_field + 两接入点)
- MOD `tests/console/test_confirmation_intelligence.py` 或新增 `tests/console/test_s10_109_field_routing.py` (契约 ≥4)
- MOD pyproject.toml / CHANGELOG.md / 版本断言 / **docs/FEATURES.md**

**Forbidden（硬边界）**:
- 改确认门 handle_product_confirm / PRD 生成 actions.py / 调度 / CLI 命令 / board
- 改 product.py 数据模型 / parse_core_features / discovery_guide (只 import APPROVE_WORDS)
- 新增命令/字段/依赖; 禁 git add -A
- 禁 stub/fake: 无 LLM 规则必须真实生效; 若模式引入误伤 → 报告并收敛

**Validation**:
- `pytest tests/console/test_s10_109_field_routing.py -q` (或对应文件) 全绿
- env -u 聚焦 (test_discovery_* / test_confirmation_intelligence / test_session_pipeline /
  test_session_ux_blockers / test_session_conversation) 全绿
- env -u 全量 console 0 新增失败
- commit: `fix(S10-109): 需求分析字段错位 — 确定性内容归类(user/features/problem) + 确认词不当字段值, 正常回答零变化, v1.1.48`

## 5. 边界（不做）

- 不改 LLM 分类本身 (field_answer 归类仍可能误判 — 规则优先, LLM 补充; 如实标注)
- 不改确认门/PRD/调度/CLI/board; 不改批量模式; 不改数据模型/解析
- 不改 DS (DiscoverySession) — 规格只指 conversation.py 字段填充

## 6. 验收标准（Hermes 独立验证）

- [ ] T9 复现脚本 → 字段正确 (user/features 归类, "可以"不填+提示缺字段)
- [ ] 正常回答零变化 (与 v1.1.47 行为一致)
- [ ] 无 LLM (env -u) 规则路径同生效
- [ ] 契约测试 ≥3 新增 + 全量回归 0 新增失败
- [ ] 版本 v1.1.48 (pyproject + 断言 + CHANGELOG + FEATURES)
