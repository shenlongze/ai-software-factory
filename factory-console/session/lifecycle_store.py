"""factory-console/session/lifecycle_store.py — J-1 生命周期状态单一来源 (S10-115)。

三处状态落点单一事实源:
- **project.json.status** = canonical (Lifecycle 词汇; 确认后即存在)
- product.json.status / execution_state.json.lifecycle = **派生镜像**,
  只许由 :func:`set_project_lifecycle` 更新 (对账/白名单例外除外)

组件:
- :data:`LEGACY_STATUS_MAP` — 旧词汇 → Lifecycle 映射 (对账/守卫兼容;
  Lifecycle 值原样通过; 未知值 → 无法判定, 不臆造)
- :func:`set_project_lifecycle` — 统一写入口: 三处同步写 + 防回退守卫
  (词汇校验 / 单调前进 / force=True 仅显式例外 / 失败安全)
- :func:`reconcile_projects` — 一次性存量对账: 快照先行 → canonical 判定
  (①project.json.status 有效 ②product.json.status 映射 ③execution_state.lifecycle
  ④全无/非法 → 跳过如实报告) → 修复写三处

边界 (S10-115 硬边界):
- 纯规则零 LLM; 不臆造: 无法判定的存量项目如实跳过
- 不动 org 状态机 (project.json.lifecycle = org 镜像字段, 保留)
- pending_arch_review (S10-111 架构审批门) 非 Lifecycle 词汇 —
  守卫对未知值不阻断 (无 index 可比较), 该 gate 状态由审批门自身管理

设计: docs/sprint10/S10-115-lifecycle-single-source-plan.md
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .pipeline import Lifecycle

#: 旧词汇 → Lifecycle (对账/守卫兼容; Lifecycle 值原样通过; 未知 → 无法判定)
LEGACY_STATUS_MAP: dict[str, str] = {
    "project_created": Lifecycle.PRODUCT_DEFINED,   # 产品已创建
    "prd_ready": Lifecycle.ENGINEERING_READY,        # PRD 就绪
    "draft": Lifecycle.IDEA,                         # 草稿
    "confirmed": Lifecycle.PRODUCT_DEFINED,          # 已确认 (产品定义完成)
}

#: 对账快照文件名前缀 (projects/<slug>/.status_snapshot_<YYYYmmdd-HHMMSS>.json)
SNAPSHOT_PREFIX = ".status_snapshot_"


class LifecycleStoreError(Exception):
    """生命周期存储错误 (状态文件损坏 / 无法安全写入)。"""


class LifecycleRegressionError(LifecycleStoreError):
    """防回退守卫拒绝: 新状态落后于现有 canonical (仅 force=True 显式例外)。"""


def _write_json(path: Path, data: dict[str, Any]) -> None:
    """落盘 JSON (ensure_ascii=False — 中文可读; 父目录自动创建)。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _canonical_index(status: str) -> Optional[int]:
    """状态 → Lifecycle 索引 (含旧词汇映射); 无法判定 → None (不臆造)。"""
    value = str(status or "").strip().lower()
    if value in Lifecycle.STATUSES:
        return Lifecycle.STATUSES.index(value)
    mapped = LEGACY_STATUS_MAP.get(value)
    if mapped in Lifecycle.STATUSES:
        return Lifecycle.STATUSES.index(mapped)
    return None


def _as_lifecycle(value: Optional[str]) -> Optional[str]:
    """任意源状态 → Lifecycle 值 (Lifecycle 原样 / 旧词汇映射); 无法判定 → None。"""
    if value is None:
        return None
    value = str(value).strip().lower()
    if value in Lifecycle.STATUSES:
        return value
    return LEGACY_STATUS_MAP.get(value)


def _read_field_fail_safe(
    path: Path, field: str
) -> tuple[Optional[str], Optional[str]]:
    """读单文件单字段 (失败安全): 缺失 → (None, None); 损坏 → (None, error)。"""
    if not path.is_file():
        return None, None
    try:
        data = json.loads(path.read_text(encoding="utf-8")) or {}
        value = data.get(field)
        if value in (None, ""):
            return None, None
        return str(value), None
    except Exception as exc:  # noqa: BLE001 — 失败安全: 损坏 → 明确错误不崩
        return None, f"{path.name} 损坏: {exc}"


