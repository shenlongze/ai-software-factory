"""Factory API —— 视图接口（供 Web/HTML 调用）。

★ 原则（Founder 定的）:
  · **CLI 是地基; API 由 CLI 派生** —— 本服务不重写业务逻辑, 只把
    `services/work/*` 已经算好的**视图数据**序列化出去。
  · 一能力一处: 视图逻辑归服务层（`user_view` / `data_flow` / `keypath` / `priority`）,
    CLI 与 API 共用 —— 不各写一套。
  · ★ 唯一例外（也是同一条原则）: `POST …/priority` —— 人工改优先级要能从页面点
    （Founder: "支持人为干预"）; 它同样只是**薄代理**到服务层函数, 不新造规则、不落第二份数据。

接口:
  GET  /                        → HTML 页面（用户视图演示）
  GET  /api/health               → {"ok": true}
  GET  /api/trees                → 任务树列表
  GET  /api/trees/{plan_id}      → 任务树原始数据
  GET  /api/trees/{plan_id}/todo → ★ 投影 A: 层级待办清单（看进度）
  GET  /api/trees/{plan_id}/flow → ★ 投影 B: 功能链路图（看关系）
  GET  /api/trees/{plan_id}/dataflow → ★ 投影 C: 数据流程图（看数据: 实体 + 谁碰它 + 实体间关系）
  GET  /api/trees/{plan_id}/both → 三个投影一起（页面一次拉完）
  POST /api/trees/{plan_id}/priority → ★ 唯一写口: 人工改优先级（P0~P3 / "auto"=回到自动）

运行:
  .venv/bin/python -m apps.api.main                    # 默认 127.0.0.1:8787
  .venv/bin/python -m apps.api.main --root ~/.factory --port 8787
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from ai_factory_os.services.work import data_flow as DF
from ai_factory_os.services.work import decomposition as D
from ai_factory_os.services.work import user_view as UV

app = FastAPI(title="Factory API", version="0.1.0")

#: 数据根（由 main() 注入）
_ROOT = Path.home() / ".factory"


def _find_tree(plan_id: str) -> dict[str, Any]:
    """★ 按 plan_id 找树 —— 复用 decomposition 的读取（含 R27 的"两处"检测）。"""
    tree = D.load_tree(_ROOT, plan_id)
    if not tree:
        raise HTTPException(status_code=404, detail=f"任务树不存在: {plan_id}")
    return tree


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "root": str(_ROOT)}


@app.get("/api/trees")
def list_trees() -> dict[str, Any]:
    """任务树列表（含项目、状态、叶数与进度 —— 供首页选择）。"""
    out: list[dict[str, Any]] = []
    for t in D.list_trees(_ROOT):
        try:
            s = D.tree_summary(t)
        except Exception:  # noqa: BLE001 — 单棵树损坏不影响列表
            continue
        out.append({
            "plan_id": str(t.get("plan_id") or ""),
            "project_id": str(t.get("project_id") or ""),
            "status": str(t.get("status") or ""),
            "leaves": s.get("leaves", 0),
            "done": s.get("done", 0),
            "percent": s.get("percent", "0"),
        })
    return {"trees": out, "count": len(out)}


@app.get("/api/trees/{plan_id}")
def get_tree(plan_id: str) -> JSONResponse:
    return JSONResponse(_find_tree(plan_id))


@app.get("/api/trees/{plan_id}/todo")
def get_todo(plan_id: str) -> JSONResponse:
    """★ 投影 A: 层级待办清单（看"要做啥、到哪了"）。"""
    return JSONResponse(UV.build_todo(_find_tree(plan_id)))


@app.get("/api/trees/{plan_id}/flow")
def get_flow(plan_id: str) -> JSONResponse:
    """★ 投影 B: 功能链路图（看"有什么、怎么串"）。"""
    return JSONResponse(UV.build_flow(_find_tree(plan_id)))


@app.get("/api/trees/{plan_id}/dataflow")
def get_dataflow(plan_id: str) -> JSONResponse:
    """★ 投影 C: 数据流程图（看数据 —— 只画真实来源, 见 services/work/data_flow.py）。"""
    tree = _find_tree(plan_id)
    pid = str(tree.get("project_id") or "")
    return JSONResponse(DF.build_data_flow(tree, (_ROOT / "projects" / pid) if pid else None))


@app.post("/api/trees/{plan_id}/priority")
def set_priority(plan_id: str, payload: dict[str, Any]) -> JSONResponse:
    """★ 唯一的【写】接口: 人工改优先级（Founder: "支持人为干预"）。

    与 CLI 同源 —— 走同一个服务层函数（`decomposition.set_node_priority` / `clear_node_priority`）,
    本接口不重写规则、不落第二份数据（API 由 CLI 派生 —— 这条原则对写接口同样成立）。
    payload: {"node_id": "…", "priority": "P0"|"P1"|"P2"|"P3"|"auto", "reason": "…"}
      priority="auto" ⇒ 清除人工值, 回到自动兜底（关键路径）。
    """
    tree = _find_tree(plan_id)
    pid = str(tree.get("project_id") or "")
    node_id = str(payload.get("node_id") or "")
    want = str(payload.get("priority") or "").strip()
    if not node_id or not want:
        raise HTTPException(status_code=400, detail="需要 node_id 与 priority")
    try:
        if want.lower() == "auto":
            D.clear_node_priority(_ROOT, plan_id, node_id=node_id, project_id=pid)
        else:
            D.set_node_priority(_ROOT, plan_id, node_id=node_id, priority=want,
                                source="manual", reason=str(payload.get("reason") or ""),
                                project_id=pid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    fresh = _find_tree(plan_id)
    return JSONResponse({"ok": True, "todo": UV.build_todo(fresh)})


@app.get("/api/trees/{plan_id}/both")
def get_both(plan_id: str) -> JSONResponse:
    """三个投影一起 —— 页面一次拉完（★ 说的是同一件事, 一起给才不会不一致）。"""
    tree = _find_tree(plan_id)
    pid = str(tree.get("project_id") or "")
    return JSONResponse({
        "plan_id": plan_id,
        "todo": UV.build_todo(tree),
        "flow": UV.build_flow(tree),
        "dataflow": DF.build_data_flow(tree, (_ROOT / "projects" / pid) if pid else None),
    })


@app.get("/status", response_class=HTMLResponse)
def status_page() -> HTMLResponse:
    """状态页 —— 活清单 + 工作日志 + 实时读数（由 scripts/build_status.py 生成 ✓; 没生成就提示怎么生成 ✓）。

    ★ 2026-09-22（Founder: "添加到 html 和 todolist 中, 要留痕"）
    """
    page = Path(__file__).parent / "status.html"
    if not page.is_file():
        return HTMLResponse(
            "<h1>状态页还没生成</h1><p>跑一下: <code>python scripts/build_status.py</code></p>",
            status_code=200,
        )
    return HTMLResponse(page.read_text(encoding="utf-8"))


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    page = Path(__file__).parent / "index.html"
    if not page.is_file():
        return HTMLResponse("<h1>Factory</h1><p>index.html 缺失</p>", status_code=500)
    return HTMLResponse(page.read_text(encoding="utf-8"))


def main() -> None:
    global _ROOT
    ap = argparse.ArgumentParser(prog="factory-api", description="Factory 只读视图 API")
    ap.add_argument("--root", default=str(Path.home() / ".factory"), help="数据根")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8787)
    args = ap.parse_args()
    _ROOT = Path(args.root).expanduser()
    import uvicorn
    print(f"  Factory API  ·  root={_ROOT}")
    print(f"  http://{args.host}:{args.port}/")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
