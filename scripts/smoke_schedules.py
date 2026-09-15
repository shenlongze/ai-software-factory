#!/usr/bin/env python3
"""schedules 面端到端冒烟 —— 调度计划 5 端点（"目标实跑"）。

为什么需要它:
    本仓无 `tests/` + SSoT R16 禁止新增顶层目录 ⇒ 功能验收靠可重复脚本。
    本脚本是刀2 第三域的**验收证据**（schedules 从老区 ops_scheduler 迁到新地基）。

归属（踩过的坑，记下来防重犯）:
    老区组名 `schedules` 归 **decomposition** 域（api-structure §6 映射表:
    「decomposition = task-trees(3) · tasks(3) · schedules(5)」）。
    ★ 第一版我按"契约域叫 work"建了 api/domains/work/ —— 那是**游离目录**，
    registry 里没有该域 ⇒ 路由永不挂载 ⇒ HTTP 404。教训: 建域目录前先查 registry。

覆盖:
    ① 端点数: decomposition=5 · 前域未回退（metrics=4, validation=3）
    ② 空态: GET → {items:[], count:0}
    ③ 创建 → 列表 → 启停 → 删除 全流程
    ④ 错误路径: 间隔过小 → 400 · 不存在 → 404
    ⑤ 真写盘核对 <root>/ops/schedules.json（原子写落地）

用法: python scripts/smoke_schedules.py       退出码 0=通过 / 1=失败
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
os.environ["FACTORY_DATA_DIR"] = str(root)      # 必须在 import 前设好

BASE = "/api/decomposition/schedules"
results: list[tuple[str, bool, str]] = []


def chk(name: str, cond: bool, got: str = "") -> None:
    results.append((name, bool(cond), got if not cond else ""))


def report(code: int) -> int:
    print("── schedules 面端到端冒烟（调度计划 5 端点）")
    ok = sum(1 for _, v, _ in results if v)
    for n, v, got in results:
        print(f"   [{'PASS' if v else 'FAIL'}] {n}" + (f"   ← {got}" if got else ""))
    print(f"   {ok}/{len(results)} 通过")
    return 0 if ok == len(results) else 1


def main() -> int:
    from fastapi.testclient import TestClient

    from ai_factory_os.api import registry
    from ai_factory_os.api.app import create_app

    c = TestClient(create_app(), raise_server_exceptions=False)
    per = {n: len(r.routes) for n, _l, r in registry.iter_routers() if r.routes}

    chk("① decomposition 域端点 = 5（schedules 归位）", per.get("decomposition") == 5, str(per))
    chk("① 前域未回退（metrics=4, validation=3）",
        per.get("metrics") == 4 and per.get("validation") == 3, str(per))

    r = c.get(BASE)
    chk("② 空态 → {items:[], count:0}",
        r.status_code == 200 and r.json() == {"items": [], "count": 0}, f"{r.status_code} {r.text[:80]}")

    r = c.post(BASE, json={"project_id": "p1", "interval_seconds": 5})
    chk("④ 间隔 <10s → 400", r.status_code == 400, str(r.status_code))

    r = c.post(BASE, json={"project_id": "p1", "interval_seconds": 60})
    chk("③ 创建 → 200 且有 sch- id",
        r.status_code == 200 and str(r.json().get("schedule_id", "")).startswith("sch-"),
        f"{r.status_code} {r.text[:100]}")
    sid = str(r.json().get("schedule_id", ""))

    r = c.get(BASE)
    chk("③ 列表 → count=1 且默认 enabled",
        r.status_code == 200 and r.json()["count"] == 1 and r.json()["items"][0]["enabled"] is True,
        str(r.json())[:100])

    chk("③ 停用 → enabled False", c.post(f"{BASE}/{sid}/disable").json().get("enabled") is False, "")
    chk("③ 启用 → enabled True", c.post(f"{BASE}/{sid}/enable").json().get("enabled") is True, "")
    chk("④ 不存在的 id 停用 → 404", c.post(f"{BASE}/sch-nope/disable").status_code == 404, "")

    f = root / "ops" / "schedules.json"
    saved = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    chk("⑤ 真写盘: ops/schedules.json 落地且含历史",
        isinstance(saved, list) and len(saved) == 1 and saved[0]["schedule_id"] == sid
        and len(saved[0].get("history", [])) >= 2,
        (json.dumps(saved, ensure_ascii=False)[:110] if saved is not None else "文件不存在"))

    r = c.delete(f"{BASE}/{sid}")
    chk("③ 删除 → {deleted,id}",
        r.status_code == 200 and r.json().get("deleted") == sid and r.json().get("id") == sid,
        str(r.json()))
    chk("③ 删除后列表回空", c.get(BASE).json() == {"items": [], "count": 0}, "")
    chk("③ 重复删除幂等（不报错）", c.delete(f"{BASE}/{sid}").status_code == 200, "")

    return report(0)


if __name__ == "__main__":
    sys.exit(main())
