# S10-101 — 产品发现引导体验：实现计划（CTO 架构设计 + Codex 指令）

> 日期: 2026-08-24 | 前置: v1.1.21 · S10-099/100 两路径 LLM 化已验收
> 用途: 三部门循环第 ②→③ 步 — Hermes(CTO) 架构设计 → Codex(工程) 实现
> 规格来源: docs/sprint10/S10-101 提示词（Founder 实测 3 缺陷）

---

## 0. 现状审计（CTO 实测确认）

| 缺陷 | 根因 | 本 Sprint 修法 |
|---|---|---|
| 1. 无进度提示 | 两路径消息只有问题, 无步骤/剩余/生命周期 | 确定性进度行 + 生命周期行（无 LLM 也显示） |
| 2. 中间字段机械 | field_answer 分类后落回机械模板 ("主要给谁使用?") | analyzer 对 field_answer 也产下一个缺失字段的智能追问 |
| 3. 求助未响应 | "给些建议/没有想法" 被当字段内容收下 | 新 category=help_request + 关键词兜底 → 建议 → 确认填入 |

路由确认: "做个记账App" → LLMIntentParser (v1.1.20, 生产默认) → create_product{name} → conversation DISCOVERY。
基线: 4866 passed / 1 skipped / 0 failed (console+api); 聚焦 180 passed。

## 1. 架构决策

### 1.1 新增共享模块 `factory-console/session/discovery_guide.py`（两路径同步的唯一来源）

```python
#: 生命周期行 (当前阶段高亮)
LIFECYCLE_LINE = "流程: 发现→确认→创建→PRD→工程→开发"

def lifecycle_line(current: str = "发现") -> str:
    # "流程: 发现→确认→创建→PRD→工程→开发 (当前: 发现)" — 当前阶段用 [ ] 标出

def format_progress(filled: list[str], pending: list[str]) -> str:
    # "产品定义 2/3: 问题✅ 用户✅ 核心功能待填"
    # 必填字段 = problem/user/core_features (3); 字段中文名用 FIELD_LABELS

def enhanced_line(answers: dict) -> str:   # DiscoverySession 专用 (可选)
    # "增强(可选): 使用场景待填 · MVP范围待填 · 非功能待填" — 已填标 ✅, 无待填则省略

#: 求助关键词 (确定性硬闸 — LLM 前先查, 两路径共用)
HELP_KEYWORDS: tuple[str, ...] = ("给些建议","给点建议","给个建议","给点意见","给些意见",
    "没有想法","没想法","没思路","没有思路","你建议","你看着办","帮我出主意",
    "不知道怎么","你帮我定","你来定","推荐一下","有什么建议")

#: 每字段确定性建议 (无 LLM 兜底 — 诚实, 不伪造 LLM)
DEFAULT_SUGGESTIONS: dict[str, list[str]] = {
    "problem": ["现有工具太繁琐", "效率低/耗时长", "信息分散难管理"],
    "user": ["个人用户", "小团队/中小企业"],
    "core_features": ["快速录入", "分类统计", "导出报表"],
    "usage_scenarios": ["日常使用", "工作场景", "移动中随时用"],
    "mvp_scope": ["核心流程跑通", "单端先行"],
    "non_functional_requirements": ["数据安全", "响应快", "兼容主流设备"],
}
```

进度提示**确定性**: format_progress 纯状态计算, 不依赖 LLM/analyzer — 无 key 也显示 (验收 3)。
求助**确定性兜底**: HELP_KEYWORDS 硬闸 + DEFAULT_SUGGESTIONS — LLM 缺席时也响应求助 (诚实降级,
非伪造 LLM; 关键词命中才触发, 正常输入零影响)。

### 1.2 Analyzer 扩展（discovery_intelligence.py）

- `VALID_CATEGORIES` += `"help_request"`; prompt 优先级: 控制指令 > 查询 > **求助** > 字段回答 > 产品描述
- 输出契约 += `suggestions: {"field": "", "items": [], "note": ""}`（help_request 时填充）
- prompt 规则:
  - 求助类输入 (给些建议/没有想法/你看着办) → category=help_request, suggestions 给当前缺失字段的
    3-5 条方向性建议 (items), note 一句话说明
  - 字段回答 (field_answer) → 除只填对应字段外, 若还有必填缺失, **smart_questions 给出下一个
    最重要缺失字段的追问** (带 missing_reasons 理由) — 中间字段 LLM 化的契约来源
- schema 归一化: suggestions 缺省空; smart_questions 逻辑不变

### 1.3 两路径集成（conversation.py + discovery.py, 对称改）

**进度/生命周期 (两路径)**:
- 每个发现阶段消息**前缀**: `lifecycle_line()` + `format_progress(filled, pending)` (必填)
- READY/确认消息: 进度 3/3 + lifecycle(current="确认")
- DiscoverySession 增强字段: `enhanced_line()` 附在必填进度后 (可选提示)
- 批量模式/编辑/逃生等既有分支: 消息统一加前缀 (保持信息一致)

