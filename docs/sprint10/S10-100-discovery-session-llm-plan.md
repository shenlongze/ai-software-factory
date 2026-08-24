# S10-100 — DiscoverySession 同步 LLM 化：实现计划（CTO 架构设计 + Codex 指令）

> 日期: 2026-08-24 | 前置: v1.1.20 · S10-099 conversation 路径 LLM 化已验收 · v1.1.19 已修多轮字段合并边界
> 用途: 三部门循环第 ②→③ 步 — Hermes(CTO) 架构设计 → Codex(工程) 实现
> 规格来源: docs/sprint10/S10-100 提示词（用户提供）

---

## 0. 现状审计（CTO 实测确认）

| 项 | 现状 |
|---|---|
| 两路径 | conversation.py (S10-099, 已 LLM 化) vs DiscoverySession (S10-065, 纯规则逐字段) — **不一致** |
| DiscoverySession | discovery.py: start → 第一问 "这个产品解决什么问题?" → process_user_input 逐字段 (problem→user→core_features→usage_scenarios→mvp_scope→nfr) → build_summary → confirm → create_product |
| analyzer | discovery_intelligence.py (S10-099 + v1.1.19 修复): extraction 契约 **5 字段** {problem,user,core_features,name,platform}; 支持 system_question 上下文 (回答并入不覆盖) |
| 字段集差异 | DiscoverySession 7 字段 (5 + usage_scenarios/mvp_scope/non_functional_requirements) vs analyzer 5 字段 |
| LLM 基建 | analyzer 默认装配 ReasoningProvider._default_llm_fn()；naming.py suggest_names 已共享 |
| 摘要标签 | 两路径标签已一致 (产品/问题/目标用户/核心功能/运行平台) — 对齐成本低 |
| 测试面 | test_session_discovery.py 108 tests（纯规则, 无 LLM 引用）; analyzer 35 tests |
| 工作区 | 有他会话未提交改动 tests/console/test_console_cli.py（create 命令测试修复, 不属本 Sprint, 勿碰/勿扫入提交） |

## 1. 架构决策：复用 + 扩展 analyzer（不重造）

**决策: 扩展 DiscoveryIntentAnalyzer 的 extraction 契约, 而非新建 DiscoverySession 专用 analyzer。**

- `EXTRACTION_FIELDS` += `usage_scenarios / mvp_scope / non_functional_requirements`（可选键, 缺省空）
- prompt 输出 schema 同步加 3 键 + 规则: "描述中明确提到使用场景/MVP范围/非功能要求才填, 否则留空"
- **向后兼容保证**: conversation.py 的 `_apply_extraction_to_intent` 只读 problem/user/core_features/name/platform,
  新键被忽略 → conversation 路径零行为变化; analyzer 既有 35 tests 零改动
- 复用: DiscoverySession 通过 `DiscoveryIntentAnalyzer(llm_fn=...)` 注入（同 conversation 模式）;
  system_question 多轮合并边界 (v1.1.19) 直接复用, 不重写

## 2. DiscoverySession 集成点（discovery.py, 最小改动）

### 2.1 构造与懒装配（镜像 conversation._get_discovery_analyzer）

```python
def __init__(self, ..., analyzer: Optional[Any] = None):
    ...
    self._analyzer_override = analyzer          # 测试注入
    self._analyzer = _ANALYZER_UNSET            # 懒装配缓存
    self._last_system_question: str = ""        # 多轮字段合并边界 (v1.1.19 模式)
    self._ai_generated: bool = False            # LLM 真产出标记
    self._understanding: str = ""               # 理解摘要 (确认门展示)
    self._proactive: dict = {}                  # 主动分析 (确认门展示)
```

`_get_analyzer()`: override → 用之; 否则懒 `DiscoveryIntentAnalyzer()`; 装配失败/无 key → None
（None = 规则兜底, 现有行为逐字节不变 — 验收 3）。

### 2.2 `start()` — 初始描述即解析（验收 1 核心）

