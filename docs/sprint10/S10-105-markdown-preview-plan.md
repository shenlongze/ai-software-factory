# S10-105 — CLI Markdown 渲染 + /preview + 多行输入：实现计划（CTO 架构设计 + Codex 指令）

> 日期: 2026-08-24 | 前置: v1.1.25 · 产品发现/确认链已验收 (S10-099~104)
> 用途: 三部门循环第 ②→③ 步 — Hermes(CTO) 架构设计 → Codex(工程) 实现
> 规格来源: docs/sprint10/S10-105 提示词（3 项 CLI 能力）

---

## 0. 现状审计（CTO 实测确认）

| 项 | 现状 |
|---|---|
| rich | **已安装** (可 import) — 未使用 |
| prompt_toolkit | **未安装** → 多行输入走"简单检测 + input() 降级" |
| 会话输出 | session.py 直接 print: chat 回答 (L281/321, LLM 输出常含 markdown), action 结果 (L345 renderer), 产品流消息 (L270/288) |
| PRD 内容 | 落盘 projects/<slug>/PRD.md; 会话只显示路径, 无预览能力 |
| slash 注册表 | commands.py build_default_registry, 注册式 (register 一行); ExitCommand(session=) 注入模式 |

基线: console+api 5030 passed / 1 skipped / 0 failed。

## 1. 架构决策

### 1.1 会话 Markdown 渲染（renderer.py + session.py, 保守启发式）

**renderer.py 新增（纯函数 + 一个输出助手）**:

```python
def looks_like_markdown(text: str) -> bool:
    # 强 markdown 信号 (保守 — 只有真文档才触发, 普通消息零影响):
    #   含 ``` 代码围栏  |  任一行 ^#{1,6} 标题  |  任一行含 | 表格
    # 列表标记(-/1.) 不算 — 发现流程建议/进度消息含编号列表, 保持纯文本 (验收: 非 markdown 纯文本不变)

def render_message(text: str) -> None:
    # rich 可 import 且 looks_like_markdown → Console().print(Markdown(text))
    # 否则 → print(text) 原样 (诚实降级; 非终端 rich 自动去 ANSI, 测试输出仍可断言)
```

**session.py 接入**: 用户面消息 print 点替换为 render_message:
- L281/L321 (chat 回答 — LLM markdown 主场景)
- L345 (action 结果 renderer 输出 — PRD/管线文档类)
- L270/L288 (产品流消息 — 启发式保守, 普通发现/确认消息无标题/表格/围栏 → 原样, 零变化)
- 错误/退出/分隔线等 (L194/198/307/329/334/337/424) 不接 (保持原样)

rich 降级: import 失败 → print 原样 (验收: 无 rich 诚实降级)。

### 1.2 /preview 命令（commands.py 注册式）

```python
class PreviewCommand(SlashCommand):
    name = "preview"
    description = "渲染显示 markdown 文件 (/preview PRD.md)"
    def execute(self, args: str, context: SessionContext) -> int:
        # 1. 无参数 → 用法提示 (rc 2)
        # 2. 路径解析: 绝对路径 → 直接用; 相对 → 依次尝试 cwd / context.workspace /
        #    context.current_project 目录 / data_dir/projects/<slug>/PRD.md (slug=current_project)
        # 3. 文件不存在/读失败 → 友好错误 (rc 2, 不崩溃)
        # 4. 读取内容 → render_message(content) (markdown 自动 rich 渲染; 非 md 原样打印)
```
- build_default_registry 注册 `registry.register(PreviewCommand())` (上下文经 execute(context) 已有)
- 未来 HTML 导出: 本 Sprint 只渲染显示 (边界)

### 1.3 多行输入（prompt_toolkit 缺失 → 简单检测 + input() 降级）

**session.py run() 输入循环**:

```python
def _read_input_line(self, prompt: str) -> str:
    """多行输入 (简单检测): 行尾 '\\' → 续行 (提示 '… '), 直到无 '\\'; 拼接 \\n。
    prompt_toolkit 缺失 → input() 降级 (诚实, 验收: 无 prompt_toolkit 降级)。"""
    line = input(prompt)
    if not line.endswith("\\"):
        return line
    parts = [line.rstrip("\\")]
    while True:
        more = input("… ")
        if not more.endswith("\\"):
            parts.append(more)
            break
        parts.append(more.rstrip("\\"))
    return "\n".join(parts)
