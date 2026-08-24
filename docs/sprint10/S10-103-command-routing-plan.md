# S10-103 — 发现流程命令分流 + CLI 输入健壮性：实现计划（CTO 架构设计 + Codex 指令）

> 日期: 2026-08-24 | 前置: v1.1.23 · S10-099~102 产品发现链已验收
> 用途: 三部门循环第 ②→③ 步 — Hermes(CTO) 架构设计 → Codex(工程) 实现
> 规格来源: docs/sprint10/S10-103 提示词（CLI 全面检查）

---

## 0. 现状审计（CTO 实测确认）

| 现象 | 根因（代码定位） |
|---|---|
| 🔴 发现中 "/status" 不执行且死胡同 | conversation.handle() 顶部 slash 分支返回 message="slash 命令由命令注册表处理" (needs_input=False, **非 passthrough**) → 宿主只打印不重分发 |
| 🔴 发现中 "exit" 被当字段 | `handle_product_answer("exit")` → problem="exit"（模型层无 exit 分流; 生产 REPL 的 run() 顶部 EXIT 检查恰好掩盖, 但直接使用 conversation 模型/未来宿主会踩） |
| 🔴 确认中 slash/exit 同样问题 | `handle_product_confirm` 无 slash/exit 分流 |
| 🟡 project 提示漏 status | `cli_factory.py project_cmd` line 2627: "错误: project 需要子命令 (create / list / rename)" — 缺 status |
| 🟡 create project 不强制 --name | `cli_factory.py create_cmd` project 分支 (line 2654) 只查 repo_path, 无 --name 校验 |

已排除: 异常输入 12/12 不崩 · readline 可用。基线: console+api 4970 passed / 1 skipped (唯一失败 m3e flaky 复跑通过)。

## 1. 架构决策

### 1.1 共享 EXIT_COMMANDS（discovery_guide.py — 单一来源, 避免循环导入）

```python
#: 退出命令集 (S10-103: 与 session.EXIT_COMMANDS 同源; conversation 不能 import session — 循环)
EXIT_COMMANDS: frozenset[str] = frozenset({"exit", "quit", "退出", "退出会话", "再见", "拜拜", "结束"})
```
- session.py: 本地定义改为 `from .discovery_guide import EXIT_COMMANDS`（集合内容不变, 既有测试不受影响）
- conversation.py: 从 discovery_guide 导入（无循环）

### 1.2 conversation.py — 命令分流（确定性, 字段收集之前, 两路径）

ConversationResponse += `exit_requested: bool = False`

```python
def _command_escape(self, text: str) -> Optional[ConversationResponse]:
    """命令分流 (S10-103): slash → passthrough; exit/quit → exit_requested。
    确定性 (不依赖 LLM); 与控制指令并列, 在字段收集之前。"""
    norm = str(text or "").strip()
    if norm.startswith("/"):
        return ConversationResponse(state=self.state, message="", needs_input=True, passthrough=True)
    if norm in EXIT_COMMANDS:
        return ConversationResponse(state=self.state, message="", needs_input=False, exit_requested=True)
    return None
```

**接入点（顺序关键 — 向后兼容）**:
- `handle_product_answer` / `handle_product_confirm`: 在 `_product_control()` 之后、字段收集之前:
  `cmd = self._command_escape(raw); if cmd is not None: return cmd`
  - 顺序原因: "退出" 同时在 _PRODUCT_CANCEL_PHRASES (取消发现) 与 EXIT_COMMANDS —
    _product_control 先处理 → "退出" 仍=取消发现 (向后兼容); 剩余 exit/quit/再见/退出会话 → exit_requested
- `handle()`: 顶部 slash 分支改为 `passthrough=True`（宿主重分发, 不再死胡同消息）;
  产品流程前加 EXIT 检查 → exit_requested

### 1.3 宿主接线（session.py）

- `_dispatch` 产品流分支 (line 228-236): 
  - passthrough → `self._dispatch(line)` — 已存在, slash 经此重分发 → registry.execute ✓
  - 新增: `exit_requested` → `print("已退出会话 — 再见!"); self.running = False; return`
