"""bootstrap.scheduler_pump — 调度驱动器: 反复 tick + 真执行 + 事件回流。

★ 2026-09-19 新增（M3 · 吸收项 1 刀2 · 最后一环）—— 让"平台心脏"真的把活干起来。

【为什么需要它】
  core/scheduler.tick() 只回答"现在该派谁"（判定 → 排序 → 分配 → 创建执行）。
  但**没人反复调它、也没人把创建出来的执行真跑起来** ⇒ 心脏跳一下就不动了。
  本文件就是那个"驱动": 循环 tick, 把 scheduled 的执行并行跑掉, 直到没有就绪叶。

【设计（照 Hermes tools/async_delegation.py 的四要点, 逐条对应）】
  ① 批量占一个槽: 一次 tick 产出的整批 scheduled 作为**一个驱动单元**提交 ——
     批内的并行度单独由 `max_parallel` 约束, 不会因为一次 fan-out 就吃满整个池。
  ② 两级并发: `max_parallel`（批内同时跑几个）× `max_ticks`（最多推进几轮）。
  ③ 池满 → 推迟不阻塞: 超出并发的执行**留在 PENDING**（下次 tick 的
     no_active_execution 判定仍是就绪 ⇒ 自然被下一轮捡起）, 不是丢弃。
  ④ 完成事件: 每批跑完发**一条**汇总事件（不是每个叶一条刷屏）。

【不做什么（诚实边界）】
  · 不重新实现执行 —— 真执行交给 `services/execution` 的 ExecutionRunner.run(execution_id)。
  · 不做抢占（core/scheduler 的 preempt 也还没实现, 一致）。
  · 不做跨进程锁（单 CLI 进程形态, 与 services/work/store.py 的约定一致）。
"""
from __future__ import annotations
import json

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ai_factory_os.core.scheduler.loop import tick
from ai_factory_os.core.scheduler.ports import Ports
from ai_factory_os.services.execution.runtime.store import open_runtime_store


#: ★ 失败重试上限（状态语义, 见 docs/实跑-全链路-20260920.md 卡点 3）：
#: 环境性失败要能重试, 但不能空转 —— 回 pending 计数, 到上限才终止。
_MAX_RETRY = 3


def _run_status(out: Any) -> str:
    """从各种"执行返回形态"里取终态字符串（dict / ExecutionRunOutcome / 普通对象）。

    ★ 2026-09-19（cr-4）：`ExecutionRunOutcome` 把终态放在 `.request.status`
    （它自己没有 `.status`）⇒ 原先 `_looks_completed()` 对它会一律返回 False,
    于是"执行成功了但任务树不知道"。
    """
    if isinstance(out, dict):
        return str(out.get("status") or out.get("state") or "").upper()
    req = getattr(out, "request", None)              # ★ ExecutionRunOutcome 的形态
    st = getattr(req, "status", None) if req is not None else getattr(out, "status", None)
    return str(getattr(st, "value", st) or "").upper()


def _looks_completed(out: Any) -> bool:
    """执行结果是否算"通过"（保守: 明确 COMPLETED/SUCCESS/ok 才算; 拿不准就不算）。"""
    if isinstance(out, dict) and out.get("ok") is True:
        return True
    return _run_status(out) in ("COMPLETED", "SUCCESS", "SUCCEEDED", "OK")


def _cap_batch(batch: list[str], *, limit: int, done: int) -> tuple[list[str], str]:
    """★ 限量：把"本轮要跑的批"掐到剩余额度内（纯函数, 便于守）。

    实测踩到（卡点 6）: 原来只在 tick **前**判 `len(scheduled) >= limit`,
    而一次 tick 可能连开好几个 ⇒ `--limit 1` 却"创建执行 2 个"。
    被截掉的执行已进 store（PENDING）⇒ 下次驱动用 `_pending_leftovers` 捡起来（不丢）。
    返回 (批, 说明; 说明为空表示没截)。
    """
    if not limit:
        return batch, ""
    budget = max(limit - done, 0)
    if budget >= len(batch):
        return batch, ""
    return batch[:budget], (f"★ 限量: 本轮只跑 {budget} 个（其余 {len(batch) - budget} 个留待下次驱动）")


def _verdict_of(out: Any) -> tuple[str, str]:
    """从执行结果里取【裁定】（第 3 项）—— 返回 (verdict, reason)。

    形态兼容: `ExecutionRunOutcome`（终态在 .request.status, 载荷在 .output/.result）或普通 dict。
    取不到 ⇒ ("", "") = **没表态**（调度器按"有没有产出证据"保守复核, 不直接算完成）。
    """
    o: Any = getattr(out, "output", None)
    if o is None:
        o = getattr(out, "result", None)
    if o is None and isinstance(out, dict):
        o = out.get("output") or out
    if isinstance(o, dict):
        return str(o.get("verdict") or ""), str(o.get("verdict_reason") or "")
    return "", ""


