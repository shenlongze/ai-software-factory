#!/usr/bin/env python3
"""decomposition 域 · 任务树面端到端冒烟（"目标实跑"）。

为什么需要它:
    本仓无 `tests/` + R16 禁新增顶层目录 ⇒ 功能验收靠可重复脚本。
    本脚本是刀2 第三域（续）**任务树面**的验收证据。

覆盖:
    ① 端点数: decomposition ≥ 8（schedules 5 + 任务树 3）
    ② 树不存在 → 404
    ③ 实体层未接线 → progress/status 返回 **unwired 标注**（结构完整，非假 0、非空页）
    ④ ★ 写操作 **fail-closed**: POST /tasks/{id}/status 未接线 → **503 拒绝**
       （绝不静默通过 —— 这是迁移里最要紧的一条语义）
    ⑤ 树存在但实体未接线时: tree_status 仍返回 title（树自己的数据不依赖实体层）

用法: python scripts/smoke_decomposition_tasks.py    退出码 0=通过 / 1=失败
副作用: 全程 tempdir 数据根, 不碰真实数据 ✓
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
warnings.filterwarnings("ignore", category=DeprecationWarning)

root = Path(tempfile.mkdtemp())
os.environ["FACTORY_DATA_DIR"] = str(root)

TREE = {"task_tree_id": "tt-1", "title": "示例树", "root_task": "T-1",
        "subtasks": ["T-2", "T-3"]}
results: list[tuple[str, bool, str]] = []


def chk(name: str, cond: bool, got: str = "") -> None:
    results.append((name, bool(cond), got if not cond else ""))


def main() -> int:
    # 造一棵树（本域自己的数据，端点不依赖实体层就能读到它）
    d = root / "ops" / "tasktree"
    d.mkdir(parents=True, exist_ok=True)
    (d / "trees.json").write_text(json.dumps([TREE], ensure_ascii=False), encoding="utf-8")

    from fastapi.testclient import TestClient

    from ai_factory_os.api import registry
    from ai_factory_os.api.app import create_app

    c = TestClient(create_app(), raise_server_exceptions=False)
    per = {n: len(r.routes) for n, _l, r in registry.iter_routers() if r.routes}

    chk("① decomposition 域端点 ≥ 8（schedules 5 + 任务树 3）",
        per.get("decomposition", 0) >= 8, str(per))

    base = "/api/decomposition"
    r = c.get(f"{base}/task-trees/tt-nope/progress")
    chk("② 树不存在 → 404", r.status_code == 404, str(r.status_code))

    r = c.get(f"{base}/task-trees/tt-1/progress")
    body = r.json() if r.status_code == 200 else {}
    chk("③ 未接线 → 200 且带 unwired 标注（非假 0）",
        r.status_code == 200 and body.get("unwired") == ["entities"],
        f"{r.status_code} {str(body)[:110]}")

    r = c.get(f"{base}/task-trees/tt-1/status")
    body = r.json() if r.status_code == 200 else {}
    chk("⑤ 未接线时树的自身数据仍可读（title）",
        r.status_code == 200 and body.get("title") == "示例树", f"{r.status_code} {str(body)[:90]}")
    chk("⑤ 未接线时 progress 被嵌套并被标注",
        isinstance(body.get("progress"), dict) and body["progress"].get("unwired") == ["entities"],
        str(body.get("progress"))[:90])

    r = c.post(f"{base}/tasks/T-1/status", json={"status": "COMPLETED"})
    chk("④ ★ 写操作 fail-closed：未接线 → 503 拒绝",
        r.status_code == 503, f"{r.status_code} {r.text[:110]}")

    # ⑤ 接线后应能真读实体（用假实体验证投影计算，不假装端到端）
    from ai_factory_os.services.decomposition import tasks as T
    fake = {"T-1": {"id": "T-1", "type": "task", "status": "ACTIVE"},
            "T-2": {"id": "T-2", "type": "task", "status": "COMPLETED"},
            "T-3": {"id": "T-3", "type": "task", "status": "BLOCKED"}}
    T.bind_lookups(get_entity=lambda _r, eid: fake[eid],
                   store_entity=lambda _r, e: e, bump_version=lambda e, **k: e)
    r = c.get(f"{base}/task-trees/tt-1/progress")
    body = r.json() if r.status_code == 200 else {}
    chk("⑤ 接线后: total=2 · completed=1 · 50% · blocked 命中",
        body.get("total_units") == 2 and body.get("completed_units") == 1
        and body.get("percentage") == 50 and body.get("blocked") == ["T-3"],
        str(body)[:140])
    chk("⑤ 接线后不再有 unwired", "unwired" not in body, str(body.get("unwired")))

    r = c.post(f"{base}/tasks/T-1/status", json={"status": "COMPLETED"})
    chk("④ 接线后写操作放行（200）", r.status_code == 200 and r.json().get("status") == "COMPLETED",
        f"{r.status_code} {r.text[:90]}")

    print("── decomposition 域 · 任务树面冒烟")
    ok = sum(1 for _, v, _ in results if v)
    for n, v, got in results:
        print(f"   [{'PASS' if v else 'FAIL'}] {n}" + (f"   ← {got}" if got else ""))
    print(f"   {ok}/{len(results)} 通过")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