```
- run() 的 `line = input(self.prompt)` → `line = self._read_input_line(self.prompt)`
- 拼接结果进入既有 _dispatch 流程 (多行需求作为一条输入 — 产品描述/字段答案天然支持 \n)
- prompt_toolkit 完整增强 → backlog (边界)

## 2. 契约测试要点

新增 `tests/console/test_s10_105_markdown_preview.py`:

1. **looks_like_markdown**: 标题/表格/围栏 → True; 进度消息/建议列表/纯文本 → False
2. **render_message**: markdown → rich 渲染 (输出含处理后的文本, 非 ANSI 断言用 in); 纯文本 → 原样
3. **rich 缺失降级**: monkeypatch import → print 原样 (不崩)
4. **/preview**: 有参渲染 / 无参 rc2 / 文件不存在 rc2 友好错误 / 非 md 文件原样
5. **多行输入**: mock input "line1\\","line2","x" → 拼接 "line1\nline2"; 单行不受影响
6. **chat 回答渲染**: markdown 回答经 render_message (捕获输出含渲染文本)
7. **非 markdown 消息零变化**: 发现/确认消息输出与渲染前一致 (关键: 不引入 ANSI/变形)
8. 全量回归 0 新增; 版本 v1.1.26

## 3. 版本与发布

- pyproject.toml `1.1.25` → `1.1.26`; CHANGELOG v1.1.26; 版本断言同步; docs

## 4. Codex 实施范围

**Allowed/Files**:
- MOD `factory-console/session/renderer.py` (looks_like_markdown + render_message, rich 可选导入)
- MOD `factory-console/session/session.py` (print 点接入 + _read_input_line)
- MOD `factory-console/session/commands.py` (PreviewCommand + 注册)
- NEW `tests/console/test_s10_105_markdown_preview.py`
- MOD pyproject.toml / CHANGELOG.md / 版本断言 / docs

**Forbidden**:
- 改 naming.py / reasoning.py / product.py / intent.py / llm_intent.py; 改状态机状态集
- 动 exec/desktop/providers/部署/数据库; 新增第三方依赖 (**rich 已装, 只 import, 不加依赖**)
- 禁 git add -A — 工作区有他会话未提交 tests/console/test_console_cli.py, 绝不扫入
- 不做 Web 富文本/完整编辑器 / prompt_toolkit 完整增强 (backlog)
- 禁 stub/fake: rich/prompt_toolkit 缺失必须真实降级

**Validation**:
- `pytest tests/console/test_s10_105_markdown_preview.py -q` 全绿
- env -u 聚焦 (session + commands + renderer + conversation) 全绿
- env -u 全量 console 0 新增失败
- 实测: 会话中 LLM markdown 回答渲染可读; /preview PRD.md 渲染; 多行续行拼接; rich 缺失不崩
- commit: `feat(S10-105): CLI Markdown 渲染(rich) + /preview 命令 + 多行输入(续行检测, input降级), v1.1.26`

## 5. 边界（不做）

- Web 富文本 / 完整编辑器 → backlog; prompt_toolkit 完整增强 → backlog; /preview HTML 导出 → 未来
- 非交互 CLI 命令输出不加渲染 (仅会话 REPL 层)

## 6. 验收标准（Hermes 独立验证）

- [ ] PRD/文档输出 rich 渲染可读（会话层）
- [ ] /preview 渲染 + 错误路径 (无参/文件不存在)
- [ ] 多行输入正确处理 (续行拼接)
- [ ] 无 rich/prompt_toolkit 诚实降级
- [ ] 非 markdown 纯文本不变
- [ ] 全量回归 0 新增失败 + 版本 v1.1.26
