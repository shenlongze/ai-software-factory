"""factory-console/external_executor/registry.py — 外部执行器适配器注册表 (M1)。

设计依据: 设计文档 §3/§5. 加载 <data_dir>/external-ais/*.yaml + 内置模板
(codex/claude/hermes — 预装, 与用户新增同构)。引擎不依赖产品名, 只依赖
适配器 Schema。

- list()/get(id)/save(adapter)/remove(id)
- save 写 <data_dir>/external-ais/<id>.yaml (WebUI 表单编辑落盘)
- 校验失败 (缺字段/非法) → 明确报错, 不猜测不降级
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .schema import ExternalExecutorAdapter, adapter_from_yaml

#: 内置模板 (预装; 与用户新增同构 — 本设计"每产品一个适配器"的铁律)
BUILTIN_ADAPTERS: dict[str, dict[str, Any]] = {
    "codex": {
        "id": "codex",
        "name": "本机 Codex",
        "binary": "codex",
        "discovery": ["PATH", "~/.local/bin", "~/.codex/bin", "/opt/homebrew/bin"],
        "version_probe": ["--version"],
        "probe_help": ["exec", "--help"],
        "invocation": {
            "non_interactive": [
                "exec", "-C", "{project_dir}", "--skip-git-repo-check",
                "--sandbox", "workspace-write", "{prompt}",
            ],
            "project_dir": "flag:-C",
            "agent_flag": None,
            "skills_flag": None,
            "timeout": 900,
        },
        "host_assets": {
            "agents": {"dir": "~/.codex/agents", "glob": "*.toml", "format": "toml",
                       "fields": {"name": "name", "description": "description",
                                  "prompt": "developer_instructions"}},
            "skills": {"dir": "~/.codex/skills", "glob": "*", "format": "skill-md"},
            "plugins": {"dir": "~/.codex/plugins/cache", "glob": "*", "format": "dirs"},
        },
        "capabilities": {"roles": ["developer", "reviewer", "architect"], "agents": True,
                         "skills": True, "cost_tier": "medium"},
    },
    "claude": {
        "id": "claude",
        "name": "本机 Claude",
        "binary": "claude",
        "discovery": ["PATH", "~/.local/bin", "/opt/homebrew/bin"],
        "version_probe": ["--version"],
        "probe_help": ["--help"],
        "invocation": {
            "non_interactive": ["-p", "--output-format", "text", "{prompt}"],
            "project_dir": "cwd",
            "agent_flag": ["--agent", "{agent}"],
            "skills_flag": None,
            "timeout": 900,
        },
        "host_assets": {
            "agents": {"dir": "~/.claude/agents", "glob": "*.md", "format": "md-frontmatter",
                       "fields": {"name": "name", "description": "description",
                                  "prompt": "body"}},
            "skills": {"dir": "~/.claude/skills", "glob": "*", "format": "skill-md"},
        },
        "capabilities": {"roles": ["developer", "reviewer", "architect"], "agents": True,
                         "skills": True, "cost_tier": "medium"},
    },
    "hermes": {
        "id": "hermes",
        "name": "本机 Hermes",
        "binary": "hermes",
        "discovery": ["PATH", "~/.local/bin", "/opt/homebrew/bin"],
        "version_probe": ["--version"],
        "probe_help": ["--help"],
        "invocation": {
            "non_interactive": ["-z", "{prompt}"],
            "project_dir": "cwd",
            "agent_flag": None,
            "skills_flag": None,
            "timeout": 900,
        },
        "host_assets": {
            "skills": {"dir": "~/.hermes/skills", "glob": "*", "format": "skill-md"},
            "persona": {"path": "~/.hermes/SOUL.md"},
        },
        "capabilities": {"roles": ["developer"], "agents": False,
                         "skills": True, "cost_tier": "medium"},
    },
}


class ExternalExecutorRegistry:
    """适配器注册表: 内置模板 + <data_dir>/external-ais/*.yaml (用户新增/覆盖)。"""

    def __init__(self, data_dir: str | Path, *, builtin: bool = True) -> None:
        self._dir = Path(data_dir) / "external-ais"
        self._adapters: dict[str, ExternalExecutorAdapter] = {}
        if builtin:
            for aid, spec in BUILTIN_ADAPTERS.items():
                self._adapters[aid] = ExternalExecutorAdapter(**spec)
        self._load_dir()

    @property
    def dir(self) -> Path:
        return self._dir

    def _load_dir(self) -> None:
        """用户 yaml 覆盖内置 (同 id 覆盖; 新增 id 追加)。"""
        if not self._dir.is_dir():
            return
        for f in sorted(self._dir.glob("*.yaml")):
            try:
                adapter = adapter_from_yaml(f.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 — 单个损坏 → 跳过 (不拖垮注册表)
                continue
            self._adapters[adapter.id] = adapter

    def list(self) -> list[ExternalExecutorAdapter]:
        return [self._adapters[a] for a in sorted(self._adapters)]

    def get(self, adapter_id: str) -> ExternalExecutorAdapter | None:
        return self._adapters.get(adapter_id)

    def save(self, adapter: ExternalExecutorAdapter) -> ExternalExecutorAdapter:
        """写 <data_dir>/external-ais/<id>.yaml (新增或覆盖; 内置也可被覆盖)。"""
        self._dir.mkdir(parents=True, exist_ok=True)
        (self._dir / f"{adapter.id}.yaml").write_text(
            adapter.to_yaml(), encoding="utf-8"
        )
        self._adapters[adapter.id] = adapter
        return adapter

    def remove(self, adapter_id: str) -> bool:
        """删除用户 yaml (内置模板不可删, 只能覆盖)。"""
        f = self._dir / f"{adapter_id}.yaml"
        if not f.is_file():
            return False
        f.unlink()
        self._adapters.pop(adapter_id, None)
        return True


def build_registry(data_dir: str | Path) -> ExternalExecutorRegistry:
    return ExternalExecutorRegistry(data_dir)
