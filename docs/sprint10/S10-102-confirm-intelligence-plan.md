# S10-102 — 确认阶段智能分流 + 求助词全覆盖：实现计划（CTO 架构设计 + Codex 指令）

> 日期: 2026-08-24 | 前置: v1.1.22 · S10-101 引导体验已验收
> 用途: 三部门循环第 ②→③ 步 — Hermes(CTO) 架构设计 → Codex(工程) 实现
> 规格来源: docs/sprint10/S10-102 提示词（Founder 实测 2 bug）

---

## 0. 现状审计（CTO 实测确认）

| Bug | 根因（代码定位） |
|---|---|
| 1. "可以，先出prd文档"/"？" 被当产品名 | `conversation.py handle_product_confirm`: 非 y/取消 → 一律 `product_intent.name = raw`（S10-081 改名兜底过宽, 无分类） |
| 2. "没 想法" 填进 core_features | `_is_help_request` 无归一化: `any(keyword in raw for keyword in HELP_KEYWORDS)` — "没 想法" 不含 "没想法"; 且词表缺 随便/你定/你看吧 等 |

现状补充: 宿主 session.py `handle_product_confirm(line, confirm_fn=_create_product_fn)`; `create_product` action 返回 `data.project`（宿主可取 id）; `generate_prd(context)` action 已存在 (S10-051, 纯规则, 产品源=session.product_intent, 确认后 product_intent 已就位) → "确认+下一步→PRD" 宿主接线可行。
DS 确认阶段: 模型级 confirm()（无 READY 输入改名逻辑）→ 确认分流只改 conversation 路径; DS 只需求助词归一化修复。
基线: console+api 4923 passed / 1 skipped / 0 failed; 聚焦 55 passed。

## 1. 架构决策

### 1.1 共享确定性表（discovery_guide.py 扩展 — 两路径/可测试唯一来源）

```python
def normalize_help_text(text: str) -> str:
    # 去全部空白 (半角/全角空格/tab/换行) — "没 想法"→"没想法"

#: 求助词全覆盖 (字段收集阶段: 命中 → 建议流, 不填字段)
HELP_KEYWORDS += ("随便","你定","你看吧","你决定","听你的","你来定","都行","都可以",
    "无所谓","你推荐","推荐个","出个主意","想不出来","没想法了","不知道做什么","不知道做啥",
    "帮我拿主意","你帮我定","都听你的","怎么都行")

#: 确认词 (纯确认 — 无下一步动作)
APPROVE_WORDS: tuple[str, ...] = ("y","yes","是","确认","同意","可以","好","好的","行",
    "行吧","ok","okay","没问题","就这样","批准","就这么办","妥","搞","做","上")

#: 确认+下一步 动作关键词 → action_id (approve 前缀 + 剩余部分含关键词)
APPROVE_NEXT_ACTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("prd", ("prd","需求文档","产品需求文档","写需求","出需求")),
    ("develop", ("开发","开工","开始做","动工")),
    ("create", ("创建","建项目","创建项目")),
)

#: 明确改名命令 (正则: 改名叫X / 名字改成X / 改名为X / 把名字改成X)
RENAME_RE = re.compile(r"(?:改名叫|名字改成|改名为|把名字改成|重命名为|名字改为)(.+)")

#: 澄清/问号请求 (→ 智能澄清, 不改名不确认)
CLARIFY_WORDS: tuple[str, ...] = ("?","？","为什么","啥意思","什么意思","解释一下","不明白",
    "没懂","没明白","这是什么","然后呢","啥","怎么用","能改吗")

#: 确认阶段委托词 (用户没想法交给你定 → 视为确认, 不改名)
CONFIRM_DELEGATE_WORDS: tuple[str, ...] = ("随便","你定","你看吧","你决定","听你的","你来定",
    "都行","都可以","无所谓","你看着办","都听你的","怎么都行")
```

匹配规则:
- 求助词: `any(kw in normalize_help_text(text) for kw in HELP_KEYWORDS)`（两路径 `_is_help_request` 改用）
- 确认词: 首段切分 `re.split(r"[，,。.、!?\s]+", norm, 1)[0].lower()` ∈ APPROVE_WORDS
- 确认+下一步: 首段是确认词 且 剩余部分含任一动作关键词 → (approved, next_action=action_id)
- 澄清: norm ∈ {"?","？"} 或开头/含 CLARIFY_WORDS 词
- 委托: norm ∈ CONFIRM_DELEGATE_WORDS → approved (保持当前名称)

### 1.2 Analyzer 确认分类（discovery_intelligence.py 扩展）

```python
@dataclass
class ConfirmationAnalysis:
    category: str   # approve | approve_next | rename | clarify | cancel | delegate | other
    next_action: str = ""   # approve_next: "prd"/"develop"/"create"
    rename_to: str = ""     # rename: 新名称
    reason: str = ""

def analyze_confirmation(self, text, *, product_summary: str) -> ConfirmationAnalysis:
    # prompt: 确认阶段输入分类 (附产品摘要/当前名称候选), 优先级:
    #   确认(含确认+下一步) > 明确改名 > 澄清提问 > 取消 > 委托 > 其它
    # 宽容解析链 + schema 校验 (category ∈ 合法面); 失败 → ConfirmationLLMError
```

### 1.3 conversation.handle_product_confirm 分流重构