def set_project_lifecycle(
    project_dir: Path | str,
    status: str,
    *,
    force: bool = False,
    product_file: Optional[Path | str] = None,
    state_file: Optional[Path | str] = None,
) -> dict[str, Any]:
    """统一写入口: 原子写三处 project.json.status + product.json.status +
    (execution_state.json 存在时) lifecycle。

    - 词汇校验: status ∈ Lifecycle.STATUSES (非法 → ValueError 明确错误)
    - 防回退守卫: 新 idx < 现有 project.json.status idx → LifecycleRegressionError
      (force=True 仅显式例外 — ChangeControl 重规划等显式场景; PRD 重生成不得 force)
    - 失败安全: project.json 损坏 → LifecycleStoreError (不覆盖损坏文件);
      product.json / execution_state.json 损坏 → 跳过该镜像 + result["errors"] 记录
      (绝不臆造); 缺失 → 跳过 (镜像文件存在才同步)

    返回: {status, previous, project_file, product_file, state_file, written, errors}。
    """
    project_dir = Path(project_dir)
    if status not in Lifecycle.STATUSES:
        raise ValueError(
            f"非法生命周期状态: {status!r} (允许: {', '.join(Lifecycle.STATUSES)})"
        )
    project_file = project_dir / "project.json"
    product_file = (
        Path(product_file)
        if product_file is not None
        else project_dir / "product.json"
    )
    state_file = (
        Path(state_file) if state_file is not None else project_dir / "execution_state.json"
    )

    # 现有 canonical (project.json.status; 缺失 → None; 损坏 → 明确错误不覆盖)
    existing: dict[str, Any] = {}
    if project_file.is_file():
        try:
            existing = json.loads(project_file.read_text(encoding="utf-8")) or {}
            if not isinstance(existing, dict):
                raise ValueError("project.json 顶层非 JSON 对象")
        except Exception as exc:  # noqa: BLE001 — 失败安全: 损坏不崩不臆造
            raise LifecycleStoreError(
                f"project.json 损坏, 无法安全写入状态: {exc}"
            ) from exc
    previous = str(existing.get("status") or "") or None

    # 防回退守卫: 单调前进 (Lifecycle.STATUSES 索引比较; 旧词汇映射后比较)
    new_idx = Lifecycle.STATUSES.index(status)
    if not force and previous:
        prev_idx = _canonical_index(previous)
        if prev_idx is not None and new_idx < prev_idx:
            raise LifecycleRegressionError(
                f"生命周期回退拒绝: {previous!r} → {status!r} "
                f"(索引 {prev_idx} → {new_idx}; force=True 仅显式例外)"
            )

    # 写 project.json (canonical; 缺失 → 新建 {name: slug, status})
    _write_json(
        project_file,
        {
            **existing,
            "name": existing.get("name") or project_dir.name,
            "status": status,
        },
    )
    written = [str(project_file)]
    errors: list[str] = []

    # product.json 镜像 (存在时)
    if product_file.is_file():
        try:
            existing_p = json.loads(product_file.read_text(encoding="utf-8")) or {}
            if not isinstance(existing_p, dict):
                raise ValueError("product.json 顶层非 JSON 对象")
            _write_json(product_file, {**existing_p, "status": status})
            written.append(str(product_file))
        except Exception as exc:  # noqa: BLE001 — 失败安全: 镜像损坏跳过 + 记录
            errors.append(f"product.json 镜像写入失败 (跳过, 不臆造): {exc}")

    # execution_state.json 镜像 (存在时)
    if state_file.is_file():
        try:
            existing_s = json.loads(state_file.read_text(encoding="utf-8")) or {}
            if not isinstance(existing_s, dict):
                raise ValueError("execution_state.json 顶层非 JSON 对象")
            _write_json(state_file, {**existing_s, "lifecycle": status})
            written.append(str(state_file))
        except Exception as exc:  # noqa: BLE001 — 失败安全: 镜像损坏跳过 + 记录
            errors.append(f"execution_state.json 镜像写入失败 (跳过, 不臆造): {exc}")

    return {
        "status": status,
        "previous": previous,
        "project_file": str(project_file),
        "product_file": str(product_file) if product_file.is_file() else None,
        "state_file": str(state_file) if state_file.is_file() else None,
        "written": written,
        "errors": errors,
    }


@dataclass
class ReconcileReport:
    """存量对账报告 (确定性): fixed / skipped / snapshots。"""

    fixed: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    snapshots: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixed": self.fixed,
            "skipped": self.skipped,
            "snapshots": self.snapshots,
        }


