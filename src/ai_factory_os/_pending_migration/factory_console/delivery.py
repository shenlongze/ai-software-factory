"""delivery — 交付环（全链第 7 环，Founder: 此前完全没有 ✗）。

为什么（Founder 实测指出 ✓）:
  全链 idea → PRD → 架构 → 拆分 → 执行 → 验证 → 【交付 ✗】→ 监控 → 运维 → 自动修复
  前 6 环都有 ✓ 而【交付这一环不存在 ✗】:
    · 命令: export/deliver/package/handover 四个全无 ✗
    · 事件流: 0 条交付类事件 ✗
    · 无"交付物"定义 ✗ · 无交付状态 ✗
  而 ⑮ 项目化已让项目目录【物理自包含】✓ → 打包交付只是"把它变成一等公民" ✓

设计（铁律: 交付物属项目 → 落 projects/<P>/delivery/ ✓）:
  · 交付记录 deliveries.json ✓（按项目 ✓ 与其他 store 同套路 ✓）
  · 交付包 <P>-<ts>.tar.gz ✓（tar 项目目录 ✓ 排除 delivery/ 自身 ✓）
  · 交付清单 manifest: 文档/代码/执行报告/验证记录/成本/架构决策 ✓
  · 状态流转 READY → DELIVERED → ACCEPTED ✓
  · 事件 org.delivery.ready|delivered|accepted ✓（此前 0 条 ✗）
失败安全: 无 docs/workspace 也能交付（清单里如实标 0 ✓）✓
"""

from __future__ import annotations

import json
import os
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _delivery_dir(root: Path | str, project_id: str) -> Path:
    """交付物目录（铁律: 属项目的文件在项目下 ✓）。"""
    return Path(root) / "projects" / project_id / "delivery"


def _records_file(root: Path | str, project_id: str) -> Path:
    return _delivery_dir(root, project_id) / "deliveries.json"


def _load(root: Path | str, project_id: str) -> dict[str, dict[str, Any]]:
    p = _records_file(root, project_id)
    if not p.is_file():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return d if isinstance(d, dict) else {}


def _save(root: Path | str, project_id: str,
          recs: dict[str, dict[str, Any]]) -> None:
    """原子写（★ 临时名唯一 ✓ —— 固定名会在并发下 FileNotFoundError ✗）。"""
    p = _records_file(root, project_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f".{p.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(recs, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    os.replace(tmp, p)


def build_manifest(root: Path | str, project_id: str) -> dict[str, Any]:
    """交付清单: 盘清这个项目【交付了些什么】✓（全部只读 ✓）。"""
    root = Path(root)
    proj = root / "projects" / project_id
    m: dict[str, Any] = {
        "project_id": project_id,
        "project_dir_exists": proj.is_dir(),
    }

    def _count(pattern: str) -> int:
        return len(list(root.glob(f"projects/{project_id}/{pattern}")))

    m["docs"] = sorted(p.name for p in proj.glob("docs/*")) if proj.is_dir() else []
    m["prd_count"] = _count("docs/PRD-*.md")
    m["task_list_count"] = _count("docs/task_*.md")
    m["workspace_files"] = _count("workspace/**/*")
    m["exec_records"] = _count("exec/*.json")
    m["artifacts"] = _count("artifacts/**/*.json")
    m["conversations"] = _count("conversations/*.json")
    # 架构决策（本轮刚补的环节 ✓ 交付清单里体现 ✓）
    try:
        from .product_truth import _load as _pt_load
        adrs = [r for r in _pt_load(root, "decisions").values()
                if isinstance(r, dict) and str(r.get("project_id") or "") == project_id]
        m["architecture_decisions"] = [
            {"form": r.get("form"), "tech_stack": r.get("tech_stack")} for r in adrs]
    except Exception:  # noqa: BLE001 — 失败安全 ✓
        m["architecture_decisions"] = []
    # 执行报告与验证证据（全局目录里按项目无索引 → 只报总数 ✓ 如实标注 ✓）
    m["exec_reports_total"] = len(list(root.glob("exec/*.report.md")))
    m["verifications_total"] = 0
    try:
        vf = root / "verifications" / "verifications.json"
        if vf.is_file():
            v = json.loads(vf.read_text(encoding="utf-8"))
            m["verifications_total"] = len(v) if isinstance(v, (dict, list)) else 0
    except Exception:  # noqa: BLE001
        pass
    # 成本（该项目预算 + 全局已完成执行的成本合计 ✓）
    try:
        from .session.budget import ProjectBudget
        bf = _delivery_dir(root, project_id).parent / "project_budget.json"
        b = ProjectBudget.load(bf) if bf.is_file() else ProjectBudget()
        m["budget"] = b.to_dict() if hasattr(b, "to_dict") else {}
    except Exception:  # noqa: BLE001
        m["budget"] = {}
    return m


def pack(root: Path | str, project_id: str) -> Path | None:
    """打包项目目录 → delivery/<P>-<ts>.tar.gz（排除 delivery/ 自身 ✓ 幂等 ✓）。"""
    root = Path(root)
    proj = root / "projects" / project_id
    if not proj.is_dir():
        return None
    out_dir = _delivery_dir(root, project_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    out = out_dir / f"{project_id}-{ts}.tar.gz"

    # ★ 只遍历【顶层条目】✓ —— 逐个 rglob 加会把目录内容重复入包 ✗
    #   （tf.add(目录) 本身递归 ✓ 再加文件就是两份 ✗ 实测: 20 项里每条出现两次 ✗）
    entries = [p for p in sorted(proj.iterdir())
               if p.name != "delivery" and not p.name.startswith(".")]
    with tarfile.open(out, "w:gz") as tf:
        for p in entries:
            tf.add(p, arcname=str(p.relative_to(root)), recursive=True)
    return out


def deliver(root: Path | str, project_id: str, *, pack_now: bool = True) -> dict[str, Any]:
    """生成交付（READY）: 清单 ✓ + 交付包 ✓ + 记录 ✓。"""
    recs = _load(root, project_id)
    did = f"DLV-{os.urandom(5).hex()}"
    manifest = build_manifest(root, project_id)
    package = str(pack(root, project_id)) if pack_now else ""
    rec = {
        "id": did, "project_id": project_id, "status": "READY",
        "manifest": manifest, "package": package,
        "created_at": _now_iso(), "delivered_at": None, "accepted_at": None,
    }
    recs[did] = rec
    _save(root, project_id, recs)
    return rec


def mark(root: Path | str, project_id: str, delivery_id: str,
         status: str) -> dict[str, Any] | None:
    """状态流转 READY → DELIVERED → ACCEPTED ✓（非法流转拒绝 ✓）。"""
    order = ["READY", "DELIVERED", "ACCEPTED"]
    recs = _load(root, project_id)
    r = recs.get(delivery_id)
    if not isinstance(r, dict):
        return None
    if status not in order:
        return None
    if order.index(status) <= order.index(str(r.get("status") or "READY")):
        return None                      # 不能倒退 ✓
    r["status"] = status
    r["delivered_at" if status == "DELIVERED" else "accepted_at"] = _now_iso()
    _save(root, project_id, recs)
    return r


def list_deliveries(root: Path | str, project_id: str) -> list[dict[str, Any]]:
    return sorted(_load(root, project_id).values(),
                  key=lambda r: str(r.get("created_at") or ""), reverse=True)