```
1. _product_control (取消/整理/逃生/修改指令) — 不变, 最前
2. "创建项目/现在创建" → approved — 不变
3. 确定性分流 (no-LLM 全覆盖):
   a. RENAME_RE 命中 → rename_to → 设名 → _enter_product_confirmation (明确改名行为不变)
   b. 确认+下一步: 首段确认词 + 动作关键词 → approved + next_action (名称不被覆盖!)
   c. 纯确认词 → approved
   d. 澄清 (？/为什么/什么意思…) → _clarify_confirmation(): 重展示摘要 + 解释选项 (不改名)
   e. 取消词 (既有 _CANCEL_ANSWERS) → reset (不变)
   f. 委托词 → approved (不改名)
4. 确定性未决 且 LLM 可用 → analyze_confirmation → 按 category 路由 (含 other → 改名兜底)
5. 兜底 (无 LLM/失败): 裸文本 → 改名 (S10-081 兼容: "墨笺" 行为不变)
```

ConversationResponse += `next_action: Optional[str] = None`
approved + next_action 时: 正常走 confirm_fn 创建 → 响应携带 next_action。

### 1.4 宿主接线（session.py — 确认+下一步执行）

- `_create_product_fn` 返回消息; 创建成功可从 `result.data["project"]` 取 id
- session 收到 resp.next_action == "prd" → 复用 context (product_intent 已设) 执行 `generate_prd` action
  → 消息追加 "已生成 PRD: projects/<slug>/PRD.md"; 失败 → 消息注明 (不阻断创建)
- "develop"/"create" 本 Sprint 只传信号 + 记录, 宿主执行留待后续 (验收锚点是 prd)

### 1.5 DiscoverySession（discovery.py — 仅求助词归一化）

- `_is_help_request` 改用 `normalize_help_text` + 扩展词表 (同 1.1) — "没 想法" 修复
- 确认阶段不改 (模型级 confirm(), 无改名 bug; 驱动未接线 — 边界)

## 2. 契约测试要点

新增 `tests/console/test_confirmation_intelligence.py` + `test_discovery_guide.py` 扩展:

1. **"可以，先出prd文档"** → approved=True + next_action="prd" + 名称未被覆盖 (验收 1)
2. **"？"/"?"** → 澄清响应 (不改名, 不确认, 消息含解释) (验收 2)
3. **"没 想法"** → 建议流 (不填 core_features="想法") (验收 3); 两路径各验
4. 纯 y → approved; "n"/"取消" → reset (向后兼容)
5. "改名叫墨笺" → rename (向后兼容); "墨笺" 裸文本 → rename 兜底
6. "可以"/"好"/"行" → approved (不再当名称)
7. "随便"/"你定" 确认阶段 → approved 不改名; 字段收集阶段 → 建议流
8. 确认+下一步各动作: "好，开始开发" → next_action="develop"; "行，创建项目" → "create"
9. LLM 分类: mock analyze_confirmation → approve_next/rename/clarify/other 路由; 无 LLM 兜底
10. 宿主接线: session 层 "可以，先出prd文档" → create_product + generate_prd 执行 (mock action 或真实 tmp workspace)
11. 全量回归 0 新增; 版本 v1.1.23

## 3. 版本与发布

- pyproject.toml `1.1.22` → `1.1.23`; CHANGELOG v1.1.23; 版本断言同步; docs

## 4. Codex 实施范围

**Allowed/Files**:
- MOD `factory-console/session/discovery_guide.py` (1.1 表 + normalize)
- MOD `factory-console/session/discovery_intelligence.py` (analyze_confirmation)
- MOD `factory-console/session/conversation.py` (handle_product_confirm 重构 + next_action)
- MOD `factory-console/session/discovery.py` (_is_help_request 归一化)
- MOD `factory-console/session/session.py` (next_action="prd" → generate_prd 宿主接线)
- NEW `tests/console/test_confirmation_intelligence.py` (+ guide 扩展)
- MOD pyproject.toml / CHANGELOG.md / 版本断言 / docs

**Forbidden**:
- 改 naming.py / reasoning.py / product.py / intent.py / llm_intent.py; 改状态机状态集
- 改既有测试语义断言 (消息精确断言按新行为更新需注释原因)
- 动 exec/desktop/providers/部署/数据库; 新增第三方依赖
- 碰工作区他会话未提交 tests/console/test_console_cli.py (禁 add -A)

**Validation**:
- `pytest tests/console/test_confirmation_intelligence.py tests/console/test_discovery_guide.py -q` 全绿
- env -u 聚焦 (conversation + discovery + analyzer + session) 全绿
- env -u 全量 console 0 新增失败
- commit: `feat(S10-102): 确认阶段智能分流(确认/确认+下一步/改名/澄清/取消) + 求助词全覆盖, 宿主PRD接线, v1.1.23`

## 5. 边界（不做）

- develop/create next_action 宿主执行留待后续 (本 Sprint 传信号)
- DS 确认阶段分流不做 (模型级 confirm, 无 bug); DS 驱动接线是 S10-065 遗留
- 不改确认消息本身文案 (除澄清响应新增解释块)

## 6. 验收标准（Hermes 独立验证）

- [ ] 真实 LLM: "可以，先出prd文档" → 确认 + next_action=prd + 名称不被覆盖; "？" 澄清不改名
- [ ] "没 想法"/"随便" 字段收集 → 建议流不填字段 (两路径)
- [ ] 向后兼容: y/N/改名叫X/裸名称 行为不变; 无 LLM 规则兜底
- [ ] 全量回归 0 新增失败; 版本 v1.1.23
