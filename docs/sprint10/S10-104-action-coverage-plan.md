# S10-104 — 确认阶段 next_action 全覆盖 + 会话分割线 + 删除指令：实现计划（CTO 架构设计 + Codex 指令）

> 日期: 2026-08-24 | 前置: v1.1.24 · S10-102/103 确认分流与命令分流已验收
> 用途: 三部门循环第 ②→③ 步 — Hermes(CTO) 架构设计 → Codex(工程) 实现
> 规格来源: docs/sprint10/S10-104 提示词（Founder 实测 3 问题）

---

## 0. 现状审计（CTO 实测确认）

| 问题 | 根因（代码定位） |
|---|---|
| 🔴 "产出份prd文档"/"生成PRD"/"出个html"/"出份功能清单" → 被当改名 | S10-102 APPROVE_NEXT_ACTIONS 只匹配"首段确认词+动作关键词"（"可以,先出X"式）; 无确认前缀的动作短语漏到改名兜底 |
| 🟡 多轮回复无分割线 | session.run() 循环无分隔输出 |
| 🟡 删除/清空字段未实现 | 确认阶段"把核心功能删掉"无分流 → 改名兜底 |

现状: handle_product_confirm 顺序 = _product_control → _command_escape → RENAME_RE → 确认+下一步 → 纯确认 → 澄清 → 委托 → LLM → 改名兜底。基线: console+api 4991 passed / 1 skipped / 0 failed。

## 1. 架构决策

### 1.1 next_action 表达全覆盖（🔴）

**类型词汇**: `next_action ∈ {prd, feature_list, html, docs}`（会话响应携带; 宿主仅 prd 真正执行, 其余记信号 — 产出引擎 backlog）

**discovery_guide.py — 动作短语规则补全（确定性, 无确认前缀也命中）**:

```python
#: next_action 动作直接短语 (正则, 无确认前缀 — "生成PRD"/"产出份prd文档"/"出个html"/"出份功能清单")
DIRECT_ACTION_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("prd",           (r"生成\s*prd", r"产出.*prd", r"出.*prd", r"写.*prd", r"prd")),
    ("feature_list",  (r"功能清单", r"出.*清单", r"清单")),
    ("html",          (r"出.*html", r"生成.*html", r"做.*页面", r"html")),
    ("docs",          (r"文档", r"说明书", r"docs")),
)
def match_direct_action(norm: str) -> Optional[str]:
    # 返回首个命中的 action_id; 大小写不敏感 (lower)
```

**顺序（handle_product_confirm）**: RENAME_RE（"改名叫X" 不变, 最优先防 "改名叫prd" 被动作规则抢）→ **DIRECT_ACTION（新增）** → 确认+下一步 → 纯确认 → 澄清 → **删除指令（新增, §1.3）** → 委托 → LLM → 改名兜底。

**LLM 分类为主**: `analyze_confirmation` prompt 更新 — next_action 词汇表 {prd/feature_list/html/docs} + 变体示例
（"生成PRD"/"产出份prd文档"/"出个html"/"出份功能清单" → approve_next + next_action）;
approve_next 允许无确认前缀（纯动作请求 = 隐含确认 + 下一步）。

**宿主**: session.py — next_action=="prd" → generate_prd（既有）; feature_list/html/docs →
消息追加 `"\n[已记录] 将生成{label} — 产出引擎 backlog"`（不阻断创建）。

### 1.2 会话分割线（🟡, 纯装饰）

- session.py: `SEPARATOR = "─" * 46`
- run() 循环: `_dispatch(cmd)` 之后 `print(SEPARATOR)`（每轮回复间; 退出/空输入路径不打印）
- 只影响 InteractiveSession REPL 输出; 非交互 CLI 命令不受影响
- 测试: 捕获输出的断言按新输出更新（注释原因）

### 1.3 删除/清空字段（🟡）

**确定性规则（conversation.py, 复用 _EDIT_FIELD_ALIASES）**:

```python
#: 删除/清空指令 (两序: "把核心功能删掉" / "清空核心功能"; 复用 _EDIT_FIELD_ALIASES 别名)
def _parse_delete_command(text: str) -> Optional[str]:
    # 命中 → 返回字段名 (problem/user/core_features/name/platform)
    # 模式: (把|将)?(别名)(删除|删掉|清空|去掉|移除|不要)  |  (清空|删除|删掉|去掉|移除)(别名)
```

