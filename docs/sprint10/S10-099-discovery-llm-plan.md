# S10-099 — 发现阶段 LLM 深度介入：实现计划（CTO 架构设计 + Codex 指令）

> 日期: 2026-08-24 | 前置: v1.1.15 · 命名 LLM 接线已验收 (bcc1b14) · 全量基线 0 回归
> 用途: 三部门循环第 ②→③ 步 — Hermes(CTO) 架构设计 → Codex(工程) 实现
> 规格来源: docs/sprint10/S10-099-hermes-discovery-llm-prompt.md

---

## 0. 现状审计（CTO 实测确认）

| 项 | 现状 |
|---|---|
| 产品发现入口 | "我想做X" → `intent.py INTENT_CREATE_PRODUCT` → `ConversationManager.handle()` → `start_product_discovery()`（DISCOVERY 多轮） |
| 字段收集 | `handle_product_answer()` 规则状态机: 控制短语优先 → 逐字段填 `_product_pending`（problem→user→core_features）→ 批量/编辑/逃生 |
| 命名 | `_enter_product_confirmation()` 已接 `ReasoningProvider._default_llm_fn()`（bcc1b14 修复, LLM 可用 → AI 命名; 否则 deterministic） |
| LLM 基建 | `reasoning.py ReasoningProvider._default_llm_fn()` — 复用 exec.cli provider 装配链, 无 key/provider → 抛 ReasoningUnavailable |
| 关键缺口 | 用户初始自然描述只存 `raw`, **从不解析** → 逐字段追问（"太模板化"根因）; 追问机械列模板; 确认门无理解摘要 |
| 另类入口 | "开始做X" → DiscoverySession (S10-065) — **本 Sprint 不动**（边界, 见 §8） |

## 1. 发现流程新架构（LLM 主路径 + 规则兜底, 混合）

```
用户描述（含初始"我想做X"整句 + 后续回答）
  │
  ├─ ① 确定性控制门（硬闸, 永在前）: _product_control() 现有短语
  │   取消/整理/修改指令/现在创建/逃生/批量 — 命中 → 走既有处理（LLM 永不覆盖）
  │
  ├─ ② LLM 可用（llm_fn 装配成功）→ 意图理解 + 结构化提取（新模块 discovery_intelligence）
  │    ├─ category=control/query（模糊改写, 确定性漏网）→ 映射既有控制行为
  │    ├─ category=product_description → extraction 一次填字段
  │    │    ├─ 必填齐 → 直入确认（LLM 理解摘要 + 主动分析展示）
  │    │    └─ 必填缺（输入真没给）→ 智能追问（针对性 1 问 + 为什么缺）
  │    └─ category=field_answer → 字段答案（并入既有 apply 逻辑）
  │
  └─ ③ LLM 不可用 / 输出非法 → 现有状态机逐字节不变（诚实降级, 不伪造）
```

**关键原则**:
- 确定性控制短语是硬闸, LLM 分类只作**模糊改写的补充网**, 永不覆盖确定性结果
- LLM 提取成功且必填齐 → **一次产出**, 不再逐字段问（验收 1）
- LLM 失败/无 key → 走 ③, 行为与 v1.1.15 完全一致（验收 3）
- 所有 LLM 路径标记 `ai_generated`（诚实标注, 前端/日志可区分）

## 2. LLM 提取/理解接口（新模块 `factory-console/session/discovery_intelligence.py`）

### 2.1 类与函数

```python
class DiscoveryIntentAnalyzer:
    def __init__(self, llm_fn: Optional[Callable[[str, str], str]] = None): ...
    # llm_fn=None → 尝试 ReasoningProvider()._default_llm_fn(); 仍不可用 → 抛 DiscoveryLLMUnavailable

    def analyze(self, text: str, *, history: Optional[list[str]] = None) -> DiscoveryAnalysis:
        # 1 次 LLM 调用 → 结构化 JSON → 解析（宽容链）→ schema 校验 → DiscoveryAnalysis

    # 供 conversation.py 使用
    def extract_once(self, text: str, history=None) -> DiscoveryAnalysis  # = analyze 别名（语义清晰）
```

