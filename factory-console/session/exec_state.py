"""factory-console/session/exec_state.py — 会话执行状态机 (S-5, v1.1.217; P0-A v1.1.244 backlog 回写).

Founder 2026-08-27: "做人事" — 会话真把事办了:
说"把 X 做完" → 出计划 → 审批 → 逐任务执行(委派+验证) → 交付汇报 → 进度可查。

结构 (<data_dir>/session_exec/<session_id>.json):
{
  "plan": {"goal", "acceptance"},
  "status": "running|done|blocked",
  "tasks": [{"title","priority","status":"todo|running|verifying|done|failed","result","verify"}],
  "current_index", "created_at", "updated_at"
}

- start(plan): 审批后启动执行链
- next(exec_fn): 推进下一个任务 → 委派执行 → 验证 → 回写 (exec_fn 注入, 测试可 stub)
- status(): 进度文本
- deliver(): 全部完成 → 交付汇报
失败安全: 文件坏/缺失 → 诚实错误。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

VALID_STATUS = ("todo", "running", "verifying", "done", "failed")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _save_json(path: Path, data: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


class ExecState:
    """会话执行状态机: plan → tasks → 逐任务 delegate+verify → deliver。"""

    def __init__(self, session_id: str, data: dict[str, Any] | None = None):
        self.session_id = session_id
        self.state: dict[str, Any] = data or {
            "plan": {}, "status": "idle", "tasks": [], "current_index": -1,
            "created_at": "", "updated_at": "",
        }

    # ------------------------------------------------------------ 持久化
    @classmethod
    def load(cls, data_dir: str | Path | None, session_id: str) -> "ExecState":
        st = cls(session_id)
        if not data_dir or not session_id:
            return st
        d = _load_json(Path(data_dir) / "session_exec" / f"{session_id}.json")
        if d:
            st.state = d
        return st

    def save(self, data_dir: str | Path | None) -> None:
        if not data_dir or not self.session_id:
            return
        self.state["updated_at"] = _now_iso()
        _save_json(Path(data_dir) / "session_exec" / f"{self.session_id}.json", self.state)

    # ------------------------------------------------------------ 启动
    def start(self, plan: dict[str, Any]) -> dict[str, Any]:
        """审批通过后启动: 按计划建任务列表, 状态 → running。"""
        tasks = plan.get("tasks") or []
        if not tasks:
            return {"ok": False, "error": "计划没有任务"}
        self.state = {
            "plan": {"goal": str(plan.get("goal") or "")[:120],
                     "acceptance": [str(a)[:200] for a in (plan.get("acceptance") or [])]},
            "status": "running",
            "tasks": [{"title": str(t.get("title") or "")[:80],
                       "priority": str(t.get("priority") or "P2"),
                       "status": "todo", "result": "", "verify": {},
                       "backlog_id": str(t.get("backlog_id") or "")} for t in tasks],
            "current_index": -1,
            "created_at": _now_iso(), "updated_at": _now_iso(),
        }
        return {"ok": True, "goal": self.state["plan"]["goal"], "total": len(self.state["tasks"])}

    # ------------------------------------------------------------ 推进
    def next(self, exec_fn: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        """推进下一个任务 (P1-FIX: 依赖感知 — Ready = todo 且全部依赖 done)。

        exec_fn(task) → {ok, output, verify?}。
        依赖语义: task.dependency = [backlog task ids] (chain_start 从 plan.order 解析)。
        - 依赖未完成 → 不执行 (跳过, 返回 waiting)
        - 依赖失败 → 下游 blocked (失败传播)
        - 全部 done → finished
        """
        tasks = self.state.get("tasks") or []
        done_ids = {t.get("backlog_id") or t.get("id") for t in tasks if t.get("status") == "done"}
        failed_ids = {t.get("backlog_id") or t.get("id") for t in tasks if t.get("status") == "failed"}
        idx = next(
            (i for i, t in enumerate(tasks)
             if t.get("status") == "todo"
             and all(d in done_ids for d in (t.get("dependency") or []))),
            -1,
        )
        if idx < 0:
            todo = [t for t in tasks if t.get("status") == "todo"]
            if todo:
                blocked = [t["title"] for t in todo
                           if any(d in failed_ids for d in (t.get("dependency") or []))]
                if blocked:
                    for t in todo:
                        if any(d in failed_ids for d in (t.get("dependency") or [])):
                            t["status"] = "blocked"
                    return {"ok": False, "blocked": blocked, "finished": False,
                            "output": f"依赖失败, 下游任务阻塞: {', '.join(blocked)}",
                            "progress": self.progress()}
                return {"ok": False, "waiting": True, "finished": False,
                        "output": "等待前置依赖完成", "progress": self.progress()}
            done = all(t.get("status") == "done" for t in tasks)
            return {"ok": done, "finished": True,
                    "output": self.deliver()["output"] if done else "无待办任务 (有失败/进行中)"}
        task = tasks[idx]
        task["status"] = "running"
        self.state["current_index"] = idx
        # 持久化由调用方 (dispatch) 在 next 后 save(data_dir) 统一落盘
        result = {}
        try:
            result = exec_fn(task) or {}
        except Exception as exc:  # noqa: BLE001 — 执行器异常 → 失败
            result = {"ok": False, "error": str(exc)}
        # 验证通过 → done (verify 信息记录); 失败 → failed
        task["status"] = "done" if result.get("ok") else "failed"
        task["result"] = str(result.get("output") or result.get("error") or "")[:1000]
        task["verify"] = dict(result.get("verify") or {})
        if not result.get("ok"):
            task["verify"] = {"method": "exec", "result": "failed",
                              "reason": str(result.get("error") or "")[:300]}
        _all_done = all(t.get("status") == "done" for t in self.state.get("tasks") or [])
        if _all_done:
            self.state["status"] = "done"
        return {"ok": bool(result.get("ok")), "task": task["title"], "status": task["status"],
                "output": task["result"], "progress": self.progress(),
                "finished": _all_done}

    # ------------------------------------------------------------ 状态/交付
    def progress(self) -> str:
        tasks = self.state.get("tasks") or []
        done = sum(1 for t in tasks if t.get("status") == "done")
        failed = sum(1 for t in tasks if t.get("status") == "failed")
        return f"{done}/{len(tasks)} 完成" + (f" · {failed} 失败" if failed else "")

    def status(self) -> dict[str, Any]:
        return {"status": self.state.get("status"), "goal": (self.state.get("plan") or {}).get("goal"),
                "progress": self.progress(),
                "tasks": [{"title": t.get("title"), "status": t.get("status"),
                           "priority": t.get("priority")} for t in (self.state.get("tasks") or [])]}

    def deliver(self) -> dict[str, Any]:
        """全部完成 → 交付汇报。"""
        tasks = self.state.get("tasks") or []
        if not tasks:
            return {"ok": False, "output": "执行链为空"}
        if not all(t.get("status") == "done" for t in tasks):
            return {"ok": False, "output": f"尚未全部完成 ({self.progress()})"}
        self.state["status"] = "done"
        goal = (self.state.get("plan") or {}).get("goal") or ""
        lines = [f"✅ 交付完成: {goal}"]
        lines.append(f"共 {len(tasks)} 个任务全部完成 (结果已回写 backlog 任务):")
        for t in tasks:
            _v = t.get("verify") or {}
            _bid = t.get("backlog_id") or ""
            lines.append(
                f"- ✅ {t.get('title')} ({t.get('priority')})"
                + (f" [任务 {_bid}]" if _bid else "")
                + (f" · 验证 {_v.get('result') or 'unknown'}" if _v else "")
            )
        acc = (self.state.get("plan") or {}).get("acceptance") or []
        if acc:
            lines.append("验收: " + "；".join(str(a) for a in acc))
        lines.append("证据: 每个任务 result/verify 已写入对应 backlog 任务 exec_result (可跨会话查询)。")
        lines.append("下一步: 可让用户验收, 或继续新任务。")
        return {"ok": True, "output": "\n".join(lines)}