def _on_failure(tries: int) -> tuple[str, str]:
    """★ 失败后的状态决策（纯函数, 便于守）—— 返回 (新状态, 说明)。

    · 未到上限 ⇒ 交回 `pending` 重试（环境性失败要能重试）
    · 到上限 ⇒ `cancelled` 终止（防空转: cr-4 那次"归还 pending ⇒ 打满 50 轮/50 个执行"的教训）
    """
    if tries >= _MAX_RETRY:
        return "cancelled", f"重试 {tries} 次仍失败 ⇒ 终止（修环境后重跑）"
    return "pending", f"第 {tries + 1} 次失败 ⇒ 交回重试（环境性失败可重试, 上限 {_MAX_RETRY}）"


def _looks_failed(out: Any) -> bool:
    """★ cr-4: 执行结果是否明确失败（用于**归还被认领的叶**, 见 _claim_and_run）。"""
    return _run_status(out) in ("FAILED", "ERROR", "ERRORED", "CANCELLED")


def sweep_stale_claims(root: Path, ports: Ports) -> list[dict[str, str]]:
    """★ 把【陈旧认领】交回 pending —— `claimed` 但**没有任何活跃执行**指着它的叶。

    为什么必须有它: 进程中断（Ctrl-C / 被 kill / 崩）后叶停在 `claimed`, 而那个"活跃执行"已经没了
    ⇒ 调度器判该叶"已有活跃执行"⇒ 永远 BLOCKED ⇒ **整棵树从此不动**（实测: 一次中断留下 1 个 claimed,
    之后再跑就是"就绪叶为空"）。

    ★★ 安全边界（这条最要紧）: **只动没有活跃执行的叶** —— 有 PENDING/RUNNING 执行的一律不碰,
    绝不抢正在跑的活。读不到执行存储 ⇒ 整轮不扫（不能瞎动）。
    ★ 交回 **不计** retry_count（它不是失败, 别吃重试额度）。
    """
    from ai_factory_os.services.work import decomposition as D

    plan_id = str(getattr(ports.work, "_plan_id", "") or "")
    project_id = str(getattr(ports.work, "_project_id", "") or "")
    active: set[str] = set()
    try:
        for req in open_runtime_store(root).list_executions():
            st = str(getattr(req.status, "value", req.status) or "").upper()
            node = str((req.input or {}).get("node_id") or "")
            if node and st in ("PENDING", "RUNNING"):
                active.add(node)
    except Exception:  # noqa: BLE001 — 读不到执行存储 ⇒ 不扫（不能瞎动数据）
        return []

    out: list[dict[str, str]] = []
    try:
        metas = D.list_trees(root)
    except Exception:  # noqa: BLE001
        return []
    for meta in metas:
        pid = str(meta.get("plan_id") or "")
        if plan_id and pid != plan_id:
            continue
        tree = D.load_tree(root, pid)
        if not tree:
            continue
        pj = str(tree.get("project_id") or project_id or "")
        for n in tree.get("nodes") or []:
            nid = str(n.get("id") or "")
            if str(n.get("status") or "") != "claimed" or not nid or nid in active:
                continue
            if D.release_leaf(root, pid, nid, status="pending", project_id=pj,
                              note="陈旧认领（无活跃执行, 进程中断遗留）⇒ 交回, 不计重试",
                              count_retry=False):
                out.append({"plan_id": pid, "node_id": nid,
                            "title": str(n.get("title") or "")[:50]})
    return out


def _mark_needs_decision(ports: Ports, execution_id: str, verdict: str, reason: str) -> None:
    """把"执行体停手待裁决"写进叶（第 3 项）—— 失败安全（写不上不影响执行结果）。"""
    try:
        from ai_factory_os.services.work import decomposition as D

        root = Path(getattr(ports.work, "_root", "."))
        store = open_runtime_store(root)
        for req in store.list_executions():
            if str(req.id) != execution_id:
                continue
            inp = req.input or {}
            D.mark_needs_decision(root, str(req.task_id or ""),
                                 str(inp.get("node_id") or ""), verdict=verdict,
                                 reason=reason,
                                 project_id=str(getattr(req, "project_id", "") or ""))
            return
    except Exception:  # noqa: BLE001
        return


def _record_memory(ports: Ports, execution_id: str, *, kind: str, text: str,
                   authority: str = "agent_claim") -> None:
    """★ 把一次执行的【经验】写进项目级记忆（全量测试查出的"写侧零调用者" ⇒ 这里接线）。

    为什么接在调度器: 执行完成/停手是**真实事件**, 而原来唯一的写入者
    （`services/execution/external/gateway.py`）没有任何调用者 ⇒ 项目记忆至今零数据,
    "跨会话记忆"这个机制实际没生效。
    · 落盘失败 ⇒ 显式告警到 stderr（`add()` 现在返回 bool; 禁静默丢）
    """
    try:
        from ai_factory_os.services.conversation.project_memory import MemoryStore

        root = Path(getattr(ports.work, "_root", "."))
        node_id = plan_id = project_id = ""
        for req in open_runtime_store(root).list_executions():
            if str(req.id) == execution_id:
                node_id = str((req.input or {}).get("node_id") or "")
                plan_id = str(req.task_id or "")
                project_id = str(getattr(req, "project_id", "") or "")
                break
        if not project_id and plan_id:
            from ai_factory_os.services.work import decomposition as D
            _t = D.load_tree(root, plan_id)
            project_id = str((_t or {}).get("project_id") or "")
        if not project_id:
            return                                   # 无项目 ⇒ 项目级记忆无处可放（不编）
        ms = MemoryStore.load(root, project_id)
        if not ms.add(f"[{node_id[-10:]}] {text}", source=f"exec:{execution_id}",
                      kind=kind, authority=authority):
            import sys as _sys
            print(f"⚠ 项目记忆落盘失败（这次经验没记住）: {text[:60]}", file=_sys.stderr)
    except Exception:  # noqa: BLE001 — 记忆写失败不阻塞执行结果
        return