### 2.2 输出契约（DiscoveryAnalysis, dataclass）

```python
@dataclass
class DiscoveryAnalysis:
    category: str            # "control" | "query" | "product_description" | "field_answer"
    reason: str              # 一句分类理由（可审计）
    extraction: dict         # {problem, user, core_features:list, name, platform} — 可空
    missing_reasons: dict    # 必填缺失字段 → 为什么缺（智能追问依据）
    smart_questions: list[str]  # ≤3 条针对性追问（优先 1 条）
    proactive: dict          # {platform, competitors, scope, notes} — 用户没说但该有的
    understanding: str       # 一句理解摘要: "我理解你要做 X, 给 Y 用, 核心是 A/B/C"
```

### 2.3 Prompt 设计（核心交付）

```
你是 AI Factory 的产品经理。用户正在描述一个产品想法, 可能是完整描述、
字段回答、控制指令或查询。判断意图（优先级: 控制指令 > 查询 > 字段回答 > 产品描述）,
并尽可能结构化提取产品定义。

【对话历史】(最近 3 轮, 无则空)
{history}

【用户最新输入】
{text}

【输出要求】只输出一个 JSON 对象, 禁止 markdown 围栏/注释/多余文字:
{
  "category": "control|query|product_description|field_answer",
  "reason": "分类理由（一句）",
  "extraction": {"problem": "", "user": "", "core_features": [], "name": "", "platform": ""},
  "missing_reasons": {"problem": "该字段缺失的原因, 只在输入确实没给时列出"},
  "smart_questions": ["针对最重要缺失字段的一个具体问题"],
  "proactive": {"platform": "", "competitors": "", "scope": "", "notes": ""},
  "understanding": "一句话理解摘要, 形如: 我理解你要做X, 给Y用, 核心是A/B/C"
}

规则:
- 控制指令（取消/算了/整理/重新开始/查询项目/修改字段）→ category=control, 不提取字段
- 查询（项目列表/当前项目/进度）→ category=query
- 产品描述（哪怕不完整）→ category=product_description, 尽力提取; 提取不到的必填字段
  在 missing_reasons 说明为什么缺, smart_questions 只问最重要的一条
- 纯字段回答（"给程序员用"）→ category=field_answer, 只填对应字段
- extraction 字段只填输入中明确出现的信息, 不猜测、不编造
```

### 2.4 解析与容错（复用 reasoning.py 模式）

- 解析宽容链: 剥 ` ```json ` 围栏 → `json.loads` → `{...}` 子串回退 → 仍失败 → `DiscoveryLLMError`
- schema 校验: `category` ∈ 合法面; `extraction` 缺字段补空; `smart_questions` 截断 ≤3
- 任何异常 → `DiscoveryLLMError` → 上层走规则兜底（诚实降级, 永不 5xx / 永不伪造理解）

## 3. 与 ConversationManager 状态机集成点（最小改动）

### 3.1 `start_product_discovery(text)` — 初始描述即解析（验收 1 核心）

```
现有: 建 ProductIntent(raw=text) → 问第一问
新增: 若 LLM 可用 → analyze(text)（历史=[text]）
  ├─ extraction 覆盖全部必填 → 填字段 → 直入 _enter_product_confirmation()（含理解摘要）
  ├─ 部分覆盖 → 填已有字段, pending 只留真正缺失 → 智能追问（1 条, 带理由）
  └─ category=control/query（罕见, 初始句一般是描述）→ 按类别映射
  LLM 不可用 → 现有逻辑不变
