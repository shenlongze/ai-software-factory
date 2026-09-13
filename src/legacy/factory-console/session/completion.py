"""factory-console/session/completion.py — Completion Framework (S10-047 Task 007)。

TAB 补全候选生成 — 只读, 无副作用 (S10-046 设计 §7 边界)。
设计: docs/sprint10/S10-046-completion-design.md (§2 数据源分层 / §3 实现架构 / §7 边界)

数据源分层 (设计 §2):
    Static Command Registry   — 命令/参数表 (本 Task: SlashCompletionProvider)
    Factory Registry          — projects/agents/skills JSON (未来: Project/Agent/Skill provider)
    Workspace                 — current project 内文件/目录 (未来: File provider)
    File System               — 路径补全, 通用 (未来)

组件:
- CompletionProvider (ABC)     — 补全接口: candidates(prefix, context) -> list[str]
  未来扩展点: FileCompletionProvider / ProjectCompletionProvider /
  AgentCompletionProvider / SkillCompletionProvider 实现同一接口后注册即可
- SlashCompletionProvider      — 命令补全 (Static 源): "/" → 全部 slash 命令;
  "/pr" → 过滤出 /project; 无匹配/非 slash 位置 → 空列表 (不报错)
- CompletionRegistry           — 提供者注册表: 按注册顺序聚合各源候选
  (去重 + 排序; 只读, 无副作用)

边界 (S10-046 §7):
- 补全只做"候选生成", 不执行任何操作
- 未知位置 → 无候选 (不报错)
- Registry 缺失 → 静默跳过该类补全
- 禁止: 补全触发副作用 (只读)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .context import SessionContext
from .slash import SlashCommandRegistry


class CompletionProvider(ABC):
    """补全提供者接口 (S10-046 §3 查源层) — 未来扩展的唯一切入点。

    未来数据源 (设计 §2) 均以同接口接入:
    - FileCompletionProvider     — Workspace / File System (文件路径补全)
    - ProjectCompletionProvider  — Factory Registry (projects.json)
    - AgentCompletionProvider    — Factory Registry (agents.json)
    - SkillCompletionProvider    — Factory Registry (skills.json)
    实现后经 CompletionRegistry.register() 注册, 单入口聚合候选。

    契约:
    - candidates(prefix, context) 只读生成候选; 无匹配/未知位置 → 空列表, 不抛错
    - 禁止副作用 (只读 — 设计 §7)
    """

    #: 数据源类型标识 (设计 §2: static-commands / factory-registry / workspace / fs)
    source: str = ""

    @abstractmethod
    def candidates(self, prefix: str, context: SessionContext) -> list[str]:
        """按前缀返回候选列表 (无匹配 → 空列表; 只读, 不执行任何操作)。"""


class SlashCompletionProvider(CompletionProvider):
    """命令补全 (Static Command Registry 数据源, 设计 §2 第一层)。

    数据源 = SlashCommandRegistry (命令表单一来源, 不硬编码 — 设计 §3);
    未注入 registry 时回退默认注册表 (与 commands.build_default_registry 同口径):
        "/"    → 全部注册命令 (如 /help /project /status /cost /exit)
        "/pr"  → 前缀过滤 → /project
        "/zz"  → 无匹配 → 空列表
        "pr"   → 非 slash 位置 → 空列表 (未知位置不报错 — 设计 §7)
    """

    source = "static-commands"

    def __init__(self, registry: Optional[SlashCommandRegistry] = None) -> None:
        #: 命令注册表 (None → 缺省构建默认注册表)
        self.registry = registry

    def _resolve_registry(self) -> SlashCommandRegistry:
        if self.registry is not None:
            return self.registry
        from .commands import build_default_registry  # 延迟导入 (completion 为叶模块)

        return build_default_registry()

    def candidates(self, prefix: str, context: SessionContext) -> list[str]:
        text = (prefix or "").strip()
        if not text.startswith("/"):
            return []  # 非 slash 位置 → 无候选 (不报错)
        name = text[1:].strip().lower()
        names = [cmd.name for cmd in self._resolve_registry().list()]
        return sorted({f"/{n}" for n in names if n.startswith(name)})


class CompletionRegistry:
    """补全提供者注册表 (设计 §2 分层聚合): 按注册顺序聚合各源候选。

    未来扩展: 注册 File/Project/Agent/Skill provider 后, 单入口聚合
    (前缀过滤 + 去重 + 排序 — 设计 §6 候选排序: 字母序兜底)。
    """

    def __init__(self) -> None:
        self._providers: list[CompletionProvider] = []

    def register(self, provider: CompletionProvider) -> CompletionProvider:
        """注册补全提供者 (顺序 = 聚合顺序; 返回 provider 便于链式)。"""
        self._providers.append(provider)
        return provider

    def providers(self) -> list[CompletionProvider]:
        """已注册提供者 (快照副本, 防外部篡改)。"""
        return list(self._providers)

    def candidates(self, prefix: str, context: SessionContext) -> list[str]:
        """聚合全部提供者候选: 去重 + 字母序 (只读, 无副作用)。"""
        out: list[str] = []
        for provider in self._providers:
            out.extend(provider.candidates(prefix, context))
        return sorted(set(out))
