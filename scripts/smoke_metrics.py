#!/usr/bin/env python3
"""metrics 域端到端冒烟 —— Control Tower 4 个投影端点（"目标实跑"）。

为什么需要它:
    本仓无 `tests/` + SSoT R16 禁止新增顶层目录 ⇒ 功能验收靠可重复脚本。
    本脚本是刀2 第二域（metrics · Control Tower）的**验收证据**。

覆盖:
    ① 端点数 = 4（与老区 control-tower 组对齐）
    ② 未接线 → 返回 unwired 标注（不是假 0, 也不是空页）—— 三条投影各自自证
    ③ 注入真实形状数据 → work/workforce 计数正确
    ④ governance 只取 PENDING · realtime 按时间倒序
    ⑤ HTTP 层同样拿到注入后的结果（注入点与 HTTP 走同一模块级钩子）

用法: python scripts/smoke_metrics.py       退出码 0=通过 / 1=失败
副作用: 全程 tempdir + 内存注入, 不碰真实数据 ✓
"""
from __future__ import annotations

import os
import sys
import tempfile
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
warnings.filterwarnings("ignore", category=DeprecationWarning)

os.environ["FACTORY_DATA_DIR"] = tempfile.mkdtemp()

ENTITIES = [
    {"id": "C-1", "type": "conv", "status": "OPEN"},
    {"id": "C-2", "type": "conv", "status": "CLOSED"},
    {"id": "T-1", "type": "task", "status": "RUNNING", "title": "跑任务"},
    {"id": "T-2", "type": "task", "status": "READY", "title": "等依赖"},
    {"id": "T-3", "type": "task", "status": "BLOCKED", "title": "被挡"},
    {"id": "T-4", "type": "task", "status": "FAILED", "title": "失败"},
    {"id": "T-5", "type": "task", "status": "DONE", "title": "完成"},
    {"id": "M-1", "type": "msg", "status": ""},          # 非 conv/task → 不该计数
]
RUNS = [{"state": "SUCCESS"}, {"state": "SUCCESS"}, {"state": "FAILED"}]
APPROVALS = [{"approval_id": "A-1", "decision": "PENDING", "subject_type": "release"},
             {"approval_id": "A-2", "decision": "APPROVED"}]
EVENTS = [{"event_id": "E-1", "timestamp": "2026-09-15T10:00:00", "event_type": "a"},
          {"event_id": "E-2", "timestamp": "2026-09-15T12:00:00", "event_type": "b"}]

results: list[tuple[str, bool, str]] = []


def chk(name: str, cond: bool, got: str = "") -> None:
    results.append((name, bool(cond), got if not cond else ""))


def main() -> int:
    from fastapi.testclient import TestClient

    from ai_factory_os.api import registry
    from ai_factory_os.api.app import create_app
    from ai_factory_os.services.metrics import control_tower as ct

    app = create_app()
    c = TestClient(app)
    per = {n: len(r.routes) for n, _l, r in registry.iter_routers() if r.routes}

    chk("① metrics 域端点 = 4（与老区 control-tower 对齐）",
        per.get("metrics") == 4, str(per))
    chk("① validation 域仍 = 3（前域未回退）", per.get("validation") == 3, str(per))

    # ② 未接线：三条投影各自给 unwired 标注
    #    注: work_overview 在 entities 缺失时【短路】返回（不会再去查 production_runs），
    #    所以此处只应标 ["entities"] —— 断言按真实设计写, 不按我的想象写。
    r = c.get("/api/metrics/control-tower")
    body = r.json()
    chk("② 未接线 → 200 且标注 unwired（entities 短路）",
        r.status_code == 200 and body["work"].get("unwired") == ["entities"],
        str(body.get("work"))[:120])
    chk("② 未接线不为空页（结构完整）",
        set(body) >= {"work", "workforce", "governance", "realtime", "calculated_at"}, str(list(body)))
    chk("② governance 未接线也标注",
        body["governance"].get("unwired") == ["approvals"], str(body["governance"])[:80])

    # ③ 注入真实形状 → 计数正确
    ct.bind_lookups(entities=lambda _root: ENTITIES,
                    production_runs=lambda _root: RUNS,
                    approvals=lambda _root: APPROVALS,
                    audit_events=lambda _root: EVENTS)

    w = c.get("/api/metrics/control-tower").json()["work"]
    chk("③ conversations 只数 conv（=2）", w["conversations"] == 2, str(w["conversations"]))
    chk("③ tasks 只数 task（=5）", w["tasks"] == 5, str(w["tasks"]))
    chk("③ executions = 3 + 状态分布", w["executions"] == 3 and w["execution_states"] == {"SUCCESS": 2, "FAILED": 1},
        f"{w['executions']} {w['execution_states']}")
    chk("③ task_states 分布正确", w["task_states"].get("RUNNING") == 1 and w["task_states"].get("DONE") == 1,
        str(w["task_states"]))
    chk("③ 注入后不再有 unwired", "unwired" not in w, str(w.get("unwired")))

    f = c.get("/api/metrics/control-tower/workforce").json()
    chk("④ workforce: running/waiting/blocked/error = 1/1/1/1",
        (f["running"], f["waiting"], f["blocked"], f["error"]) == (1, 1, 1, 1),
        f"{f['running']}/{f['waiting']}/{f['blocked']}/{f['error']}")
    chk("④ idle = 5-4 = 1", f["idle"] == 1, str(f["idle"]))
    chk("④ active_tasks 只含活动态", len(f["active_tasks"]) == 4, str(len(f["active_tasks"])))

    g = c.get("/api/metrics/control-tower/governance").json()
    chk("④ governance 只数 PENDING（=1）",
        g["pending_approvals"] == 1 and g["items"][0]["approval_id"] == "A-1", str(g))

    rt = c.get("/api/metrics/control-tower/realtime").json()
    chk("④ realtime 按时间倒序（最新在前）",
        rt["events"][0]["event_id"] == "E-2" and rt["count"] == 2, str(rt))

    print("── metrics 域端到端冒烟（Control Tower 4 投影端点）")
    ok = sum(1 for _, v, _ in results if v)
    for n, v, got in results:
        print(f"   [{'PASS' if v else 'FAIL'}] {n}" + (f"   ← {got}" if got else ""))
    print(f"   {ok}/{len(results)} 通过")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