```
现有: 建 session + 第一问 (problem 模板)
新增: analyzer 可用 → analyze(idea)
  ├─ extraction 覆盖全部必填 → 填 product_intent → READY_FOR_CONFIRMATION
  │    消息 = 理解摘要 + to_text() + 建议名称候选 + 确认提示 (ai_generated=True)
  ├─ 部分覆盖 → 填已有字段, _pending_fields 只留真正缺失 → 智能追问 1 条
  │    (question + "(为什么还问: <missing_reasons>)" — 非机械第一问)
  └─ analyzer None/失败 → 现有第一问 (零变化)
```

### 2.3 `process_user_input(text)` — 回答轮

```
现有: 空答拒绝 → apply 当前字段 → 队列推进 → 追问/READY
新增: analyzer 可用 → analyze(text, system_question=_last_system_question)
  ├─ category=product_description → 提取合并 (只填缺失字段, 不覆盖已填 — v1.1.19 边界)
  │    ├─ 必填齐 → READY (理解摘要+主动建议+命名候选)
  │    └─ 仍缺 → 智能追问 (带理由)
  ├─ category=field_answer → 并入现有 apply 逻辑 (当前字段, 不覆盖其它)
  ├─ category=control → 取消类关键词 → cancel(); 其余 → 不当作字段, 重问当前问题
  ├─ category=query → 不当作字段, 重问当前问题 (模型层不逃生 — 逃生是驱动层职责)
  └─ analyzer None/失败 → 现有逻辑 (零变化)
```

### 2.4 确认门增强（build_summary / READY 消息 — 两路径摘要格式对齐, 验收 3）

```
现有 READY 消息: to_text() + "请确认产品需求 — 输入 y 确认创建 / n 重新描述 (或 /cancel 取消)"
对齐后 (ai_generated=True 时):
  {understanding}                                  ← "我理解你要做 X, 给 Y 用, 核心是 A/B/C" (首行)
  {to_text() 各行}
  建议名称: {name}
    {候选列表 1..N}                                  ← 复用 naming.suggest_names (LLM-gated)
  主动建议: 平台=.. · 竞品=.. · 范围=.. · 备注=..      ← proactive 非空时
  请确认产品需求 — 输入 y 确认创建 / n 重新描述 (或 /cancel 取消)
ai_generated=False → 现有消息逐字节不变 (零变化)
```

**命名决策（LLM-gated, 对齐的一部分）**: DiscoverySession 确认时若 name 是临时名 (is_temp_name) 且
analyzer 可用 → `suggest_names(raw/problem, llm_fn=analyzer 同一 llm_fn)` → 取候选 1 设名 + 展示候选
（与 conversation 一致）。无 LLM → 临时名保留（当前行为, 零变化）。此决策透明记录: 超出规格 6 项的
最小扩展, 服务于"两路径摘要格式对齐"（conversation 确认含建议名称, DiscoverySession 目前只有临时名）。

### 2.5 持久化（to_dict/from_dict）

- 新增字段: `_last_system_question` / `_ai_generated` / `_understanding` / `_proactive`
- from_dict 缺省兼容 (旧会话文件无新键 → 默认值, 不崩)

## 3. 字段集扩展明细（discovery_intelligence.py）

```python
EXTRACTION_FIELDS = ("problem", "user", "core_features", "name", "platform",
                     "usage_scenarios", "mvp_scope", "non_functional_requirements")
```
- prompt schema: extraction 对象加 3 键 + 规则行
- schema 归一化: 新键缺省补 "" (list 类 core_features 补 []); 不影响既有校验
- 单测: extraction 含新键 (mock 注入) + conversation 路径不受新键影响 (回归)

## 4. 契约测试要点（新增 tests/console/test_discovery_session_llm.py, mock 注入）

1. **LLM 一次产出**: mock extraction 全 7 字段 → `start("开始做个记账App")` → READY_FOR_CONFIRMATION
   直达, 消息含理解摘要 + 建议名称 (非"这个产品解决什么问题?"第一问)