def _repo_state(repo: str, *, window_sec: float = 1800) -> str:
    """项目仓库的【收尾状态】⇒ "committed" / "uncommitted" / "none" / "unknown"。

    判据（可解释）:
      · 不是 git 仓库 / git 不可用 / 路径不存在 ⇒ "unknown"（判不出, 不猜）
      · `git status --porcelain` 非空 ⇒ **"uncommitted"**（有产出但没收尾: 工作区脏）
      · 否则: 最近一次提交落在 `window_sec` 内 ⇒ "committed"; 更早 ⇒ "none"

    ★ 2026-09-21（卡点4 实测）: 原来只有 True/False/None 三态 ⇒ **分不清"提交了"和"留了脏工作区"**。
      实测两份场景: EXR-002/003 的执行体自提交（干净）;  EXR-004 超时、EXR-005 收工都**没提交**
      （场景仓库 6 / 18 个未提交文件, main 分支 0 提交）⇒ 叶却被记成干净完成。
      ⇒ 未提交也是"有产出", 但要**标明"待核"**（下一个人/下一个叶会踩到这份脏工作区）。
    """
    p = Path(repo) if repo else None
    if not p or not p.is_dir():
        return "unknown"
    try:
        import subprocess

        def _git(*args: str) -> str:
            r = subprocess.run(["git", "-C", str(p), *args], capture_output=True,
                               text=True, timeout=20)
            return r.stdout.strip() if r.returncode == 0 else ""

        if not _git("rev-parse", "--is-inside-work-tree"):
            return "unknown"
        if _git("status", "--porcelain"):
            return "uncommitted"
        ts = _git("log", "-1", "--format=%ct")
        if not ts:
            return "none"                       # 仓库在、但一次都没提交过
        import time
        return "committed" if (time.time() - float(ts)) <= window_sec else "none"
    except Exception:  # noqa: BLE001 — 判不出 ⇒ unknown（调用方标待核）
        return "unknown"


def _repo_changed(repo: str, *, window_sec: int = 1800) -> bool | None:
    """项目仓库有没有【产出迹象】⇒ True/False; 判不出来 ⇒ None（调用方标"待核"）。

    薄包装（保留旧签名, 语义不变）; 细分的四态见 `_repo_state`。
    """
    st = _repo_state(repo, window_sec=window_sec)
    if st == "unknown":
        return None
    return st in ("committed", "uncommitted")


def _mark_evidence(ports: Ports, execution_id: str) -> str:
    """★ 记【产出证据】（完成时附加信息）—— 返回证据串（repo-changed / no-change / unknown）。

    实测: 执行体"核验 + 停手、零改动"照样被记成 `completed` ⇒ 进度 1/199 是**假的**。
    这里只做**标记**, 不动状态（改状态会牵动调度器终态集合, 风险大; 且验证类任务本来就无改动）:
      · 项目仓库有改动/新提交 ⇒ `evidence="repo-changed"`（有据）
      · 没有任何改动 ⇒ `evidence="no-change"` + `verify_needed=True`（**待核**）
        —— 可能是"验证类任务"（合理）, 也可能是"执行体停手"（不合理）; 两种都该被人看一眼,
        不能混进"真做完了"。进度里会把 `verify_needed` 的条数单独报出来。
    失败安全: 任何一步拿不到 ⇒ 静默返回（标记是附加信息, 不能拖垮执行）。
    """
    try:
        import json as _json

        from ai_factory_os.services.work import decomposition as D

        root = Path(getattr(ports.work, "_root", "."))
        node_id = ""
        plan_id = ""
        project_id = ""
        store = open_runtime_store(root)
        for req in store.list_executions():
            if str(req.id) == execution_id:
                inp = req.input or {}
                node_id = str(inp.get("node_id") or "")
                plan_id = str(req.task_id or "")
                project_id = str(getattr(req, "project_id", "") or "")
                break
        if not (node_id and plan_id):
            return "unknown"
        # ★ 执行请求里没有 project_id（契约只有 task_id/input）⇒ 从树上取
        #   （真跑踩到: 没有它 ⇒ 找不到仓库 ⇒ evidence=unknown, 白标一条"待核"）
        if not project_id:
            _t = D.load_tree(root, plan_id)
            if _t:
                project_id = str(_t.get("project_id") or "")
        # 项目仓库路径（org/projects.json 里 adopt 时写的 repo_path）
        repo = ""
        pj = root / "org" / "projects.json"
        if pj.is_file() and project_id:
            try:
                data = _json.loads(pj.read_text(encoding="utf-8"))
                rows = data.get("projects") if isinstance(data, dict) else data
                if isinstance(rows, dict):
                    repo = str((rows.get(project_id) or {}).get("repo_path") or "")
                elif isinstance(rows, list):
                    repo = next((str(r.get("repo_path") or "") for r in rows
                                 if isinstance(r, dict) and str(r.get("id")) == project_id), "")
            except Exception:  # noqa: BLE001
                repo = ""
        changed = _repo_state(repo)           # ★ 四态: committed/uncommitted/none/unknown（卡点4）
        tree = D.load_tree(root, plan_id, project_id)
        if not tree:
            return "unknown"
        for n in tree.get("nodes") or []:
            if str(n.get("id") or "") != node_id:
                continue
            if changed == "committed":
                ev, need = "repo-changed", False
            elif changed == "uncommitted":
                # ★ 有产出但没收尾（工作区脏）: 记产出 + 标"待核"（下一个人/下一个叶会踩到）
                ev, need = "repo-uncommitted", True
            elif changed == "none":
                ev, need = "no-change", True
            else:
                ev, need = "unknown", True
            D.set_node_evidence(root, plan_id, node_id, evidence=ev,
                                verify_needed=need, project_id=project_id)
            if changed == "uncommitted" and hasattr(D, "release_leaf"):
                # 把"产出未提交"写进叶的状态说明（人一眼看到为什么待核）
                try:
                    D.set_node_note(root, plan_id, node_id, project_id=project_id,
                                    note="产出未提交（工作区有未提交文件）⇒ 待核")
                except Exception:  # noqa: BLE001 — 说明写不上不影响证据
                    pass
            return ev
    except Exception:  # noqa: BLE001 — 标记失败不影响执行结果
        return "unknown"
    return "unknown"


