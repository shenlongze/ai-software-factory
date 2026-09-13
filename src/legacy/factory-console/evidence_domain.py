"""factory-console/evidence_domain.py — P0-F4 Evidence SSOT (EVD-*)。

D2 冻结: canonical Evidence = EVD-* 独立域 (支撑 Verification 结论的事实材料)。
- 旧 ev-* EvidenceBundle (M3 approval package) = LEGACY, 不升级不迁移。
- Evidence ≠ Verification ≠ Artifact ≠ Approval ≠ Audit。

EVD-* 语义: 保存"为什么这个 Verification 结论值得相信"的可追溯事实
(真实 verifier 输出: pytest stdout/test report/校验报告/checksum 等)。

- identity: EVD-{hex10}
- 幂等: 同 (verification_id, evidence_type, source_ref) 已存在 → 返回已有
- 不可变 (修改 = 新记录, 不 UPDATE 旧)
- 共享: 一个 EVD 可被多 Verification 引用 (D3 — 引用方持有, Evidence 不可变)
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_lock = threading.RLock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _evidence_file(root: Path | str, evidence_id: str) -> Path:
    return Path(root) / "evidence" / f"{evidence_id}.json"


def _load_all(root: Path | str) -> dict[str, dict[str, Any]]:
    d = Path(root) / "evidence"
    if not d.is_dir():
        return {}
    out: dict[str, dict[str, Any]] = {}
    for p in sorted(d.glob("EVD-*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue  # 单文件损坏跳过 (失败安全; 域内其它可读)
        if isinstance(data, dict) and data.get("evidence_id"):
            out[str(data["evidence_id"])] = data
    return out


def get_evidence(root: Path | str, evidence_id: str) -> dict[str, Any] | None:
    """按 EVD-* id 读取 (不存在 → None)。"""
    return _load_all(root).get(evidence_id)


def list_evidence(root: Path | str,
                  verification_id: str = "") -> list[dict[str, Any]]:
    """全部 (可按 verification_id 过滤; 审计友好排序)。"""
    recs = _load_all(root)
    out = []
    for e in recs.values():
        if verification_id and verification_id not in (e.get("verification_refs") or []):
            continue
        out.append(e)
    return sorted(out, key=lambda e: str(e.get("created_at") or ""))


def count(root: Path | str) -> int:
    return len(_load_all(root))


def materialize_evidence(
    root: Path | str,
    *,
    verification_id: str,
    evidence_type: str,
    source_ref: str = "",
    content: str = "",
    metadata: dict[str, Any] | None = None,
    actor: str = "verification",
) -> dict[str, Any]:
    """P0-F4 唯一写入口: 真实 verifier 输出 → EVD-* SSOT (幂等, 不可变)。

    - evidence_type: pytest_output / test_report / syntax_report / checksum /
      verifier_log / build_output / artifact_snapshot (真实生产材料)
    - source_ref: 可溯源来源 (文件路径/命令/verifier id)
    - content: 真实输出内容 (截断保护? 由调用方控制; 大内容存引用 path)
    - 幂等: 同 (verification_id, evidence_type, source_ref) → 返回已有
    - 不可变: 写入后不提供 update (I10 精神)
    """
    if not verification_id:
        raise ValueError("evidence verification_id required")
    if not evidence_type:
        raise ValueError("evidence_type required")
    with _lock:
        for e in _load_all(root).values():
            if (verification_id in (e.get("verification_refs") or [])
                    and e.get("evidence_type") == evidence_type
                    and e.get("source_ref") == (source_ref or "")):
                return e
        eid = f"EVD-{uuid.uuid4().hex[:10]}"
        now = _now_iso()
        rec: dict[str, Any] = {
            "evidence_id": eid,
            "verification_refs": [verification_id],  # 创建者引用; 共享=追加引用 (见 attach)
            "evidence_type": str(evidence_type),
            "source_ref": str(source_ref or ""),
            "content": str(content or "")[:20000],
            "metadata": dict(metadata or {}),
            "actor": str(actor or "verification"),
            "created_at": now,
            "immutable": True,
        }
        p = _evidence_file(root, eid)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, p)
        return rec


def attach_evidence(root: Path | str, evidence_id: str, verification_id: str) -> bool:
    """共享: 追加 Verification 引用到已有 EVD (不可变 content, 引用可变)。"""
    with _lock:
        recs = _load_all(root)
        e = recs.get(evidence_id)
        if e is None:
            return False
        refs = list(e.get("verification_refs") or [])
        if verification_id not in refs:
            refs.append(verification_id)
            e["verification_refs"] = refs
            p = _evidence_file(root, evidence_id)
            tmp = p.with_suffix(p.suffix + ".tmp")
            tmp.write_text(json.dumps(e, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            os.replace(tmp, p)
        return True