2. **智能追问带理由**: 部分提取 (缺 user) → 追问 1 条含 "(为什么还问:" + 非机械
3. **回答并入不覆盖 (v1.1.19 边界)**: 对追问的回答 → field_answer → 只填对应字段, 已填不覆盖
4. **理解摘要 + 主动分析**: READY 消息含 "我理解你要做" + "主动建议:"
5. **无 LLM 零变化**: analyzer=None → start/process_user_input 行为与既有 108 tests 一致
   (既有测试零改动, 全部仍绿)
6. **控制/查询不当字段**: category=control(取消) → cancel; category=query → 不吞为字段
7. **非法 LLM 输出**: 非 JSON/schema 缺 → 规则兜底, 不崩溃
8. **持久化 round-trip**: 新字段 save/load 完整
9. **命名**: LLM 可用+临时名 → 候选设名; 无 LLM → 临时名保留

## 5. 版本与发布

- pyproject.toml `1.1.20` → `1.1.21`（patch+1）
- CHANGELOG.md v1.1.21 条目（中文, Keep a Changelog）
- 版本断言测试同步（test_s10_074_deployment.py 等）
- 全量回归: `env -u DEEPSEEK_API_KEY .venv/bin/python -m pytest tests/console tests/api -q` 0 新增失败

## 6. Codex 实施范围（Files / Allowed / Forbidden / Validation）

**Allowed/Files**:
- MOD `factory-console/session/discovery_intelligence.py`（§3 字段集扩展, 仅此）
- MOD `factory-console/session/discovery.py`（§2 LLM 集成）
- NEW `tests/console/test_discovery_session_llm.py`
- MOD pyproject.toml / CHANGELOG.md / 版本断言测试 / docs 版本引用

**Forbidden**:
- 改 conversation.py / naming.py / reasoning.py / product.py / intent.py / llm_intent.py（复用不重造）
- 改既有测试断言（版本号 1.1.20→1.1.21 除外）
- 动 exec/desktop/providers/部署/数据库; 新增第三方依赖
- **碰工作区他会话未提交改动 tests/console/test_console_cli.py**（git add 只加本 Sprint 文件, 禁 add -A）
- 禁止 stub/fake: 无 LLM 诚实规则兜底, 不伪造理解

**Validation（Codex 自测后提交）**:
- `.venv/bin/python -m pytest tests/console/test_discovery_session_llm.py -q` 全绿
- `env -u DEEPSEEK_API_KEY .venv/bin/python -m pytest tests/console/test_session_discovery.py tests/console/test_discovery_llm_intelligence.py tests/console/test_session_conversation.py -q` 既有 0 破
- `env -u DEEPSEEK_API_KEY .venv/bin/python -m pytest tests/console -q` 全量 0 新增失败
- commit message: `feat(S10-100): DiscoverySession 同步 LLM 化 — 复用 analyzer 一次产出/智能追问/理解摘要/主动分析, 规则兜底, v1.1.21`

## 7. 边界（不做）

- 不改 conversation 路径（已 LLM 化, 仅 analyzer 契约扩展对其透明）
- 不做驱动层逃生/控制指令接线（DiscoverySession 是模型层; 驱动/CLI 接线非本 Sprint）
- 不做多语言; 不改 DiscoverySession 既有状态机状态集/流转
- naming 仅 LLM-gated 最小接入（§2.4 透明决策）

## 8. 验收标准（Hermes 独立验证, 非 Codex 自报告）

- [ ] 真实 LLM: `DiscoverySession.start("开始做个记账App")` → 一次产出/智能追问 + 摘要（唯一真相）
- [ ] 无 LLM（env -u / analyzer=None）→ 逐字段零变化（与 v1.1.20 行为对照）
- [ ] 两路径摘要格式对齐: 理解摘要首行 + 建议名称 + 主动建议（LLM 时）
- [ ] 全量回归 0 新增失败 + 提交只含本 Sprint 文件
- [ ] 版本 v1.1.21