def _write_back_node_status(ports: Ports, execution_id: str, status: str) -> bool:
    """执行完成 → 把对应叶的状态回写进任务树（闭环保闭环的最后一环）。

    链路: execution_id → RuntimeStore 里该请求的 input.node_id → 任务树里那个叶 → 改 status。
    失败安全: 任何一步拿不到 ⇒ 返回 False（调用方记录, 不抛）。
    """
    try:
        from ai_factory_os.services.work import decomposition as D

        root = Path(getattr(ports.work, "_root", "."))
        task_id = ""
        node_id = ""
        store = open_runtime_store(root)
        for req in store.list_executions():
            if str(req.id) == execution_id:
                inp = req.input or {}
                node_id = str(inp.get("node_id") or "")
                task_id = str(req.task_id or "")
                break
        if not node_id:
            return False
        tree = D.load_tree(root, task_id) if task_id else None
        if not tree:
            return False
        hit = False
        for n in tree.get("nodes") or []:
            if str(n.get("id") or "") == node_id:
                n["status"] = status
                # ★ 完成即归还: 清掉认领痕迹（否则树里永远挂着 claimed_by, 看着像还在跑）
                n.pop("claimed_by", None)
                n.pop("claimed_at", None)
                hit = True
                break
        if hit:
            plan_id = str(tree.get("plan_id") or task_id or "")
            if plan_id:
                D._save(root, plan_id, tree, str(tree.get("project_id") or ""))  # noqa: SLF001
                return True
    except Exception:  # noqa: BLE001 — 回写失败不影响驱动
        return False
    return False


def _conflicting_nodes(root: Path) -> set[str]:
    """★ cr-5: 找出"同层写同一文件"的冲突节点（**这些节点不能同时跑**）。

    依据 `decomposition.file_conflicts()` 自述:
      "两个同层任务若 expected_files 有交集, 并行执行必然互相覆盖
       ⇒ 执行器需按此把冲突任务**降级为串行**（或报给用户裁决）"
    为什么必须在此调用: 该函数此前**零调用者** ⇒ 并行批里两个写同一文件的任务
    会**静默互相覆盖**（丢改动, 且不报错）。

    返回: 需要串行的 node_id 集合（冲突组内**除第一个外**的全部节点）。
    """
    from ai_factory_os.services.work import decomposition as D

    serial: set[str] = set()
    try:
        for f in sorted((Path(root) / "task_trees").glob("*.json")):
            try:
                tree = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for c in D.file_conflicts(tree) or []:
                ids = [str(x) for x in (c.get("ids") or [])]
                serial.update(ids[1:])          # 冲突组只留第一个可并行, 其余串行
    except Exception:  # noqa: BLE001 — 检测不可用 ⇒ 不退化为"全都并行"（安全优先）
        return set()
    return serial


def _split_by_conflict(root: Path, batch: list[str],
                       exec_to_node: dict[str, str]) -> tuple[list[str], list[str]]:
    """把批内【会写同一文件】的执行拆出来串行 → (可并行批, 需串行批)。"""
    serial_nodes = _conflicting_nodes(root)
    if not serial_nodes:
        return batch, []
    par: list[str] = []
    ser: list[str] = []
    for eid in batch:
        (ser if exec_to_node.get(eid, "") in serial_nodes else par).append(eid)
    return par, ser