def reconcile_projects(
    workspace: Path | str, *, dry_run: bool = False
) -> ReconcileReport:
    """一次性存量对账 (确定性修复): 每项目快照先行 → canonical 判定 → 修复写三处。

    canonical 判定优先级:
      ① project.json.status 有效 (Lifecycle) → 原样
      ② 缺失/无效 → product.json.status 经 LEGACY_STATUS_MAP 映射
      ③ 再缺失 → execution_state.json.lifecycle (Lifecycle 校验)
      ④ 全无/非法/损坏 → 跳过 + 如实报告 (不臆造)

    dry_run=True → 只读报告 (不写快照/不修复)。修复前每项目快照
    projects/<slug>/.status_snapshot_<YYYYmmdd-HHMMSS>.json (三处原值),
    快照落盘后再改。
    """
    root = Path(workspace) / "projects"
    report = ReconcileReport()
    if not root.is_dir():
        return report
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    for pdir in sorted(root.iterdir()):
        if not pdir.is_dir():
            continue
        slug = pdir.name
        project_file = pdir / "project.json"
        product_file = pdir / "product.json"
        state_file = pdir / "execution_state.json"

        pj_status, pj_err = _read_field_fail_safe(project_file, "status")
        prod_status, prod_err = _read_field_fail_safe(product_file, "status")
        es_lifecycle, es_err = _read_field_fail_safe(state_file, "lifecycle")

        # canonical 判定 (优先级 ①②③)
        canonical = _as_lifecycle(pj_status)
        source = "project.json.status"
        if canonical is None and prod_status is not None:
            canonical = _as_lifecycle(prod_status)
            source = "product.json.status"
        if canonical is None and es_lifecycle is not None:
            canonical = _as_lifecycle(es_lifecycle)
            source = "execution_state.json.lifecycle"

        base = {
            "slug": slug,
            "project_status": pj_status,
            "product_status": prod_status,
            "execution_lifecycle": es_lifecycle,
        }
        errors = [e for e in (pj_err, prod_err, es_err) if e]
        if canonical is None:
            report.skipped.append(
                {
                    **base,
                    "reason": "无法判定: 无有效 canonical (全无/非法/损坏, 不臆造)",
                    "errors": errors,
                }
            )
            continue
        if errors:
            # 损坏文件: project.json 损坏无法安全修复 → 如实跳过; 镜像损坏可修复
            if pj_err:
                report.skipped.append(
                    {
                        **base,
                        "reason": f"无法判定/修复: {pj_err}",
                        "errors": errors,
                    }
                )
                continue

        # 现状对比 (是否需要修复)
        prod_ok = prod_status is None or _as_lifecycle(prod_status) == canonical
        es_ok = es_lifecycle is None or _as_lifecycle(es_lifecycle) == canonical
        if pj_status == canonical and prod_ok and es_ok:
            report.skipped.append(
                {"slug": slug, "canonical": canonical, "reason": "已一致"}
            )
            continue

        snapshot_file = pdir / f"{SNAPSHOT_PREFIX}{ts}.json"
        entry = {
            "slug": slug,
            "status": canonical,
            "source": source,
            "snapshot": str(snapshot_file),
        }
        if dry_run:
            report.fixed.append({**entry, "dry_run": True})
            continue

        # 快照先行 (三处原值; 快照落盘后再改)
        _write_json(
            snapshot_file,
            {
                "slug": slug,
                "reconciled_at": datetime.now(timezone.utc).isoformat(),
                "canonical": canonical,
                "source": source,
                "project_json": (
                    {"status": pj_status} if project_file.is_file() else None
                ),
                "product_json": (
                    {"status": prod_status} if product_file.is_file() else None
                ),
                "execution_state": (
                    {"lifecycle": es_lifecycle} if state_file.is_file() else None
                ),
            },
        )
        report.snapshots.append(str(snapshot_file))
        # 修复写三处 (canonical 不落后于 project.json.status → 无需 force)
        try:
            set_project_lifecycle(
                pdir,
                canonical,
                product_file=product_file,
                state_file=state_file,
            )
        except LifecycleStoreError as exc:
            report.skipped.append(
                {**base, "canonical": canonical, "reason": f"修复失败: {exc}"}
            )
            continue
        report.fixed.append(entry)
    return report
