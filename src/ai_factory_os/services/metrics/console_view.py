"""services.metrics.console_view — Human Console 只读聚合（七域）。

★ 2026-09-15 新增。功能来源: 老区 `service.py:264 ConsoleService`（4,926 行）的
  **dashboard / approvals 两个视图** —— 但**只做新区需要的那部分**, 不搬老区包袱。

【老区那份里有什么, 我们为什么不搬】
 老区 ConsoleService 除了聚合, 还带着: 旧项目懒迁移（_migrate_legacy_spaces）·
  workspace 项目定义 ∪ org 项目的并集去重与 lifecycle 聚合 · 示例目录过滤 ·
  ProjectSpaceStore 目录镜像回填 … 这些是**老区自己的历史包袱**（要删的那套）。
 新区需要的是"看一眼现在什么状态" —— 所以这里只做**七域只读计数 + 待审批清单**。

【为什么依赖注入 9 个 store 而不是内部自建】
 装配点（apps/cli/commands.py:_open_console_service）已经把新地基的 store 全传进来了:
 workspace_manager / task_store / agent_registry / product_store / decision_store /
 recommendation_store / experience_store / usage_store / provider_registry
 ⇒ 保持同签名: 装配点**零改动**, 且全部 store 可选（缺任一 → 该域按空数据, 失败安全）。

【只读铁律】本模块不执行、不审批; 唯一副作用在调用方（发 console.dashboard.viewed 审计）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

__all__ = ["ConsoleView"]

#: 默认活动条数
DEFAULT_RECENT_LIMIT = 10


class ConsoleView:
    """Human Console 只读聚合视图（七域快照; 依赖全可选, 失败安全）。"""

    def __init__(
        self,
        *,
        workspace_manager: Any = None,
        task_store: Any = None,
        agent_registry: Any = None,
        product_store: Any = None,
        decision_store: Any = None,
        recommendation_store: Any = None,
        experience_store: Any = None,
        usage_store: Any = None,
        provider_registry: Any = None,
        event_store: Any = None,
        project_store: Any = None,
        root: Any = None,
    ) -> None:
        self._workspace = workspace_manager
        self._tasks = task_store
        self._agents = agent_registry
        self._product = product_store
        self._decisions = decision_store
        self._recs = recommendation_store
        self._exp = experience_store
        self._usage = usage_store
        self._providers = provider_registry
        self._events = event_store
        self._projects = project_store
        self._root = Path(root) if root else None

    # ---------------------------------------------------------------- 工具（全部失败安全）

    @staticmethod
    def _safe(fn: Any, default: Any) -> Any:
        """调用取数函数; 依赖缺失/异常 → default（Console 永不因数据缺失失败）。"""
        try:
            return fn()
        except Exception:  # noqa: BLE001
            return default

    def _list(self, store: Any) -> list[Any]:
        if store is None:
            return []
        for name in ("list_all", "list", "load_all", "recent"):
            fn = getattr(store, name, None)
            if callable(fn):
                got = self._safe(lambda: fn(), [])
                if isinstance(got, dict):
                    return list(got.values())
                return list(got or [])
        return []

    # ---------------------------------------------------------------- 七域

    def list_projects(self) -> list[dict[str, Any]]:
        """项目清单（org 项目 + 项目目录下有 product.json 的真实工作区）。"""
        out: dict[str, dict[str, Any]] = {}
        for p in self._list(self._projects):
            pid = str(getattr(p, "id", "") or "")
            if pid:
                out[pid] = {"id": pid, "name": getattr(p, "name", "") or pid,
                            "status": str(getattr(p, "state", "") or getattr(p, "status", "") or "")}
        if self._root is not None:
            pj = self._root / "projects"
            if pj.is_dir():
                for d in pj.iterdir():
                    if d.is_dir() and d.name not in out:
                        out[d.name] = {"id": d.name, "name": d.name, "status": "active"}
        return list(out.values())

    def list_approvals(self) -> list[dict[str, Any]]:
        """审批请求清单（★ 产品侧 9c 状态机 — ProductStore.approvals.json; 只读不决定）。

        口径照老区 ConsoleService.list_approvals:
          · 数据源 = ProductStore.list_requests()
          · risk 投影: 绑定 Artifact 的 confidence < 0.5 → "medium"（低置信需人确认）
        """
        store = self._product
        if store is None:
            return []
        reqs = self._safe(lambda: store.list_requests(), [])
        out: list[dict[str, Any]] = []
        for r in reqs or []:
            conf = 0.0
            try:
                art = store.get_artifact(r.artifact_id) if getattr(r, "artifact_id", "") else None
                if art is not None:
                    conf = float(getattr(art, "confidence", 0.0) or 0.0)
            except Exception:  # noqa: BLE001 — 产物缺失 → 置信度按 0（失败安全）
                conf = 0.0
            out.append({
                "id": getattr(r, "id", ""),
                "artifact_id": getattr(r, "artifact_id", ""),
                "gate": getattr(r, "gate", ""),
                "status": str(getattr(r, "status", "") or ""),
                "confidence": conf,
                "risk": "medium" if conf < 0.5 else "",
                "idea_id": getattr(r, "idea_id", None),
                "requested_at": getattr(r, "requested_at", ""),
            })
        return out

    def _agent_summaries(self) -> list[dict[str, Any]]:
        reg = self._agents
        if reg is None:
            return []
        items: list[Any] = []
        st = getattr(reg, "store", None)
        if st is not None:
            items = self._list(st)
        if not items:
            items = self._list(reg)
        out = []
        for a in items:
            aid = str(getattr(a, "id", None) or (a.get("id") if isinstance(a, dict) else "") or "")
            out.append({"id": aid,
                        "status": str(getattr(a, "status", None)
                                      or (a.get("status") if isinstance(a, dict) else "") or "")})
        return out

    def _cost_summary(self) -> dict[str, Any]:
        """成本域: 从 provider usage 汇总（无 usage store → 空口径）。"""
        if self._usage is None:
            return {"total_tokens": 0, "total_cost": 0.0, "calls": 0}
        data = self._safe(lambda: self._usage.list_all(), {})
        if isinstance(data, list):
            data = {str(i): v for i, v in enumerate(data)}
        tot_tok = tot_cost = 0
        calls = 0
        for v in (data or {}).values():
            d = v if isinstance(v, dict) else {}
            calls += 1
            tot_tok += int(d.get("total_tokens") or 0)
            tot_cost += float(d.get("estimated_cost_usd") or d.get("cost") or 0.0)
        return {"total_tokens": tot_tok, "total_cost": round(tot_cost, 6), "calls": calls}

    def _experience_summary(self) -> dict[str, Any]:
        recs = self._list(self._exp)
        by_result: dict[str, int] = {}
        for r in recs:
            k = str(getattr(r, "result", "") or "")
            k = getattr(k, "value", k)
            by_result[k] = by_result.get(k, 0) + 1
        succ = by_result.get("success", 0)
        return {
            "total": len(recs),
            "by_result": by_result,
            "success_rate": round(succ / len(recs), 4) if recs else 0.0,
        }

    def _recent_events(self, limit: int) -> list[dict[str, Any]]:
        ev = self._events
        if ev is None:
            return []
        got = self._safe(lambda: ev.recent(limit), [])
        out = []
        for e in got or []:
            out.append({"seq": getattr(e, "seq", None), "type": str(getattr(e, "type", "") or ""),
                        "source": str(getattr(e, "source", "") or ""),
                        "timestamp": str(getattr(e, "timestamp", "") or "")})
        return out

    def fleet(self) -> dict[str, Any]:
        """★ 舰队视图 —— 谁在做什么、谁空闲、谁干完了（吸收自 amux 的 Worker awareness）。

        amux 原文: "every worker sees the fleet (who is live, what they own, what they are
        doing)" —— 一个调度平台如果不能回答"此刻谁在干什么", 用它的人就只能盲猜。

        数据源（都是已有事实, 不新增存储）:
          · 任务树的叶: status='claimed' → claimed_by/claimed_at  ⇒ **正在做**
          · execution 记录: agent_id + status + created_at        ⇒ **做过什么 / 做完没**
        ⇒ 合成一张 "worker → 当前任务 + 最近活动" 的表。

        实现: 扫 root 下所有任务树 + execution 记录（失败安全: 缺/坏 → 空表, 不抛）。
        """
        workers: dict[str, dict[str, Any]] = {}
        busy_leaves: list[dict[str, Any]] = []
        if self._root is None:                      # 无数据根 ⇒ 空舰队（不抛）
            return {"workers": [], "busy": 0, "idle": 0, "busy_leaves": []}

        # ── ① 正在做: 任务树里 claimed 的叶
        try:
            from ai_factory_os.services.work import decomposition as D

            for t in D.list_trees(self._root):
                pid = str(t.get("plan_id") or "")
                tree = D.load_tree(self._root, pid)
                if not tree:
                    continue
                for n in tree.get("nodes") or []:
                    if str(n.get("status") or "").lower() != "claimed":
                        continue
                    who = str(n.get("claimed_by") or "(未记名)")
                    busy_leaves.append({
                        "worker": who, "plan_id": pid,
                        "node_id": str(n.get("id") or ""),
                        "task": str(n.get("title") or ""),
                        "since": str(n.get("claimed_at") or ""),
                    })
                    w = workers.setdefault(who, {"worker": who, "status": "busy",
                                                 "current_task": "", "since": "",
                                                 "done": 0, "failed": 0})
                    w["current_task"] = str(n.get("title") or "")
                    w["since"] = str(n.get("claimed_at") or "")
        except Exception:  # noqa: BLE001 — 失败安全
            pass

        # ── ② 做过什么: execution 记录（agent_id × status）
        try:
            from ai_factory_os.services.execution.runtime.store import RuntimeStore

            for req in RuntimeStore(self._root / "runtime").list_executions():
                who = str(req.agent_id or "").strip()
                if not who:
                    continue
                w = workers.setdefault(who, {"worker": who, "status": "idle",
                                             "current_task": "", "since": "",
                                             "done": 0, "failed": 0})
                st = str(getattr(req.status, "value", req.status)).upper()
                if st in ("COMPLETED", "SUCCESS", "SUCCEEDED"):
                    w["done"] = int(w.get("done") or 0) + 1
                elif st in ("FAILED", "ERROR"):
                    w["failed"] = int(w.get("failed") or 0) + 1
        except Exception:  # noqa: BLE001
            pass

        rows = sorted(workers.values(),
                      key=lambda w: (w.get("status") != "busy", -(int(w.get("done") or 0))))
        return {
            "workers": rows,
            "busy": sum(1 for w in rows if w.get("status") == "busy"),
            "idle": sum(1 for w in rows if w.get("status") != "busy"),
            "busy_leaves": busy_leaves,
        }

    def dashboard(self, *, recent_limit: int = DEFAULT_RECENT_LIMIT) -> dict[str, Any]:
        """七域汇总快照（只读; 空工厂 → 全空域, 永不因数据缺失失败）。"""
        return {
            "projects": self.list_projects(),
            "approvals": self.list_approvals(),
            "agents": self._agent_summaries(),
            "decisions": self._list(self._decisions)[:recent_limit],
            "cost": self._cost_summary(),
            "experience": self._experience_summary(),
            "activity": self._recent_events(recent_limit),
        }
