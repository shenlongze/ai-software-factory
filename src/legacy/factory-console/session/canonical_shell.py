"""factory-console/session/canonical_shell.py — AI Factory OS Shell (Canonical Entry).

R0 P0: 裸 `factory` 默认进入本 Shell → CanonicalGoldenPath (Application Orchestrator)
→ Conversation Application → Product Understanding → Golden Path → Production Runtime。

本文件是表现层 REPL, 不含业务逻辑; 业务走 factory_console.canonical_golden_path。
"""
from __future__ import annotations

from pathlib import Path

from factory_console.canonical_golden_path import CanonicalGoldenPath

BANNER = (
    "AI Factory OS — Canonical Shell (R0)\n"
    "自然语言优先: 直接说你想做什么。\n"
    "斜杠命令: /help /status /new /exit"
)

HELP = (
    "你直接输入自然语言即可, 例如:\n"
    "  「我想做一个飞机大战小游戏, 可以在浏览器运行」\n"
    "系统会持续理解 → 澄清 → 形成 Product Understanding → PRD → 计划 → 生产。\n"
    "生命周期自然语言: 整理成 PRD / 就按这个做 / 生成计划 / 确认计划 / 开始做\n"
    "斜杠命令: /help /status /plan /new /exit"
)


def _default_root() -> Path:
    try:
        from factory_console.config import ConfigProvider

        return Path(str(ConfigProvider().get_data_dir()))
    except Exception:  # noqa: BLE001 — 配置读取失败 → 默认 ~/.factory
        return Path.home() / ".factory"


class CanonicalShell:
    """AI Factory OS Shell — 表现层 REPL (无业务逻辑)。"""

    def __init__(self, root: str | Path | None = None,
                 orchestrator: CanonicalGoldenPath | None = None) -> None:
        self.root = Path(root) if root is not None else _default_root()
        self.orchestrator = (
            orchestrator if orchestrator is not None
            else CanonicalGoldenPath(self.root, semantic=True,
                                     real_executor=True)
        )
        self.conversation_id: str | None = None
        self.running = False

    # ------------------------------------------------------------- REPL
    def run(self) -> int:
        print(BANNER)
        self.running = True
        while self.running:
            try:
                line = input("You > ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            cmd = line.strip()
            if not cmd:
                continue
            if cmd in ("exit", "quit", "/exit", "/quit", "退出"):
                print("已退出 — 再见!")
                break
            if cmd == "/help":
                print(HELP)
                continue
            if cmd == "/new":
                self._new()
                continue
            if cmd == "/status":
                self._status()
                continue
            if cmd == "/plan":
                self._plan()
                continue
            self._handle(cmd)
        return 0

    # ------------------------------------------------------------- 动作
    def _new(self) -> None:
        conv = self.orchestrator.create_conversation(title="AI Factory OS 会话")
        self.conversation_id = conv["id"]
        print(f"已创建新会话 {conv['id']} — 直接说你想做什么。")

    def _status(self) -> None:
        if self.conversation_id is None:
            print("还没有会话 — 直接说你想做什么即可自动开始。")
            return
        st = self.orchestrator.status(self.conversation_id)
        print(st["understanding"])
        print(f"\n当前阶段: {st['stage']}")

    def _plan(self) -> None:
        """/plan — 当前 Plan 多级任务树摘要 (层/叶/关键路径/degraded)。"""
        if self.conversation_id is None:
            print("还没有会话 — 先描述你想做什么。")
            return
        tree = self.orchestrator.plan_tree(self.conversation_id)
        if not tree or not tree.get("exists", False):
            print("还没有任务树 — 确认 PRD 并「生成计划」后可见。")
            return
        print("任务树:")
        print(f"  goal: {tree.get('goal', '')[:80]}")
        print(f"  节点 {tree.get('node_count', 0)} · 叶 {tree.get('leaf_count', 0)}"
              f" · 层 {tree.get('depth', 0)}"
              f"{' · ⚠️ 模板降级' if tree.get('degraded') else ''}")
        for d in tree.get("domains", []):
            print(f"  - {d}")
        cp = tree.get("critical_path") or []
        if cp:
            print(f"  关键路径: {len(cp)} 叶")
        print("输入「就按这个做」确认 PRD /「确认计划」确认 Plan 后开始执行。")

    def _handle(self, text: str) -> None:
        try:
            if self.conversation_id is None:
                conv = self.orchestrator.create_conversation(title="AI Factory OS 会话")
                self.conversation_id = conv["id"]
            res = self.orchestrator.handle(self.conversation_id, text)
        except Exception as exc:  # noqa: BLE001 — REPL 不崩溃
            print(f"⚠️ {exc}")
            return
        reply = res.get("reply") or ""
        if reply:
            print(reply)
        stage = res.get("stage")
        if stage and res.get("kind") in ("chat", "lifecycle"):
            print(f"\n[{stage}]")
        if res.get("kind") == "gate":
            print("(Gate 未通过 — 系统不会自动批准或自动执行。)")


__all__ = ["CanonicalShell"]
