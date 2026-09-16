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


def _load_project_prds(root: Path, project_id: str) -> list[dict]:
    """读项目 product_truth/prds.json ✓（兼容包装/扁平两格式 ✓ 失败安全 ✓）。"""
    f = Path(root) / "projects" / project_id / "product_truth" / "prds.json"
    if not f.is_file():
        return []
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if isinstance(d, dict):
        inner = d.get("prds")
        d = inner if isinstance(inner, dict) else d
        return [v for v in d.values() if isinstance(v, dict)]
    return [v for v in d if isinstance(v, dict)] if isinstance(d, list) else []


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
    # ★ 2026-09-14 修 ✗: PRD 记录在 product_truth/prds.json ✓ 不在 docs/ ✗
    #   （原来只数 docs/PRD-*.md ✗ → 交付清单永远显示"PRD 0"✗ 即使有 PRD ✓）
    _pt_prds = _load_project_prds(root, project_id)
    _md_prds = _count("docs/PRD-*.md")
    m["prd_count"] = max(_md_prds, len(_pt_prds))
    m["prd_ids"] = [str(p.get("id")) for p in _pt_prds[:5]]
    m["task_list_count"] = _count("docs/task_*.md")
    m["workspace_files"] = _count("workspace/**/*")
    m["exec_records"] = _count("exec/*.json")
    m["artifacts"] = _count("artifacts/**/*.json")
    m["conversations"] = _count("conversations/*.json")
    # ★ 冲突文件 + 产物清单 + 健康判定（2026-09-15 修，Founder: "每一个环节都需要优化"）
    #   病灶实测: 「把 Markdown 转成 PDF」那个项目交付时 workspace 里躺着 **20 个
    #   `.conflict-*` 文件**（8 个任务都写 index.html 互相覆盖），而交付报告写的是
    #   「通过 (Ready to ship)」、检查项 3 / 失败 0 / 警告 0 —— 因为交付环节
    #   **只盘数量、不盘内容、无门槛**。此处补上：冲突必现、产物逐列、健康给结论 ✓
    _ws = proj / "workspace"
    _conf = sorted(p.name for p in _ws.rglob("*.conflict-*")) if _ws.is_dir() else []
    m["conflict_files"] = _conf
    m["conflict_count"] = len(_conf)
    # 产物清单（逐文件, 排除依赖目录与冲突残留本身）
    _skip = {"node_modules", ".git", "__pycache__", ".nodes"}
    _tree: list[dict[str, Any]] = []
    if _ws.is_dir():
        for p in sorted(_ws.rglob("*")):
            if not p.is_file() or any(s in p.parts for s in _skip):
                continue
            if ".conflict-" in p.name:
                continue
            try:
                _tree.append({"path": str(p.relative_to(_ws)), "bytes": p.stat().st_size})
            except OSError:  # noqa: PERF203 — 单个文件读不到不影响清单
                continue
    m["workspace_tree"] = _tree[:200]
    m["workspace_tree_count"] = len(_tree)
    m["health"] = ("conflicts" if _conf else
                   "empty_workspace" if _ws.is_dir() and not _tree else "ok")
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
    """生成交付（READY）: 清单 ✓ + 交付包 ✓ + 记录 ✓。

    ★ 2026-09-15 修（Founder: "每一个环节都需要优化"）: 记录里带上 **health**
      （ok / conflicts / empty_workspace）与 **conflict_count**。
      此前清单只盘数量、无健康结论 ⇒ 一个 workspace 里躺着 20 个 `.conflict-*`
      （任务互相覆盖留下的）的交付, 也能拿「READY」而没人看得见。
      ★ 状态仍给 READY（是否接受由人决定）, 但**健康结论必须随记录一起走** ✓
    """
    recs = _load(root, project_id)
    did = f"DLV-{os.urandom(5).hex()}"
    manifest = build_manifest(root, project_id)
    package = str(pack(root, project_id)) if pack_now else ""
    rec = {
        "id": did, "project_id": project_id, "status": "READY",
        "health": manifest.get("health", "ok"),
        "conflict_count": int(manifest.get("conflict_count") or 0),
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


# ══════════════════════════════════════════════════════════════════════════
# 用户验收测试 (UAT) —— 正常交付流程的标准节点（2026-09-14 补 ✓）
#
# 为什么单独有这一环（Founder: "正常交付流程还有什么节点没有" ✓）:
#   tester 做的是【技术测试 ✓】，验收要的是【用户按验收标准逐条确认 ✓】——
#   两者不同 ✗（技术全绿 ≠ 用户认为可用 ✓）。
# 验收标准的自然来源: PRD 的 features / user_stories（契约字段 ✓）
#   → 不需要用户另填 ✓（有 PRD 就能生成清单 ✓）
# 门语义: 交付置 ACCEPTED 前【必须每一条都签过 ✓】—— 这是真门 ✗ 不是装饰 ✓
# 落盘: projects/<P>/delivery/uat.json ✓（铁律: 交付物属项目 ✓）
# ══════════════════════════════════════════════════════════════════════════


def _uat_file(root: Path | str, project_id: str) -> Path:
    return _delivery_dir(root, project_id) / "uat.json"


def build_uat_checklist(root: Path | str, project_id: str) -> dict[str, Any]:
    """从 PRD 生成验收清单 ✓（无 PRD 也返回空清单 + 提示 ✓ 不报错 ✓）。"""
    criteria: list[str] = []
    try:
        from .product_truth import _load as _pt_load
        for prd in _pt_load(Path(root), "prds").values():
            if not isinstance(prd, dict):
                continue
            if str(prd.get("project_id") or "") not in ("", project_id):
                continue
            c = prd.get("content") or {}
            if not isinstance(c, dict):
                continue
            # ★ 键要对上 PRD 的实际字段 ✗（2026-09-14 实测修正 ✓）
            #   PRD content 实际是: overview / functional_requirements /
            #   constraints / decisions / future_considerations ✓
            #   （我原来读 features/feature_list ✗ → 永远取空 ✗）
            for key in ("functional_requirements", "features", "feature_list",
                        "user_stories", "constraints"):
                v = c.get(key)
                if isinstance(v, list):
                    for item in v:
                        s = item if isinstance(item, str) else (
                            str(item.get("title") or item.get("story") or item)
                            if isinstance(item, dict) else str(item))
                        if s.strip() and s.strip() not in criteria:
                            criteria.append(s.strip()[:160])
    except Exception:  # noqa: BLE001 — 失败安全 ✓
        pass
    rec = {
        "project_id": project_id,
        "criteria": [{"index": i, "text": c, "result": None, "note": "", "signed_at": None}
                     for i, c in enumerate(criteria)],
        "created_at": _now_iso(),
        "hint": ("" if criteria else
                 "未从 PRD 取到验收标准（PRD content 为空）→ 可用 "
                 "factory projectos uat <P> --add \"<一条可验收的标准>\" 手工补 ✓"),
    }
    f = _uat_file(root, project_id)
    f.parent.mkdir(parents=True, exist_ok=True)
    _save_json_atomic(f, rec)
    return rec


def uat_get(root: Path | str, project_id: str) -> dict[str, Any]:
    f = _uat_file(root, project_id)
    if not f.is_file():
        return {}
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return d if isinstance(d, dict) else {}


def uat_sign(root: Path | str, project_id: str, index: int, *,
             passed: bool, note: str = "") -> dict[str, Any] | None:
    """逐条签字 ✓（越界/非法索引 → None ✓ 不静默 ✓）。"""
    rec = uat_get(root, project_id)
    items = rec.get("criteria") or []
    if not (0 <= index < len(items)):
        return None
    items[index]["result"] = "passed" if passed else "failed"
    items[index]["note"] = note
    items[index]["signed_at"] = _now_iso()
    _save_json_atomic(_uat_file(root, project_id), rec)
    return rec


def uat_add(root: Path | str, project_id: str, text: str) -> dict[str, Any]:
    rec = uat_get(root, project_id) or build_uat_checklist(root, project_id)
    rec.setdefault("criteria", []).append(
        {"index": len(rec["criteria"]), "text": text[:160],
         "result": None, "note": "", "signed_at": None})
    rec["hint"] = ""
    _save_json_atomic(_uat_file(root, project_id), rec)
    return rec


def uat_status(root: Path | str, project_id: str) -> dict[str, Any]:
    """验收状态汇总 ✓（门要用它 ✓）。"""
    items = (uat_get(root, project_id) or {}).get("criteria") or []
    signed = [i for i in items if i.get("result")]
    failed = [i for i in items if i.get("result") == "failed"]
    return {
        "total": len(items), "signed": len(signed), "failed": len(failed),
        "complete": bool(items) and len(signed) == len(items) and not failed,
        "all_signed": bool(items) and len(signed) == len(items),
    }


def _save_json_atomic(path: Path, data: dict[str, Any]) -> None:
    """原子写 ✓ 临时名带 pid ✓（吸取 _write_list 固定名并发崩溃的教训 ✓）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)
