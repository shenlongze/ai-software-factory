#!/usr/bin/env python3
"""validation 域端到端冒烟 —— 真起 app · 真打 HTTP · 真写盘（"目标实跑"）。

为什么需要它:
    本仓无 `tests/`（刀29 清理）+ SSoT R16 禁止新增顶层目录 ⇒ 功能验收只能靠
    可重复脚本。本脚本是刀2 首域的**验收证据**: 搬迁后行为必须与老区一致,
    且 fail-closed（未接线的校验不许放行）必须真拦 —— 不是声明, 是跑出来的。

覆盖（6 项）:
    ① approve 成功 + reviewer 落盘        ② APPROVED→CHANGE_REQUESTED 合法
    ③ release 仅放行 APPROVED（业务规则）  ④ 不存在 id → 404
    ⑤ 未定义端点 → 404                    ⑥ fail-closed: 带 ver 未接线 → 拒绝
    另: 真写盘核对（status / history / decision.comment）

用法: python scripts/smoke_validation.py       退出码 0=通过 / 1=失败
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
warnings.filterwarnings("ignore", category=DeprecationWarning)   # httpx/starlette 提示

root = Path(tempfile.mkdtemp())
os.environ["FACTORY_DATA_DIR"] = str(root)          # 必须在 import 前设好


def _seed(recs: dict[str, dict]) -> None:
    d = root / "acceptance"
    d.mkdir(parents=True, exist_ok=True)
    (d / "acceptance.json").write_text(json.dumps(recs, ensure_ascii=False), encoding="utf-8")


def _rec(aid: str, *, version: int = 1, ver: str = "", run: str = "RUN-1") -> dict:
    return {"acceptance_id": aid, "artifact_id": "ART-1", "version": version,
            "verification_id": ver, "source_run_id": run, "status": "PENDING",
            "reviewer": "", "decision": None, "created_at": "t", "updated_at": "t",
            "history": []}


def main() -> int:
    from fastapi.testclient import TestClient

    from ai_factory_os.api.app import create_app, route_count
    from ai_factory_os.api import registry

    app = create_app()
    c = TestClient(app)
    cases: list[tuple[str, bool, str]] = []

    def chk(name: str, cond: bool, got: str = "") -> None:
        cases.append((name, cond, got))

    # 端点数: 修好的读数（不是 len(app.routes) —— 那算的是挂载次数）
    per = {n: len(r.routes) for n, _l, r in registry.iter_routers() if r.routes}
    chk("route_count() == registry 各 router 之和", route_count() == sum(per.values()),
        f"{route_count()} vs {sum(per.values())}")
    chk("validation 域端点 = 3（与老区对齐）", per.get("validation") == 3, str(per))

    _seed({"ACC-ok": _rec("ACC-ok")})
    r = c.post("/api/validation/acceptances/ACC-ok/approve", json={"reviewer": "u1", "comment": "认可"})
    chk("① approve → 200/APPROVED", r.status_code == 200 and r.json().get("status") == "APPROVED",
        f"{r.status_code} {r.json().get('status')}")
    chk("① reviewer 落盘", r.json().get("reviewer") == "u1", str(r.json().get("reviewer")))

    r = c.post("/api/validation/acceptances/ACC-ok/request-change", json={"comment": "要改"})
    chk("② APPROVED→CHANGE_REQUESTED 合法",
        r.status_code == 200 and r.json().get("status") == "CHANGE_REQUESTED",
        f"{r.status_code} {r.json().get('status')}")

    r = c.post("/api/validation/acceptances/ACC-ok/release")
    chk("③ release 仅放行 APPROVED（409）", r.status_code == 409, str(r.status_code))

    r = c.post("/api/validation/acceptances/ACC-nope/approve", json={})
    chk("④ 不存在 id → 404", r.status_code == 404, str(r.status_code))

    r = c.get("/api/validation/acceptances/ACC-ok")
    chk("⑤ 未定义端点 → 404", r.status_code == 404, str(r.status_code))

    # 先核对落盘（下面的 fail-closed 用例会重新 seed, 覆盖本文件）
    saved = json.loads((root / "acceptance" / "acceptance.json").read_text(encoding="utf-8"))
    chk("真写盘: status/history/decision 落地",
        saved["ACC-ok"]["status"] == "CHANGE_REQUESTED"
        and len(saved["ACC-ok"]["history"]) == 2
        and saved["ACC-ok"]["decision"]["comment"] == "要改",
        json.dumps(saved.get("ACC-ok", {}), ensure_ascii=False)[:120])

    _seed({"ACC-v": _rec("ACC-v", version=9, ver="VER-1")})
    r = c.post("/api/validation/acceptances/ACC-v/approve", json={"reviewer": "u"})
    chk("⑥ fail-closed: 带 ver 未接线 → 拒绝（409/503）",
        r.status_code in (409, 503), f"{r.status_code}")

    print("── validation 域端到端冒烟（真起 app · 真打 HTTP · 真写盘）")
    ok = sum(1 for _, v, _ in cases if v)
    for n, v, got in cases:
        print(f"   [{'PASS' if v else 'FAIL'}] {n}" + (f"   ← {got}" if not v else ""))
    print(f"   {ok}/{len(cases)} 通过")
    return 0 if ok == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