**求助流 (两路径)**:
```
用户: 给些建议
1) HELP_KEYWORDS 确定性硬闸 (LLM 前) → 命中 → 当前缺失字段的 DEFAULT_SUGGESTIONS
2) 未命中 → LLM analyze → category=help_request → suggestions.items
→ 展示: "当前缺{字段} — 建议方向:\n 1. X  2. Y  3. Z\n(输入 y 用全部建议 / 1-3 选择 / 直接输入自定义)"
→ 挂起 proposal 状态 {field, items}; 用户下一输入: y → 全填; 1-3 → 选填; 其它 → 自定义填入
→ 填入后: 更新进度 → 继续追问/确认 (走 LLM 智能或机械)
```
- proposal 状态: conversation `_suggestion_proposal`; DiscoverySession `_suggestion_proposal`
- 求助输入**绝不当字段内容收下** (验收 3); 无 LLM → 关键词+默认建议仍响应 (诚实)

**中间字段 LLM 化 (两路径)**:
- field_answer 分类 → apply 后, 下一问优先取 analysis.smart_questions[0] (带理由);
  analyzer 未给/失败 → 机械模板 (诚实降级, 验收 "无 LLM 机械追问保留")
- system_question 多轮合并 (v1.1.19) 保持不变 — 回答并入不覆盖

## 2. 契约测试要点（新增 tests/console/test_discovery_guide.py + 两路径用例）

1. **进度确定性**: 无 LLM (env -u) 两路径消息含 "产品定义 X/3:" + "流程: 发现→确认→创建→PRD→工程→开发" + 字段 ✅/待填
2. **进度推进**: 每答一问进度 +1; READY 时 3/3
3. **中间字段智能**: mock LLM field_answer + smart_questions → 下一问用 LLM 追问 (非机械); smart_questions 空 → 机械
4. **求助 LLM 路径**: mock LLM help_request + suggestions → 展示建议 → y → 填入字段 → 进度更新
5. **求助关键词兜底 (无 LLM)**: "给些建议" → DEFAULT_SUGGESTIONS → 确认填入
6. **求助不当字段**: "没有想法" 不被收为字段内容 (答案不是 "没有想法")
7. **选择/自定义**: y 全填 / "2" 单选 / "自定义内容" 直填
8. **无 LLM 零变化 (语义)**: 非求助输入 → 问题文本/字段顺序与 v1.1.21 一致 (仅加进度前缀);
   既有 108+26+35+conversation 测试中**消息断言按新格式更新** (进度前缀是有意变更, 逐条记录)
9. **两路径行为一致**: 同输入 (progress/help/smart) 两路径输出结构相同

## 3. 版本与发布

- pyproject.toml `1.1.21` → `1.1.22` (patch+1)
- CHANGELOG.md v1.1.22 条目; 版本断言测试同步; docs 版本引用

## 4. Codex 实施范围（Files / Allowed / Forbidden / Validation）

**Allowed/Files**:
- NEW `factory-console/session/discovery_guide.py`
- MOD `factory-console/session/discovery_intelligence.py` (help_request + suggestions + field_answer 追问契约)
- MOD `factory-console/session/conversation.py` (进度/求助/中间字段 — 本 Sprint 首次允许)
- MOD `factory-console/session/discovery.py` (同)
- NEW `tests/console/test_discovery_guide.py` (+ 两路径新增用例; 既有测试仅当断言精确消息时按新格式更新并注释原因)
- MOD pyproject.toml / CHANGELOG.md / 版本断言测试 / docs

**Forbidden**:
- 改 naming.py / reasoning.py / product.py / intent.py / llm_intent.py
- 改 analyzer/两路径的**语义** (字段顺序/状态机状态集/控制短语) — 只加不减
- 动 exec/desktop/providers/部署/数据库; 新增第三方依赖
- 碰工作区他会话未提交改动 tests/console/test_console_cli.py (只 add 本 Sprint 文件, 禁 add -A)
- 禁止 stub/fake: 无 LLM 的求助建议必须是确定性默认 (非伪造 LLM); 进度/生命周期纯确定性

**Validation（Codex 自测后提交）**:
- `.venv/bin/python -m pytest tests/console/test_discovery_guide.py -q` 全绿
- `env -u DEEPSEEK_API_KEY` 聚焦套件 (discovery 108 + session_llm 26 + analyzer 35 + conversation + product) 全绿
- `env -u DEEPSEEK_API_KEY .venv/bin/python -m pytest tests/console -q` 全量 0 新增失败
- 无 LLM 实测: "做个记账App" (Keyword 路径) → 消息含进度行 + 机械追问 + "给些建议" → 默认建议填入
- commit message: `feat(S10-101): 产品发现引导体验 — 确定性进度/生命周期 + 中间字段智能追问 + 求助建议填入, 两路径同步, v1.1.22`

## 5. 边界（不做）

- 不改 lifecycle 流程本身 (发现→确认→创建→PRD→工程→开发 仅是引导文案, 不驱动状态机)
- 不做图形化进度 (CLI 文本); 不做多语言
- 求助建议只作用于**当前缺失字段** (不做整产品方案生成 — 那是 PM 分析已有)

## 6. 验收标准（Hermes 独立验证, 非 Codex 自报告）

- [ ] 真实 LLM: "做个记账App" (LLMIntentParser 生产路由) → 全流程消息带进度 + 生命周期;
      中间字段追问智能 (带理由, 非纯模板); "给些意见" → 建议展示 → 确认填入
- [ ] 无 LLM: 进度仍在 (确定性) + 机械追问保留 + 求助关键词默认建议
- [ ] 两路径输出结构一致 (进度/求助/中间字段)
- [ ] 全量回归 0 新增失败 (消息格式更新逐条有因) + 提交只含本 Sprint 文件
- [ ] 版本 v1.1.22
