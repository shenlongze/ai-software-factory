"""factory-console/session/agent_registry.py — 工厂层专家注册表 (M2 A2, S10-087)。

薄包装 (复用 session/agents.py AgentRegistry.load 模式 + core/agents/registry.py
口径): 工厂层 AgentEntity 注册表 — add/get/list/remove + 行业命名空间
(it.* / ops.*) + agents.json 持久化。

契约 (S10-087-M2 §2 / A2):
1. agent id 唯一 (同 role 多 provider 并存 — id 是唯一键, 不按 role 去重)
2. 行业隔离: 合法行业 {it, ops}; id 前缀 agt-<industry>- 与 industry 字段一致;
   list(industry) 只返回该行业
3. 落盘格式沿用 agents.json 键值结构 ({agent_id: {…}}, 同 session/agents.py)
4. 失败安全: 读取缺失/损坏 → 空注册表 (不抛); 写入/校验错误 → 明确报错
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .agent_entity import AgentEntity

#: 合法行业命名空间 (it.* / ops.* — 行业隔离边界)
INDUSTRIES: tuple[str, ...] = ("it", "ops")

#: 默认专家注册表文件 (~/.factory/agents/factory_agents.json — 与既有数据空间
#: ~/.factory/agents/ 同目录, 独立文件名避免与 workforce agents.json 混写)
DEFAULT_AGENTS_FILE = Path.home() / ".factory" / "agents" / "factory_agents.json"

#: 每行业每角色序号缺省 (next_id 无历史时起始 n=1)
DEFAULT_SEQUENCE_START = 1


class AgentRegistryError(Exception):
    """工厂层 AgentRegistry 基础异常。"""


class AgentAlreadyExists(AgentRegistryError):
    """agent id 已存在 (add 冲突 — id 唯一)。"""


class AgentNotFound(AgentRegistryError):
    """agent id 不存在。"""


class InvalidIndustry(AgentRegistryError):
    """行业不在命名空间内 (it.* / ops.*)。"""


class AgentRegistry:
    """工厂层专家注册表: AgentEntity 集合 + agents.json 持久化。"""

    DEFAULT_FILE = DEFAULT_AGENTS_FILE
    INDUSTRIES = INDUSTRIES

    def __init__(self, agents_file: Optional[Path] = None) -> None:
        self._file = Path(agents_file) if agents_file is not None else self.DEFAULT_FILE

    @property
    def file(self) -> Path:
        return self._file

    # ------------------------------------------------------------ 写

    def add(self, agent: AgentEntity) -> AgentEntity:
        """注册专家; id 冲突 → AgentAlreadyExists; 行业非法 → InvalidIndustry。

        校验后落盘 (agents.json 键值结构, id 为键)。
        """
        if not isinstance(agent, AgentEntity):
            raise AgentRegistryError(f"add 需要 AgentEntity, got {type(agent).__name__}")
        if agent.industry not in INDUSTRIES:
            raise InvalidIndustry(
                f"非法行业命名空间: {agent.industry!r} (合法: {', '.join(INDUSTRIES)})"
            )
        if self.get(agent.id) is not None:
            raise AgentAlreadyExists(f"agent 已存在: {agent.id}")
        data = self.load()
        data[agent.id] = agent.to_dict()
        self.save(data)
        return agent

    def remove(self, agent_id: str) -> AgentEntity:
        """移除专家; 不存在 → AgentNotFound (明确报错, 不静默)。"""
        data = self.load()
        if agent_id not in data:
            raise AgentNotFound(f"agent 不存在: {agent_id}")
        agent = AgentEntity.from_dict(data.pop(agent_id))
        self.save(data)
        return agent

    # ------------------------------------------------------------ 读

    def get(self, agent_id: str) -> Optional[AgentEntity]:
        """按 id 取专家 (不存在 → None)。"""
        data = self.load()
        raw = data.get(str(agent_id))
        if raw is None:
            return None
        try:
            return AgentEntity.from_dict(raw)
        except Exception:  # noqa: BLE001 — 失败安全: 损坏条目跳过
            return None

    def list(self, industry: Optional[str] = None) -> list[AgentEntity]:
        """全部专家 (按 id 排序); industry 非空 → 只返回该行业 (行业隔离)。"""
        agents = []
        for raw in self.load().values():
            try:
                entity = AgentEntity.from_dict(raw)
            except Exception:  # noqa: BLE001 — 失败安全: 损坏条目跳过
                continue
            if industry is not None and entity.industry != str(industry):
                continue
            agents.append(entity)
        return sorted(agents, key=lambda a: a.id)

    def count(self, industry: Optional[str] = None) -> int:
        return len(self.list(industry=industry))

    def next_id(self, industry: str, role: str) -> str:
        """自动编号: agt-<industry>-<role>-<n> (取该行业该角色最大序号 +1)。

        行业非法 → InvalidIndustry (不静默生成脏 id)。
        """
        if industry not in INDUSTRIES:
            raise InvalidIndustry(
                f"非法行业命名空间: {industry!r} (合法: {', '.join(INDUSTRIES)})"
            )
        prefix = f"agt-{industry}-{role}-"
        max_n = 0
        for entity in self.list(industry=industry):
            if entity.id.startswith(prefix):
                suffix = entity.id[len(prefix):]
                if suffix.isdigit():
                    max_n = max(max_n, int(suffix))
        return f"{prefix}{max_n + 1}"

    # ------------------------------------------------------------ 持久化

    def load(self) -> dict[str, dict[str, Any]]:
        """读回 agents.json → {agent_id: {…}}; 缺失/损坏/非 dict → {} (失败安全)。"""
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(k): dict(v) for k, v in data.items() if isinstance(v, dict)}
            return {}
        except Exception:  # noqa: BLE001 — 失败安全: 缺失/损坏 → 空注册表
            return {}

    def save(self, data: dict[str, Any]) -> Path:
        """落盘 agents.json (父目录自动创建; 确定性无时间戳)。"""
        path = self._file
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            raise AgentRegistryError(f"agents.json 落盘失败: {exc}") from exc
        return path


__all__ = [
    "INDUSTRIES",
    "DEFAULT_AGENTS_FILE",
    "AgentRegistry",
    "AgentRegistryError",
    "AgentAlreadyExists",
    "AgentNotFound",
    "InvalidIndustry",
]