def _exec_node_map(root: Path, batch: list[str]) -> dict[str, str]:
    """execution_id → node_id（用于冲突判定）。"""
    out: dict[str, str] = {}
    try:
        store = open_runtime_store(root)
        want = set(batch)
        for req in store.list_executions():
            if str(req.id) in want:
                out[str(req.id)] = str((req.input or {}).get("node_id") or "")
    except Exception:  # noqa: BLE001 — 拿不到 ⇒ 空表（调用方按"无冲突"处理）
        return {}
    return out


def _void_execution(root: Path, execution_id: str) -> None:
    """把一个执行**作废**（标 FAILED, 落盘）—— 用于 CAS 认领失败等"本次执行不该继续"。

    ★ 为什么必须落盘（实测）: 只返回 SKIPPED 不改存储 ⇒ 它仍是 PENDING ⇒
    `_pending_leftovers` 下一轮又捡起 ⇒ 再认领失败 ⇒ 死循环（打满 max_ticks）。
    ★ 用 FAILED 而非新增状态: `ExecutionStatus` 只有 PENDING/RUNNING/SUCCESS/FAILED
    （作废语义 = "这次没成功", 且它**失败后不再被捡**, 正是所需）。
    """
    try:
        from ai_factory_os.services.execution.runtime.types import ExecutionStatus

        store = open_runtime_store(root)
        req = store.get_execution(execution_id)
        if req is not None:
            req.status = ExecutionStatus.FAILED
            store.save_execution(req)
    except Exception:  # noqa: BLE001 — 作废失败不该炸掉驱动
        pass


def _claim_and_run(ports: Ports, execution_id: str, run_execution: Callable[[str], Any]) -> Any:
    """★ CAS 认领 → 执行 → 归还（吸收自 amux: "两个 agent 永不会拿同一张卡"）。

    为什么要在执行前认领:
        调度器判定 READY 之后、真正开跑之前有时间窗 —— 若另一轮 tick / 另一个驱动
        同时看见同一个叶, 单靠"判定时是 pending"防不住双领。
        CAS 把它变成: 只有把 pending 改成 claimed 的那一方能继续 ⇒ **恰好一个赢**。

    失败回滚: 认领成功但执行抛异常 ⇒ 交回 pending（供重认）, 不把叶永久占死。
    """
    from ai_factory_os.services.work import decomposition as D
    from ai_factory_os.services.execution.runtime.store import open_runtime_store

    root = Path(getattr(ports.work, "_root", "."))
    # ★ 2026-09-19（实测修正）: claim/release 也必须带 project_id ——
    #   否则 `decomposition._read` 会走"全局优先"读到 `task_trees/` 那份**影子树**
    #   （实测: 我重置了项目内那棵, claim 却说 "status=claimed" —— 因为动的是另一份）。
    #   与 cmd_run_plan 取 project_id 是同一个修法（读写必须锁定同一份）。
    project_id = str(getattr(ports.work, "_project_id", "") or "")
    node_id, task_id, who = "", "", ""
    try:
        store = open_runtime_store(root)
        for req in store.list_executions():
            if str(req.id) == execution_id:
                inp = req.input or {}
                node_id = str(inp.get("node_id") or "")
                task_id = str(req.task_id or "")
                # ★ 认领要记**真实成员名**（不是执行 id）—— 否则舰队视图里看到的
                #   全是 "exec:EXR-00x", 回答不了"谁在干什么"（实测暴露过）。
                who = str(inp.get("member_id") or req.agent_id or "")
                break
    except Exception:  # noqa: BLE001 — 拿不到就退化为"直接跑"（老行为）
        return run_execution(execution_id)

    if node_id and task_id:
        got = D.claim_leaf(root, task_id, node_id, member_id=who or f"exec:{execution_id}",
                           project_id=project_id)
        if not got.get("ok"):
            # 已被别人领 ⇒ 本执行作废（不跑）—— 这正是 CAS 的意义
            # ★ 2026-09-19（实测修正）: 作废必须【落盘成终态】+【不动叶】——
            #   否则该执行仍是 PENDING ⇒ 下一轮又被 _pending_leftovers 捡起 ⇒
            #   再认领失败 ⇒ SKIPPED ⇒ 再捡 …… **打满 max_ticks 空转**
            #   （实测: 同一棵 13 叶的树创建 52 个执行、打满 50 轮）。
            _void_execution(root, execution_id)
            return {"status": "SKIPPED", "reason": f"CAS 认领失败: {got.get('reason')}"}
    try:
        result = run_execution(execution_id)
    except Exception:
        if node_id and task_id:
            D.release_leaf(root, task_id, node_id, status="pending",
                           project_id=project_id)   # 回滚, 供重认
        raise
    # ★ 状态语义（全链路实跑踩到, 卡点 3）: 环境性失败**要能重试**, 但**不能空转** —— 两种病都踩过:
    #   · 一律回 pending ⇒ 失败又被调度 ⇒ 打满 max_ticks + 每轮新建执行（cr-4 实测: 13 叶创建 50 个执行）
    #   · 一律 cancelled ⇒ 缺个 runtime / provider 抖一下, 任务就**永久终止、不可重试**
    #   正解: 回 pending + `retry_count` 计数, 到上限才终止（并写明原因, 让人修完环境能重跑）。
    if node_id and task_id and _looks_failed(result):
        _leaf = D.get_leaf(root, task_id, node_id, project_id=project_id) or {}
        _tries = int(_leaf.get("retry_count") or 0)
        _st, _note = _on_failure(_tries)
        if _st == "cancelled":
            # ★ 终止（重试到上限）也是最该记住的经验（下次别再撞同一面墙）
            _record_memory(ports, execution_id, kind="error",
                           text=f"重试 {_tries} 次仍失败 ⇒ 终止: {_note[:140]}",
                           authority="repo_evidence")
        D.release_leaf(root, task_id, node_id, status=_st, project_id=project_id, note=_note)
    return result