- run() 循环不变 (EXIT_COMMANDS 已在顶部拦截)

### 1.4 CLI 小修（cli_factory.py, 🟡）

1. `project_cmd` 无子命令提示 (line 2627): "(create / list / rename)" → "(create / list / rename / status)"
2. `create_cmd` project 分支 (line 2654): 加 `--name` 校验 —
   `if not getattr(args, "project_name", None) and not getattr(args, "name", None):`
   `print("错误: create project 需要 --name <项目名>", file=sys.stderr); return 2`
   （字段名以 argparse 实际参数名为准 — Codex 实现时对照 _proxy_org_cli/register 参数）

## 2. 契约测试要点

新增 `tests/console/test_s10_103_command_routing.py`（或并入既有会话测试）:

1. **发现中 "/status"** → passthrough=True + problem 不被填（handle_product_answer 与 handle() 两入口）
2. **发现中 "exit"/"quit"** → exit_requested=True + problem 不被填
3. **确认中 slash/exit** → 同样分流（handle_product_confirm）
4. **"退出"** → 仍取消发现（向后兼容, 非退出会话）
5. **普通字段答案** → 不受影响（字段收集正常）
6. **宿主级**: InteractiveSession 产品流中 "/status" → registry 执行（/status 输出）; "exit" → running=False
7. **handle() slash** → passthrough（不再死胡同消息）
8. **CLI**: `factory project`（无子命令）提示含 status; `factory create project`（无 --name）→ rc 2
9. 全量回归 0 新增; 版本 v1.1.24

## 3. 版本与发布

- pyproject.toml `1.1.23` → `1.1.24`; CHANGELOG v1.1.24; 版本断言同步; docs

## 4. Codex 实施范围

**Allowed/Files**:
- MOD `factory-console/session/discovery_guide.py` (EXIT_COMMANDS 单一来源)
- MOD `factory-console/session/conversation.py` (_command_escape + 两路径接入 + handle() 改造 + exit_requested)
- MOD `factory-console/session/session.py` (EXIT_COMMANDS 改 import + exit_requested 宿主处理)
- MOD `factory-console/cli_factory.py` (project 提示 + create --name 校验) — ⚠️ 该文件有他会话曾改动, 提交前确认工作区状态
- NEW `tests/console/test_s10_103_command_routing.py` (+ 既有测试按新行为更新, 注释原因)
- MOD pyproject.toml / CHANGELOG.md / 版本断言 / docs

**Forbidden**:
- 改 naming.py / reasoning.py / product.py / intent.py / llm_intent.py; 改状态机状态集
- 动 exec/desktop/providers/部署/数据库; 新增第三方依赖
- 禁 git add -A — 工作区有他会话未提交 tests/console/test_console_cli.py, 绝不扫入
- 禁 stub/fake: 命令分流纯确定性, 不依赖/不伪造 LLM

**Validation**:
- `pytest tests/console/test_s10_103_command_routing.py -q` 全绿
- env -u 聚焦 (conversation + session + discovery + cli) 全绿
- env -u 全量 console 0 新增失败
- 实测: 发现中 "/status" → 状态输出; "exit" → 退出; 确认中同; `factory project` 提示含 status;
  `factory create project` 无 --name → rc 2
- commit: `feat(S10-103): 发现流程命令分流(slash→passthrough/exit→退出, 两路径) + CLI小修(project提示status/create --name必填), v1.1.24`

## 5. 边界（不做）

- prompt_toolkit 交互升级 → backlog; 会话历史持久化 → backlog
- 其它 CLI 行为/命令不改; DS (DiscoverySession) 模型层无 REPL 命令概念, 不改
- "退出" 语义保持取消发现 (向后兼容), 不改为退出会话

## 6. 验收标准（Hermes 独立验证）

- [ ] 发现中 "/status" → 显示状态不当字段（模型层 passthrough + 宿主 registry 执行）
- [ ] "exit" → 退出（模型层 exit_requested + 宿主 running=False）
- [ ] 确认中 slash 同样分流
- [ ] project 提示含 status; create project 无 --name → rc 2
- [ ] 字段收集正常 + 全量回归 0 新增失败
- [ ] 版本 v1.1.24