```

### 3.2 `handle_product_answer(text)` — 回答轮（含"整理一下"类模糊控制）

```
现有: _product_control() 确定性硬闸 → 未命中 → 逐字段填
新增: 确定性未命中且 LLM 可用 → analyze(text, history=最近轮次)
  ├─ category=control → 映射到 _cancel_product_discovery/_summarize_product_only/
  │    _escape_product_flow（"整理一下" 等模糊改写 → 整理不创建, 不被当字段 — 验收 2）
  ├─ category=query → _escape_product_flow（交回宿主按普通意图链）
  ├─ category=product_description → extraction 合并填缺失字段:
  │    ├─ 必填齐 → _enter_product_confirmation()（理解摘要）
  │    └─ 仍缺 → 智能追问（只问最重要的 1 条, 用 missing_reasons 组织话术）
  └─ category=field_answer / LLM 不可用 / 非法 → 现有逐字段逻辑（不变）
```

### 3.3 `_enter_product_confirmation()` — 确认门增强（验收 4）

```
现有: 命名候选 → to_summary() → 确认提示
新增: LLM 理解摘要可用时, 消息头部加:
  "我理解你要做 {name}, 给 {user} 用, 核心是 {core_features}, 对吗?"
  + 主动分析块（若 proactive 非空）:
  "主动建议: 平台={platform} · 竞品={competitors} · 范围={scope} · 备注={notes}"
  LLM 不可用 → 现有消息逐字节不变
```

### 3.4 ConversationResponse 扩展（可审计, 缺省零影响）

- 新增可选字段: `understanding: Optional[str] = None`, `proactive: Optional[dict] = None`,
  `ai_generated: bool = False` — 缺省与既有行为完全一致
- `handle_product_confirm` 不改（确认语义不变）

### 3.5 llm_fn 装配（复用 naming 修复同一模式）

```python
try:
    from .discovery_intelligence import DiscoveryIntentAnalyzer
    analyzer = DiscoveryIntentAnalyzer()   # 内部尝试 _default_llm_fn()
except Exception:
    analyzer = None                          # 无 key/provider → 规则兜底
```

## 4. 智能追问 vs 机械追问判定

| 情形 | 走 |
|---|---|
| LLM 不可用 / 输出非法 / 分类失败 | 机械追问（现有 FIELD_QUESTIONS 模板, 逐字段） |
| LLM category=product_description, 缺 1 必填（输入真没给） | 智能追问: 1 条 + 为什么缺（missing_reasons 话术） |
| LLM category=product_description, 缺 ≥2 必填 | 智能追问 1 条（最重要）; 若用户再答, 继续逐轮 |
| LLM category=field_answer | 并入现有 apply（视为当前字段答案） |
| 控制/查询 | 确定性/分类映射, 绝不进字段 |

原则: **智能追问只问"输入里真没有"的**, 且一次只问最重要的一条;
机械追问是兜底, 不是默认。

## 5. 契约测试要点（Codex 必须覆盖）

新增 `tests/console/test_discovery_llm_intelligence.py`（mock LLM 注入, 不依赖真实 key）:

1. **自然描述一次产出**: mock LLM 返回 product_description+全字段 extraction →
   单次 `handle("我想做个markdown编辑器, 要typora和notepad++优点, 适配手机")`
   → 必填齐, 状态直达 PRODUCT_CONFIRMATION, 消息含理解摘要（验收 1/4）
2. **控制指令不被当字段**: "取消"（确定性）与 mock LLM 返回 product_description →
   确定性优先, 走取消; "整理一下"（模糊）mock LLM 返回 control →
   走整理不创建（验收 2）
3. **无 LLM 零变化**: llm_fn 装配失败/None → 现有状态机行为不变（与基线测试逐条对照,
   "我想做X" 仍逐字段问; 既有 40+ 命名/对话测试不改不破 — 验收 3）
4. **确认摘要展示**: LLM 用后确认消息含 "我理解你要做"; 未用 → 不含（验收 4）
5. **非法 LLM 输出降级**: mock 返回非 JSON / 缺 schema → 规则兜底, 不崩溃
6. **批量/编辑/逃生回归**: 既有 handle_product_answer 分支在 LLM 路径下仍可达
7. **向后兼容**: tests/console/test_session_product*.py / test_conversation*.py 全绿

**真实 LLM 验收（唯一真相, 独立验证用, 不进 CI）**:
```bash
env DEEPSEEK_API_KEY=... .venv/bin/python - <<'PY'
from factory_console.session.discovery_intelligence import DiscoveryIntentAnalyzer
a = DiscoveryIntentAnalyzer().analyze(
    "我想做个 markdown 编辑器, 要 typora 和 notepad++ 的优点, 适配手机")