@dataclass
class PumpReport:
    """一次驱动的汇总（给 CLI / 事件用）。"""

    ticks: int = 0
    scheduled: list[str] = field(default_factory=list)     # 本驱动创建的执行 id
    outcomes: list[dict[str, Any]] = field(default_factory=list)  # 每个执行的终态摘要
    deferred: list[str] = field(default_factory=list)      # 被容量/预算推迟的叶
    released: list[dict[str, str]] = field(default_factory=list)  # ★ 交回的陈旧认领（进程中断遗留）
    paused: list[str] = field(default_factory=list)        # ★ 被 steering 指令暂停的叶（吸收项 7）
    stopped_because: str = ""                              # 停止原因（可解释）


def _pending_leftovers(root: Path, ports: Ports) -> list[str]:
    """★ 捡起【遗留 PENDING 执行】—— 上一轮中断留下的（已在 RuntimeStore 但没跑完）。

    为什么必须捡: tick 看到该叶"已有活跃执行"（PENDING）⇒ 判 BLOCKED（防重复是对的）,
    但若不把存量 PENDING 跑掉, 它就**永远挂着** —— 表现为整棵树卡住不动。

    只捡**本任务树**的（按 `task_id == plan_id` 过滤）—— 不干扰别的工作。

    ★ 防死循环（实测踩过）: cr-4 会把"执行返回 FAILED"的叶**归还为 pending**,
    若失败是**环境性**的（如 `NoAvailableRuntimeError` —— runtime 未注册）,
    下一轮又会捡起同一个 PENDING ⇒ 失败 ⇒ 归还 ⇒ 再捡 …… **打满 max_ticks 空转**
    （实测: 13 叶的树创建了 51 个执行、同一 id 重试 50 轮）。
    ⇒ 规则: **同一叶已有 FAILED 执行（且无 SUCCESS）时不再捡** —— 交给人工/上层处置,
      不空转（这也符合"失败要显式, 不静默重试"）。
    """
    plan_id = str(getattr(ports.work, "_plan_id", "") or "")
    pending: list[tuple[str, str]] = []       # (execution_id, node_id)
    by_node: dict[str, set[str]] = {}          # node_id → 见过的状态集合
    try:
        for req in open_runtime_store(root).list_executions():
            st = str(getattr(req.status, "value", req.status) or "").upper()
            node = str((req.input or {}).get("node_id") or "")
            if node:
                by_node.setdefault(node, set()).add(st)
            if st == "PENDING" and (not plan_id or str(req.task_id or "") == plan_id):
                pending.append((str(req.id), node))
    except Exception:  # noqa: BLE001 — 读不到 ⇒ 不捡（保持原行为）
        return []
    out: list[str] = []
    for eid, node in sorted(pending):
        seen = by_node.get(node, set())
        # ★ 该叶失败过且从未成功 ⇒ 不重试（防环境性失败空转）
        if "FAILED" in seen and not (seen & {"SUCCESS", "COMPLETED"}):
            continue
        out.append(eid)
    return out