**行为**: 命中且字段有值 → 清空（core_features → []; 其余 → ""）→ 若为必填字段 → 迁移 DISCOVERY + pending=[field] +
追问该字段（机械/智能）; 可选字段/已确认后 → 重进确认（_enter_product_confirmation, 摘要更新）。
**绝不当改名**（验收 3）。handle_product_answer 同步支持（字段收集期"清空X" → 重问）。

### 1.4 DiscoverySession

- 不改（DS 确认是模型级 confirm(), 无输入分流; 删除/动作短语不适用; 分割线是 REPL 层）

## 2. 契约测试要点

新增 `tests/console/test_s10_104_action_coverage.py`（或并入确认测试）:

1. **"产出份prd文档"** → approved + next_action="prd" + 名称不被覆盖（验收 1）
2. **"生成PRD" / "出个html" / "出份功能清单"** → next_action 分别 prd/html/feature_list + 名称不变
3. **"改名叫X"** → 仍走改名（验收 2, 不被动作规则抢）
4. **分割线**: InteractiveSession 两轮输出间含 SEPARATOR（验收 3）
5. **"把核心功能删掉"** → core_features 清空 → 重进确认/追问（验收 4）; "清空目标用户" 同; 名称字段"把名字删掉"→ 临时名?
6. **无 LLM 规则兜底**: env -u 下 1/2/3/5 全过
7. **LLM**: mock analyze_confirmation 变体 → approve_next + 各 next_action 路由
8. **宿主**: next_action="prd" → PRD 执行; "html"/"feature_list" → 信号注释
9. 全量回归 0 新增; 版本 v1.1.25

## 3. 版本与发布

- pyproject.toml `1.1.24` → `1.1.25`; CHANGELOG v1.1.25; 版本断言同步; docs

## 4. Codex 实施范围

**Allowed/Files**:
- MOD `factory-console/session/discovery_guide.py` (DIRECT_ACTION_PATTERNS + match_direct_action)
- MOD `factory-console/session/discovery_intelligence.py` (analyze_confirmation next_action 词汇 + 变体示例)
- MOD `factory-console/session/conversation.py` (DIRECT_ACTION 接入 + 删除指令 + next_action 词汇)
- MOD `factory-console/session/session.py` (SEPARATOR + 宿主 next_action 信号)
- NEW `tests/console/test_s10_104_action_coverage.py` (+ 既有测试按新输出更新, 注释原因)
- MOD pyproject.toml / CHANGELOG.md / 版本断言 / docs

**Forbidden**:
- 改 naming.py / reasoning.py / product.py / intent.py / llm_intent.py; 改状态机状态集
- 动 exec/desktop/providers/部署/数据库; 新增第三方依赖
- 禁 git add -A — 工作区有他会话未提交 tests/console/test_console_cli.py, 绝不扫入
- 不做 prompt_toolkit / feature_list 产出引擎（backlog）
- 禁 stub/fake: 动作/删除规则纯确定性; LLM 只做补充分类

**Validation**:
- `pytest tests/console/test_s10_104_action_coverage.py -q` 全绿
- env -u 聚焦 (conversation + session + confirm + cli) 全绿
- env -u 全量 console 0 新增失败
- 实测: "产出份prd文档" → next_action + 名称不变; "改名叫X" 改名; 分割线出现; "把核心功能删掉" → 清空重确认
- commit: `feat(S10-104): 确认阶段 next_action 全覆盖(prd/feature_list/html/docs) + 会话分割线 + 删除/清空字段指令, v1.1.25`

## 5. 边界（不做）

- prompt_toolkit → backlog; feature_list/html/docs 产出引擎 → backlog（本 Sprint 只传信号）
- DS 模型层不改; 非交互 CLI 输出不加分割线

## 6. 验收标准（Hermes 独立验证）

- [ ] "产出份prd文档" → next_action + 名称不被覆盖
- [ ] "改名叫X" 仍走改名
- [ ] 每轮有分割线
- [ ] "把核心功能删掉" → 清空重确认
- [ ] 无 LLM 规则兜底
- [ ] 全量回归 0 新增失败 + 版本 v1.1.25