print(a.category, a.extraction, a.understanding, a.proactive, a.smart_questions)
PY
# 断言: category=product_description; extraction.problem/user/core_features 非空;
# understanding 含"我理解你要做"; 非逐字段问
```

## 6. 版本与发布

- `pyproject.toml` version `1.1.15` → `1.1.16`（patch+1）
- `CHANGELOG.md` 加 v1.1.16 条目（Fixed/Added 分类, 中文, Keep a Changelog 风格）
- 版本断言测试同步（`tests/console/test_s10_074_deployment.py` 及任何断言 1.1.15 的测试）
- 全量回归: `env -u DEEPSEEK_API_KEY .venv/bin/python -m pytest tests/console tests/api -q`
  0 新增失败 + 相关 doc 版本引用更新

## 7. Codex 实施范围（Files / Allowed / Forbidden / Validation）

**Allowed/Files**:
- 新增 `factory-console/session/discovery_intelligence.py`
- 新增 `tests/console/test_discovery_llm_intelligence.py`
- 修改 `factory-console/session/conversation.py`（§3 集成点, 最小改动）
- 修改 `factory-console/session/__init__.py`（如需导出）
- 修改 `pyproject.toml` / `CHANGELOG.md` / 版本断言测试 / docs 版本引用

**Forbidden**:
- 改 `naming.py` / `reasoning.py` / `product.py` / `intent.py` / `DiscoverySession`（复用不重造）
- 改任何既有测试的断言（除版本号 1.1.15→1.1.16 外）
- 动 providers/exec/desktop / 部署 / 数据库
- 新增第三方依赖（纯标准库 + 现有模块）

**Validation（Codex 自测后提交）**:
- `.venv/bin/python -m pytest tests/console/test_discovery_llm_intelligence.py -q` 全绿
- `env -u DEEPSEEK_API_KEY .venv/bin/python -m pytest tests/console/test_session_product.py tests/console/test_conversation.py -q`（既有产品/对话测试 0 破）
- `git status` 只含上述文件; commit message: `feat(S10-099): 发现阶段 LLM 深度介入 — 意图理解/结构化提取/智能追问/确认摘要, 规则兜底, v1.1.16`

## 8. 边界（不做）

- 不做 product_pipeline 深度分析（"让PM分析"已有）
- 不做多语言（仅中文）
- 不改 DiscoverySession (S10-065, "开始做X" 路径) — 本 Sprint 聚焦 ConversationManager 主路径; 若验收暴露 DiscoverySession 同样模板化, 记风险下个 Sprint 处理
- 不做前端/桌面端 UI 改动（消息文案即界面）
- 不重造命名/推理/LLM 装配（全复用）

## 9. 验收标准（Hermes 独立验证, 非 Codex 自报告）

- [ ] 真实 LLM 自然描述一次产出（§5 脚本, 唯一真相）
- [ ] 控制指令 "取消"/"整理一下" 不被当字段
- [ ] 无 LLM（env -u + 模拟无 key）→ 现有状态机零变化（行为对照）
- [ ] 确认门展示 LLM 理解摘要
- [ ] 全量回归 0 新增失败 + git clean（除既有 untracked: demo/team_execution_state.json, unused/）
- [ ] 版本 v1.1.16