def drive(
    ports: Ports,
    *,
    run_execution: Callable[[str], Any],
    max_parallel: int = 3,
    max_ticks: int = 50,
    limit: int = 0,
    on_batch_done: Callable[[PumpReport], None] | None = None,
) -> PumpReport:
    """反复 tick 并**并行**跑掉被调度的执行, 直到没有就绪叶（或触顶）。

    `run_execution`: 执行一个 execution_id（真实实现 = ExecutionRunner.run）。
    `max_parallel`: 批内并发上限（第一级）。
    `max_ticks`: 最多推进几轮（第二级 · 防死循环）。
    `limit`: ★ 本次【最多跑几个执行】(0=不限) —— 第三级, 给"小步试跑"用:
      一棵 199 叶的树不加限量会一路跑到没就绪叶为止（真实 agent + LLM 成本）,
      想先验一个/一批就得能掐住。
    `on_batch_done`: 每批完成回调（事件回流用）。

    返回 PumpReport（ticks/scheduled/outcomes/deferred/stopped_because）——
    每一条都可解释: 为什么停、跑了哪些、推迟了哪些。
    """
    rep = PumpReport()
    root = Path(getattr(ports.work, "_root", "."))
    # ★ 起手先交回【陈旧认领】（进程中断遗留的 claimed）—— 否则它们永远 BLOCKED, 整棵树不动
    rep.released = sweep_stale_claims(root, ports)

    for _ in range(max_ticks):
        # ★ 限量: 已经跑够就停（停在【执行之间】, 不打断正在跑的那批）
        if limit and len(rep.scheduled) >= limit:
            rep.stopped_because = f"达到本次上限（limit={limit} 个执行）"
            break
        # ★ 吸收项 7（Steering）: 每轮 tick 前检查改向指令 —— 这是"运行中改向"的注入点。
        #   只影响**未派发的**（已完成的叶不动 —— 改向不该回滚已完成的工作）。
        try:
            from ai_factory_os.services.work import steering as _steer

            eff = _steer.effective(root)
            if eff.get("stop"):
                rep.stopped_because = "被 steering 指令停止（stop）"
                break
            if eff.get("paused"):
                rep.paused = sorted(eff["paused"])
        except Exception:  # noqa: BLE001 — 无 steering 能力 ⇒ 老行为
            eff = {}
        try:
            result = tick(ports)
        except NotImplementedError:
            # ExecutionPort.create 未实现（刀1 的 NullExecution）⇒ 无法推进
            rep.stopped_because = "ExecutionPort.create 未装配（无法创建执行）"
            return rep
        rep.ticks += 1
        rep.deferred.extend(result.deferred)

        if not result.scheduled:
            # ★ 本轮没新调度 —— 但先看有没有**遗留 PENDING**（上一轮中断留下的）:
            #   有则继续跑（否则它们永远挂着 ⇒ 整棵树卡住）。
            _left = _pending_leftovers(root, ports)
            if not _left:
                # 没有可推进的执行: 要么全完成, 要么全被卡（依赖/能力/容量）
                ready = [d for d in result.decisions if str(d.kind.value) == "ready"]
                if not ready:
                    kinds = {str(d.kind.value) for d in result.decisions}
                    rep.stopped_because = (
                        "无可推进执行（就绪叶为空）: " + ", ".join(sorted(kinds))
                    )
                else:
                    rep.stopped_because = "有就绪叶但未创建执行（容量/预算受限）"
                break

        # ★ ① 整批作为"一个驱动单元"; ② 批内并发受 max_parallel 约束
        #   ★ 并入遗留 PENDING: 同一批一起跑（中断后续跑的入口）
        # ★★ 2026-09-20 修: 限量必须在【建批时就掐住】—— 原来只在 tick 前判,
        #   而一次 tick 可能连开好几个（实测: `--limit 1` 却"创建执行 2 个"）。
        #   被截掉的执行已进 store（PENDING）⇒ 下一次驱动会用 `_pending_leftovers` 捡起来（不丢）。
        batch = list(result.scheduled) + _pending_leftovers(root, ports)
        batch, _cap_note = _cap_batch(batch, limit=limit, done=len(rep.scheduled))
        if _cap_note:
            rep.outcomes.append({"execution_id": "", "ok": True, "state": _cap_note})
        rep.scheduled.extend(batch)
        # ★ cr-5: 批内文件冲突检测 —— 同层写同一文件的执行**不能并行**（否则静默互相覆盖）。
        #   decomposition.file_conflicts() 自述要求"执行器降级为串行", 此前零调用者。
        _emap = _exec_node_map(root, batch)
        _par, _ser = _split_by_conflict(root, batch, _emap)
        if _ser:
            rep.outcomes.append({"execution_id": ",".join(_ser), "ok": True,
                                 "state": f"★ 文件冲突 ⇒ 降级串行（{len(_ser)} 个）"})
        batch = _par
        with ThreadPoolExecutor(max_workers=max(1, int(max_parallel))) as pool:
            futures = {pool.submit(_claim_and_run, ports, eid, run_execution): eid
                       for eid in batch}
            for fut in as_completed(futures):
                eid = futures[fut]
                try:
                    out = fut.result()
                    rep.outcomes.append({"execution_id": eid, "ok": True,
                                         "state": getattr(out, "status", None) or str(out)[:80]})
                    # ★ 2026-09-19 补（闭环最后一环）: 执行成功 → **回写任务树的叶状态**。
                    #   契约自述: "完成的判据不是跑完了, 而是有 accepted Outcome" ——
                    #   不回写的话, 依赖它的下游叶永远 blocked（实测: 3 叶跑完后第 4 叶仍卡）。
                    #   判据: 执行结果视为通过（COMPLETED/True）⇒ 叶 status = "completed"
                    #   （has_accepted_outcome 认 completed/accepted/done）。
                    # ★ 第 3 项: 执行体显式【停手待裁决】⇒ 叶终止 + 留原因, **绝不记成完成**
                    _v, _why = _verdict_of(out)
                    if _v in ("needs_decision", "blocked"):
                        if _write_back_node_status(ports, eid, "cancelled"):
                            _mark_needs_decision(ports, eid, _v, _why)
                            # ★ 停手也是【该记住的经验】（第 3 项 + 记忆接线）
                            _record_memory(ports, eid, kind="decision",
                                           text=f"执行体停手待裁决（{_v}）: {_why[:160]}",
                                           authority="agent_claim")
                            inv = getattr(ports.work, "invalidate", None)
                            if callable(inv):
                                inv()
                        rep.outcomes.append({"execution_id": eid, "ok": False,
                                             "state": f"停手待裁决({_v}): {_why[:70]}"})
                        continue
                    if _looks_completed(out):
                        if _write_back_node_status(ports, eid, "completed"):
                            # ★ 完成必须留产出证据（实跑踩到: 停手零改动也被记成 completed）
                            _ev = _mark_evidence(ports, eid)
                            # ★ 完成的经验进项目记忆（含裁定与产出证据 —— 跨会话可复用）
                            _record_memory(ports, eid, kind="learning",
                                           text=f"任务完成（裁定={_v or '未表态'}, 产出证据={_ev}）"
                                                + (f" · {_why[:120]}" if _why else ""),
                                           authority="repo_evidence")
                            # ★ 回写后必须让适配器的树缓存失效 —— 否则本轮 tick 仍读旧树,
                            #   下游叶看不到"前驱已验收"（实测踩过）。
                            inv = getattr(ports.work, "invalidate", None)
                            if callable(inv):
                                inv()
                except Exception as exc:  # noqa: BLE001 — 单叶失败不终止整批
                    rep.outcomes.append({"execution_id": eid, "ok": False,
                                         "state": f"{type(exc).__name__}: {exc}"})
        # ★ ④ 每批一条完成事件（不刷屏）
        if on_batch_done is not None:
            try:
                on_batch_done(rep)
            except Exception:  # noqa: BLE001 — 事件失败不影响驱动
                pass
    else:
        rep.stopped_because = f"达到 max_ticks={max_ticks} 上限"

    return rep


