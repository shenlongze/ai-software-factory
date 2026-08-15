"""factory-console/session/teams.py — Agent Team Collaboration (S10-056)。

从"单 Agent 自动开发"升级为"多 Agent 软件生产团队"的扩展层 (不重构主链路):

- AgentTeam  — 团队数据模型 (team_id/name/members/projects/created_at +
  member_roles/has_member/to_dict/from_dict)
- TeamRegistry — 团队注册表 (teams.json 读取 + create/get/list/has/assign_project/
  build_default_team/load/save/add_team; 失败安全 → 默认团队 software-team)
- TeamService — 协作视图服务: team_snapshot (成员 + Registry 状态 + Metrics 绩效
  合并; 缺 agent 注册 → 占位 "-")

设计: docs/sprint10/S10-056-team-design.md (§2 数据模型 / §3 模块计划 / §4 协作视图)
边界:
- 只读/聚合数据, 不执行业务; 失败安全 (缺失/损坏 → 默认团队, 永不抛)
- 纯标准库 (json/pathlib/dataclasses), 零新依赖; 只 import .agents
  (AgentRegistry/AgentMetrics 复用 agents.json + agent_metrics.json, 不造新数据源)
- 不 import actions/pipeline (避免循环依赖)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .agents import AgentMetrics, AgentRegistry

#: 默认团队注册表文件 (~/.factory/teams/teams.json — 与 agents.json 同数据空间)
DEFAULT_TEAMS_FILE = Path.home() / ".factory" / "teams" / "teams.json"

#: 默认团队 id/name (software-team — 设计 §2 示例口径)
DEFAULT_TEAM_ID = "software-team"
DEFAULT_TEAM_NAME = "AI Software Team"

#: 默认团队成员编制 (agent → role; 设计 §5: 现有 3 真实 Agent + 预留 pm/architect/qa)
DEFAULT_TEAM_MEMBERS: list[dict[str, str]] = [
    {"agent": "pm-agent", "role": "product_manager"},
    {"agent": "architect-agent", "role": "architect"},
    {"agent": "backend-1", "role": "backend"},
    {"agent": "flutter-dev", "role": "frontend"},
    {"agent": "qa-agent", "role": "qa"},
]


def _now_iso() -> str:
    """UTC 当前时间 ISO 格式 (团队创建时间戳)。"""
    return datetime.now(timezone.utc).isoformat()


#: 默认团队 (设计 §2.1 示例口径 — software-team 固定 5 角色编制; 与
#: build_default_team() 同源, 供零配置引用: DEFAULT_TEAM["team_id"] == "software-team")
DEFAULT_TEAM: dict[str, Any] = {
    "team_id": DEFAULT_TEAM_ID,
    "name": DEFAULT_TEAM_NAME,
    "members": [dict(m) for m in DEFAULT_TEAM_MEMBERS],
    "projects": [],
    "created_at": _now_iso(),
}


@dataclass
class AgentTeam:
    """团队数据模型 (设计 §2): team_id/name/members/projects/created_at。

    members: [{agent, role}] — 团队成员与角色; projects: 项目归属列表。
    member_roles() -> {agent: role}; has_member(agent_id) -> bool。
    to_dict()/from_dict() — 与 teams.json 落盘格式互转 (兼容缺省字段)。
    """

    team_id: str
    name: str
    members: list[dict[str, Any]] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    created_at: Optional[str] = None

    def member_roles(self) -> dict[str, str]:
        """成员 → 角色映射 ({agent: role}); 无效成员 (非 dict/无 agent) 跳过。"""
        roles: dict[str, str] = {}
        for member in self.members or []:
            if not isinstance(member, dict):
                continue
            agent_id = member.get("agent")
            if not agent_id:
                continue
            roles[str(agent_id)] = str(member.get("role") or "")
        return roles

    def has_member(self, agent_id: str) -> bool:
        """agent_id 是否团队成员 (缺失/空 → False)。"""
        if not agent_id:
            return False
        return str(agent_id) in self.member_roles()

    def to_dict(self) -> dict[str, Any]:
        """落盘格式 (teams.json 条目): 顶层契约字段 + members/projects 拷贝。"""
        return {
            "team_id": self.team_id,
            "name": self.name,
            "members": [dict(m) for m in (self.members or [])],
            "projects": list(self.projects or []),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]]) -> "AgentTeam":
        """读回格式 (teams.json 条目) → AgentTeam; 缺失/损坏字段失败安全缺省。"""
        data = data or {}
        members = data.get("members") or []
        projects = data.get("projects") or []
        return cls(
            team_id=str(data.get("team_id") or data.get("id") or ""),
            name=str(data.get("name") or ""),
            members=[dict(m) for m in members if isinstance(m, dict)],
            projects=[str(p) for p in projects if not isinstance(p, dict)],
            created_at=data.get("created_at"),
        )


class TeamRegistry:
    """团队注册表 (设计 §3): teams.json 读取 (失败安全 → 默认团队) + 查询/创建/分配。

    load(teams_file) → {team_id: team}: 读 teams.json (缺失/损坏/空 → 默认团队
    注册表 {software-team}, 失败安全); 每个团队经 AgentTeam 规范化。
    与 AgentRegistry 同失败安全口径 — 默认团队永远可用 (查看团队零配置开箱即用)。
    """

    DEFAULT_FILE = DEFAULT_TEAMS_FILE

    # ------------------------------------------------------------ 默认团队

    @classmethod
    def build_default_team(
        cls, agents_file: Optional[Path] = None
    ) -> dict[str, Any]:
        """默认团队 (software-team): DEFAULT_TEAM_MEMBERS 5 角色编制。

        现有 agents.json 成员 (backend-1/flutter-dev/tester-1) 复用真实注册表
        状态 (经 team_snapshot 合并); 未在编制内的注册 Agent 不强制加入
        (默认团队是固定 5 角色 — 设计 §5: 现有 3 Agent + 预留 pm/architect/qa)。
        agents_file 参数保留供未来按注册表动态补全 (当前为固定编制, 确定性)。
        """
        team = AgentTeam(
            team_id=DEFAULT_TEAM_ID,
            name=DEFAULT_TEAM_NAME,
            members=[dict(m) for m in DEFAULT_TEAM_MEMBERS],
            projects=[],
            created_at=_now_iso(),
        )
        return team.to_dict()

    # ------------------------------------------------------------ 读写

    @classmethod
    def load(cls, teams_file: Optional[Path] = None) -> dict[str, dict[str, Any]]:
        """读 teams.json → {team_id: team}; 缺失/损坏/空 → 默认团队 (失败安全)。"""
        path = Path(teams_file) if teams_file is not None else cls.DEFAULT_FILE
        data: Any = None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — 失败安全: 缺失/损坏 → 默认团队
            data = None
        return cls._normalize(data)

    @classmethod
    def _normalize(cls, data: Any) -> dict[str, dict[str, Any]]:
        """任意结构 → {team_id: team} (AgentTeam 规范化; 非 dict/空 → 默认团队)。"""
        if not isinstance(data, dict) or not data:
            default = cls.build_default_team()
            return {default["team_id"]: default}
        result: dict[str, dict[str, Any]] = {}
        for key, raw in data.items():
            if not isinstance(raw, dict):
                raw = {"team_id": str(key)}
            team = AgentTeam.from_dict(raw)
            if not team.team_id:
                team.team_id = str(key)
            result[team.team_id] = team.to_dict()
        if not result:
            default = cls.build_default_team()
            return {default["team_id"]: default}
        return result

    @classmethod
    def save(cls, teams_file: Optional[Path], teams: dict[str, Any]) -> Path:
        """落盘 teams.json (父目录自动创建; 中文可读, 确定性无时间戳)。"""
        path = Path(teams_file) if teams_file is not None else cls.DEFAULT_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(teams, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    # ------------------------------------------------------------ 查询

    @classmethod
    def get(
        cls, team_id: str, teams_file: Optional[Path] = None
    ) -> Optional[dict[str, Any]]:
        """按 team_id 取团队; 未注册 → None (调用方决定默认, 不静默)。"""
        return cls.load(teams_file).get(str(team_id))

    @classmethod
    def list(cls, teams_file: Optional[Path] = None) -> list[dict[str, Any]]:
        """全部团队, 按 team_id 排序 (list 稳定性)。"""
        registry = cls.load(teams_file)
        return [registry[tid] for tid in sorted(registry)]

    @classmethod
    def has(cls, team_id: str, teams_file: Optional[Path] = None) -> bool:
        """team_id 是否已注册。"""
        return str(team_id) in cls.load(teams_file)

    # ------------------------------------------------------------ 变更

    @classmethod
    def create(
        cls,
        team_id: str,
        name: str,
        members: Optional[list[dict[str, Any]]] = None,
        teams_file: Optional[Path] = None,
    ) -> dict[str, Any]:
        """创建团队 → 注册表落盘 (add_team) → 返回团队 dict (验收 F)。

        team_id 空 → ValueError (明确错误, 不静默); name 空 → 回落 team_id。
        """
        team_id = str(team_id or "").strip()
        if not team_id:
            raise ValueError("team_id 不能为空")
        team = AgentTeam(
            team_id=team_id,
            name=str(name or "").strip() or team_id,
            members=[dict(m) for m in (members or [])],
            projects=[],
            created_at=_now_iso(),
        ).to_dict()
        return cls.add_team(team, teams_file=teams_file)

    @classmethod
    def add_team(
        cls, team: dict[str, Any], teams_file: Optional[Path] = None
    ) -> dict[str, Any]:
        """注册/覆盖团队 → 落盘 → 返回规范化团队 dict (已存在 → 覆盖, 声明式)。"""
        normalized = AgentTeam.from_dict(team).to_dict()
        if not normalized["team_id"]:
            raise ValueError("team_id 不能为空")
        registry = cls.load(teams_file)
        registry[normalized["team_id"]] = normalized
        cls.save(teams_file, registry)
        return normalized

    @classmethod
    def assign_project(
        cls,
        team_id: str,
        project_id: str,
        teams_file: Optional[Path] = None,
    ) -> dict[str, Any]:
        """项目 → 团队归属: 追加 project_id (去重) → 落盘 → 返回更新后团队。

        团队不存在 → ValueError (明确错误, 不静默); project_id 已存在 → 幂等。
        """
        registry = cls.load(teams_file)
        team = registry.get(str(team_id))
        if team is None:
            raise ValueError(f"团队不存在: {team_id}")
        projects = [str(p) for p in (team.get("projects") or [])]
        if str(project_id) not in projects:
            projects.append(str(project_id))
        team["projects"] = projects
        registry[str(team_id)] = team
        cls.save(teams_file, registry)
        return team

    @classmethod
    def add_member(
        cls,
        team_id: str,
        agent: str,
        role: str,
        teams_file: Optional[Path] = None,
    ) -> dict[str, Any]:
        """成员 → 团队: 追加 {agent, role} (同 agent 已存在 → 更新 role) → 落盘 → 返回团队。

        团队不存在 → ValueError (明确错误, 不静默); agent 空 → ValueError;
        成员追加幂等 (agent 唯一, 追加/更新不重复)。
        """
        registry = cls.load(teams_file)
        team = registry.get(str(team_id))
        if team is None:
            raise ValueError(f"团队不存在: {team_id}")
        agent_id = str(agent or "").strip()
        if not agent_id:
            raise ValueError("agent 不能为空")
        members = [dict(m) for m in (team.get("members") or []) if isinstance(m, dict)]
        entry = {"agent": agent_id, "role": str(role or "")}
        replaced = False
        for i, member in enumerate(members):
            if str(member.get("agent")) == agent_id:
                members[i] = entry
                replaced = True
                break
        if not replaced:
            members.append(entry)
        team["members"] = members
        registry[str(team_id)] = team
        cls.save(teams_file, registry)
        return team


class TeamService:
    """团队协作视图服务 (设计 §4): team_snapshot 成员 + Registry + Metrics 合并。"""

    @classmethod
    def team_snapshot(
        cls,
        team: dict[str, Any],
        registry: dict[str, Any],
        metrics: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """团队协作视图: {team_id, name, members: [{agent, role, status,
        success_rate, total_tasks, current_task}]}。

        成员行 = 团队成员 × Registry 状态 (status/current_task) × Metrics 绩效
        (success_rate/total_tasks); 缺 agent 注册 → 占位 "-" (失败安全, 不抛)。
        """
        metrics = metrics or {}
        rows: list[dict[str, Any]] = []
        for member in team.get("members") or []:
            if not isinstance(member, dict):
                continue
            agent_id = str(member.get("agent") or "")
            if not agent_id:
                continue
            role = str(member.get("role") or "")
            reg = registry.get(agent_id) if isinstance(registry, dict) else None
            entry = metrics.get(agent_id) if isinstance(metrics, dict) else None
            entry = entry if isinstance(entry, dict) else {}
            if isinstance(reg, dict):
                status = str(reg.get("status") or "available")
                current = reg.get("current_task")
                current_task = str(current) if current else "-"
                total_tasks = entry.get("total_tasks", 0)
            else:
                status = "-"
                current_task = "-"
                total_tasks = "-"
            sr = entry.get("success_rate")
            rows.append(
                {
                    "agent": agent_id,
                    "role": role,
                    "status": status,
                    "success_rate": sr if isinstance(sr, (int, float)) else "-",
                    "total_tasks": total_tasks,
                    "current_task": current_task,
                }
            )
        return {
            "team_id": str(team.get("team_id") or ""),
            "name": str(team.get("name") or ""),
            "members": rows,
        }
