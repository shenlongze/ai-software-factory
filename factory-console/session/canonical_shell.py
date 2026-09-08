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
    "斜杠命令: /status 当前阶段 · /new 新会话 · /exit 退出"
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