def make_real_execution_port(root: Path | str, *, task_id: str, work: Any = None,
                             logger: Any = None) -> Any:
    """构造**真实**的 ExecutionPort（create 会落库一条 PENDING 执行请求）。

    与刀1 的 NullExecution 相对: 这是"能真创建执行"的适配器。
    `task_id` = 执行请求归属的任务（刀2 用任务树的 plan_id）。
    """

    class _RealExecution:
        def active_for(self, node_id: str) -> Any:
            """★ 幂等的关键（core/scheduler/evaluate 的 no_active_execution 条件）:
            该 node 是否已有**未完成**的执行（PENDING/RUNNING）——
            有 ⇒ 调度器 BLOCKED, 不重复创建（否则每轮 tick 都会再建一个, 实测过:
            10 tick 建了 30 个执行 ⇒ 同一批叶被反复跑）。
            失败安全: 读不到/坏数据 ⇒ 当作"无活跃"（退化为老行为, 不假阻塞）。
            """
    
            try:
                # ★ claimed 的叶也算"活跃"（CAS 已把它锁给人了）——
                #   否则每轮 tick 又判 READY ⇒ 重复创建执行（CAS 虽会拒, 但执行请求已白建）。
                tree = getattr(work, "_tree", None)
                if callable(tree):
                    for n in (tree().get("nodes") or []):
                        if (str(n.get("id") or "") == node_id
                                and str(n.get("status") or "").lower() == "claimed"):
                            from ai_factory_os.contracts.execution import Execution as _Exec

                            return _Exec(id=str(n.get("claimed_by") or "claimed"),
                                         task_node_id=node_id, member_id="", status="running")
                store = open_runtime_store(root)
                for req in store.list_executions(task_id=task_id):
                    if str((req.input or {}).get("node_id") or "") != node_id:
                        continue
                    if str(getattr(req.status, "value", req.status)) in ("PENDING", "RUNNING"):
                        from ai_factory_os.contracts.execution import Execution as _Exec

                        return _Exec(id=req.id, task_node_id=node_id, member_id="",
                                     status=str(getattr(req.status, "value", req.status)).lower())
            except Exception:  # noqa: BLE001 — 失败安全: 不因存储问题假阻塞
                pass
            return None

        def create(self, node_id: str, *, resolution_id: str,
                   member_id: str, identity_id: str) -> Any:
            from ai_factory_os.contracts.execution import Execution as _Exec
            from ai_factory_os.services.execution.runtime.store import open_runtime_store
            from ai_factory_os.services.execution.runtime.types import ExecutionRequest

            store = open_runtime_store(root)
            eid = store.next_execution_id(prefix="EXR-")
            req = ExecutionRequest(
                id=eid, task_id=task_id,
                agent_id=member_id or None,
                input={"node_id": node_id, "resolution_id": resolution_id,
                       "member_id": member_id, "identity_id": identity_id},
            )
            store.save_execution(req)
            return _Exec(id=eid, task_node_id=node_id, resolution_id=resolution_id,
                         member_id=member_id, actor_identity_id=identity_id,
                         status="queued")

    return _RealExecution()
