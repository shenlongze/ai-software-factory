"""factory-console/session/evidence.py — EvidenceBundle 证据包 (M1a · E1)。

Claude 产品战略 E1 + Hermes 架构: 把「AI 改了什么 + 为什么 + 测试/日志证据」
打包成可审计的证据包 — 信任优先的交付基础。

EvidenceBundle:
  {bundle_id, project_id, task_id, agent_id,
   diff, test_results, logs, decisions, artifacts,
   created_at, status(pending/approved/rejected/applied)}

- EvidenceBuilder: 从 repo_mode 结果 / 执行数据组装 (diff + 测试 + 决策链 + 产物)
- 持久化: projects/<slug>/evidence/<bundle_id>.json (版本化, 旧包不覆盖)
- 审计: EVIDENCE_BUNDLE_CREATED 事件 (失败安全)
- 消费: 分级审批 (exec.approval) / 组织记忆回流 (M1c) / 观测视图

边界: 纯标准库; 只读消费方输入; 失败安全 (组装/落盘异常 → 明确报错, 不中断业务)。
设计: docs/sprint10/S10-089-cto-tech-design-v2.md §3
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

#: 证据目录名 (项目目录内)
EVIDENCE_ROOT = "evidence"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class EvidenceBundle:
    """证据包: AI 变更的完整可审计证据 (diff+测试+日志+决策+产物)。"""

    bundle_id: str
    project_id: str = ""
    task_id: str = ""
    agent_id: str = ""
    diff: str = ""                       # patch/diff 内容
    test_results: list[dict[str, Any]] = field(default_factory=list)
    logs: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)  # 为什么这么做
    artifacts: list[str] = field(default_factory=list)
    created_at: str = ""
    status: str = "pending"              # pending/approved/rejected/applied

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "diff": self.diff,
            "test_results": list(self.test_results),
            "logs": list(self.logs),
            "decisions": list(self.decisions),
            "artifacts": list(self.artifacts),
            "created_at": self.created_at,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "EvidenceBundle":
        data = data or {}
        return cls(
            bundle_id=str(data.get("bundle_id") or ""),
            project_id=str(data.get("project_id") or ""),
            task_id=str(data.get("task_id") or ""),
            agent_id=str(data.get("agent_id") or ""),
            diff=str(data.get("diff") or ""),
            test_results=list(data.get("test_results") or []),
            logs=list(data.get("logs") or []),
            decisions=list(data.get("decisions") or []),
            artifacts=[str(a) for a in (data.get("artifacts") or [])],
            created_at=str(data.get("created_at") or ""),
            status=str(data.get("status") or "pending"),
        )


class EvidenceBuilder:
    """证据包组装器: 从 repo_mode 结果 / 执行数据构建可审计 EvidenceBundle。"""

    @staticmethod
    def build(
        *,
        project_id: str = "",
        task_id: str = "",
        agent_id: str = "",
        diff: str = "",
        test_results: Optional[list[dict[str, Any]]] = None,
        logs: Optional[list[dict[str, Any]]] = None,
        decisions: Optional[list[dict[str, Any]]] = None,
        artifacts: Optional[list[str]] = None,
    ) -> EvidenceBundle:
        """组装 (字段失败安全缺省; bundle_id 自动生成 ev-<hex8>)。"""
        return EvidenceBundle(
            bundle_id=f"ev-{uuid.uuid4().hex[:8]}",
            project_id=str(project_id or ""),
            task_id=str(task_id or ""),
            agent_id=str(agent_id or ""),
            diff=str(diff or ""),
            test_results=list(test_results or []),
            logs=list(logs or []),
            decisions=list(decisions or []),
            artifacts=[str(a) for a in (artifacts or [])],
            created_at=_now_iso(),
            status="pending",
        )

    @classmethod
    def from_repo_result(cls, result: Any, *, project_id: str = "", agent_id: str = "repo") -> EvidenceBundle:
        """从 RepoModeResult 组装 (diff + 测试结果 + 决策链 + 变更文件)。"""
        test_results: list[dict[str, Any]] = []
        if getattr(result, "test_ok", None) is not None:
            test_results.append({
                "ok": bool(result.test_ok),
                "output": str(getattr(result, "test_output", "") or "")[-2000:],
            })
        decisions: list[dict[str, Any]] = []
        plan = str(getattr(result, "plan_reason", "") or "")
        if plan:
            decisions.append({"step": "plan", "reason": plan[:1000]})
        return cls.build(
            project_id=project_id,
            task_id=str(getattr(result, "target", "") or ""),
            agent_id=agent_id,
            diff=str(getattr(result, "_patch_text", "") or ""),
            test_results=test_results,
            decisions=decisions,
            artifacts=list(getattr(result, "changed_files", []) or []),
        )


class EvidenceStore:
    """证据包持久化: projects/<slug>/evidence/<bundle_id>.json (失败安全)。"""

    def __init__(self, workspace: Any, slug: str) -> None:
        self.root = Path(workspace) / "projects" / str(slug) / EVIDENCE_ROOT

    def save(self, bundle: EvidenceBundle) -> Path:
        """落盘 (父目录自动创建; OSError → 响亮抛错)。"""
        path = self.root / f"{bundle.bundle_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(bundle.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    def load(self, bundle_id: str) -> Optional[EvidenceBundle]:
        """读取 (缺失/损坏 → None, 失败安全)。"""
        try:
            data = json.loads((self.root / f"{bundle_id}.json").read_text(encoding="utf-8"))
            return EvidenceBundle.from_dict(data)
        except Exception:  # noqa: BLE001 — 失败安全
            return None

    def list(self) -> list[EvidenceBundle]:
        """全部证据包 (按创建时间升序; 无 → [])。"""
        bundles: list[EvidenceBundle] = []
        if not self.root.is_dir():
            return bundles
        for path in sorted(self.root.glob("ev-*.json")):
            try:
                bundles.append(EvidenceBundle.from_dict(
                    json.loads(path.read_text(encoding="utf-8"))
                ))
            except Exception:  # noqa: BLE001 — 单包损坏跳过
                continue
        return bundles


def emit_evidence_created(workspace: Any, bundle: EvidenceBundle) -> str:
    """EVIDENCE_BUNDLE_CREATED 审计事件 (失败安全 → ""; 返回 audit_id)。"""
    try:
        from ..audit.audit_emitter import AuditEmitter
        ev = AuditEmitter(workspace=workspace).emit(
            "EVIDENCE_BUNDLE_CREATED",
            project_id=bundle.project_id,
            agent_id=bundle.agent_id,
            actor_type="agent",
            actor_id=bundle.agent_id or "system",
            artifact_reference=bundle.bundle_id,
            bundle_id=bundle.bundle_id,
            task_id=bundle.task_id,
        )
        return str(getattr(ev, "audit_id", "") or "") if ev is not None else ""
    except Exception:  # noqa: BLE001 — 审计故障不中断
        return ""
