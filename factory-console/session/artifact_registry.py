"""factory-console/session/artifact_registry.py — 版本化资产注册表 (S10-084 P0)。

产品管线每角色产出 = 版本化 Artifact (artifact.md + artifact.json, v1..n),
供 PM/Market/Competitive/UX/Architect/QA/PRD 及后续 PRD/工程/审批消费。

目录约定:
  <workspace>/projects/<slug>/artifacts/<type>/v<n>/artifact.md + artifact.json

组件:
- ArtifactRecord — {id, type, version, source, created_by, status,
  content_ref, event_id, parent_event_id, timestamp, model, token_usage,
  cost, metadata}
- ArtifactRegistry — write (版本递增) / latest / list / get

边界:
- 纯标准库 (dataclasses/json/uuid/datetime/pathlib), 零新依赖
- 失败安全: 读写异常 → 明确报错 (write 抛 ValueError; 读取类 None/[]),
  不中断业务 (调用方失败安全兜底)
- 确定性: version 从已有 v<n> 递增; 不覆盖旧版本 (渐进明细的版本前提)
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

#: 资产根目录名 (项目目录内)
ARTIFACT_ROOT = "artifacts"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ArtifactRecord:
    """单个版本化资产记录 (meta 与内容分离, 内容在 content_ref 指向的 .md)。"""

    id: str
    type: str
    version: int
    source: str = ""           # conversation_id / idea_id / 触发来源
    created_by: str = ""       # 角色 (pm/market/...) 或 user+ai
    status: str = "draft"      # draft → confirmed
    content_ref: str = ""      # artifact.md 相对/绝对路径
    event_id: str = ""         # 关联审计事件 (血缘)
    parent_event_id: str = ""  # 上游事件 (血缘链)
    timestamp: str = ""
    model: str = ""
    token_usage: int = 0
    cost: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "version": self.version,
            "source": self.source,
            "created_by": self.created_by,
            "status": self.status,
            "content_ref": self.content_ref,
            "event_id": self.event_id,
            "parent_event_id": self.parent_event_id,
            "timestamp": self.timestamp,
            "model": self.model,
            "token_usage": self.token_usage,
            "cost": self.cost,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, data: Any) -> "ArtifactRecord":
        data = data or {}
        return cls(
            id=str(data.get("id") or ""),
            type=str(data.get("type") or ""),
            version=int(data.get("version") or 0),
            source=str(data.get("source") or ""),
            created_by=str(data.get("created_by") or ""),
            status=str(data.get("status") or "draft"),
            content_ref=str(data.get("content_ref") or ""),
            event_id=str(data.get("event_id") or ""),
            parent_event_id=str(data.get("parent_event_id") or ""),
            timestamp=str(data.get("timestamp") or ""),
            model=str(data.get("model") or ""),
            token_usage=int(data.get("token_usage") or 0),
            cost=str(data.get("cost") or ""),
            metadata=dict(data.get("metadata") or {}),
        )


class ArtifactRegistry:
    """版本化资产注册表: write 自动 v+1, 旧版本永不覆盖 (渐进明细/变更前提)。"""

    def __init__(self, workspace: Any, slug: str) -> None:
        self.root = Path(workspace) / "projects" / str(slug) / ARTIFACT_ROOT

    # ------------------------------------------------------------ 写入

    def write(
        self,
        artifact_type: str,
        content_md: str,
        *,
        created_by: str = "",
        source: str = "",
        status: str = "draft",
        parent_event_id: str = "",
        model: str = "",
        token_usage: int = 0,
        cost: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> ArtifactRecord:
        """写入新版本: version = latest+1 (首版 v1); 返回 ArtifactRecord (抛错明确)。"""
        if not str(artifact_type or "").strip():
            raise ValueError("artifact_type 不能为空")
        latest = self.latest(artifact_type)
        version = (latest.version + 1) if latest is not None else 1
        record = ArtifactRecord(
            id=f"{artifact_type}-v{version}-{uuid.uuid4().hex[:8]}",
            type=str(artifact_type).strip(),
            version=version,
            source=source,
            created_by=created_by,
            status=status,
            timestamp=_now_iso(),
            model=model,
            token_usage=token_usage,
            cost=cost,
            parent_event_id=parent_event_id,
            metadata=dict(metadata or {}),
        )
        vdir = self.root / record.type / f"v{version}"
        try:
            vdir.mkdir(parents=True, exist_ok=True)
            md_path = vdir / "artifact.md"
            md_path.write_text(str(content_md or ""), encoding="utf-8")
            record.content_ref = str(md_path)
            json_path = vdir / "artifact.json"
            json_path.write_text(
                json.dumps(record.to_dict(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            raise ValueError(f"资产落盘失败 ({record.type} v{version}): {exc}") from exc
        return record

    # ------------------------------------------------------------ 读取

    def latest(self, artifact_type: str) -> Optional[ArtifactRecord]:
        """最新版本 (不存在 → None)。"""
        type_dir = self.root / str(artifact_type or "")
        if not type_dir.is_dir():
            return None
        versions = sorted(
            (p for p in type_dir.glob("v*") if p.is_dir()),
            key=lambda p: _version_of(p.name),
            reverse=True,
        )
        for vdir in versions:
            rec = self._read(vdir / "artifact.json")
            if rec is not None:
                return rec
        return None

    def read(self, record: ArtifactRecord) -> str:
        """读取资产正文 (content_ref → artifact.md); 缺失/损坏 → "" (失败安全)。

        S10-088 T2: HandoffBus.route 交接消费读上一产出正文 (prompt 嵌
        '上一资产内容'), 而非仅传 asset id。
        """
        if record is None or not getattr(record, "content_ref", ""):
            return ""
        try:
            return Path(str(record.content_ref)).read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001 — 失败安全: 内容缺失/损坏 → 空
            return ""

    def list(self, artifact_type: Optional[str] = None) -> list[ArtifactRecord]:
        """全部资产记录 (按 type/version 升序; 无 → [])。"""
        results: list[ArtifactRecord] = []
        type_dirs = (
            [self.root / artifact_type] if artifact_type else sorted(self.root.glob("*"))
        )
        for type_dir in type_dirs:
            if not type_dir.is_dir():
                continue
            for vdir in sorted(type_dir.glob("v*"), key=lambda p: _version_of(p.name)):
                rec = self._read(vdir / "artifact.json")
                if rec is not None:
                    results.append(rec)
        return results

    def _read(self, path: Path) -> Optional[ArtifactRecord]:
        """读取 artifact.json (缺失/损坏 → None, 失败安全)。"""
        try:
            return ArtifactRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001 — 失败安全
            return None


def _version_of(name: str) -> int:
    """目录名 'v<n>' → n (非法 → 0)。"""
    try:
        return int(str(name).lstrip("v"))
    except (ValueError, AttributeError):
        return 0
