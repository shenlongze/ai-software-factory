"""按 DAG 层并行执行（刀4 ✓ 2026-09-14）。

设计原则（为什么【加法】而不是改内核 ✗）:
  既有 execute_production_run 是【串行内核】✓ 已被 Golden Path 与端到端依赖 ✓
  → 动它 = 动主链 ✗（本会话已多次栽在"改主链不留退路"✗）
  → 本模块【新增】一条按层并行的路径 ✓ 复用既有【单节点内核】
    （create_node_run + execute_node_run ✓）不复制逻辑 ✓
  判据: 任何既有调用方不传 parallel 参数 → 行为与今天【逐字节相同】✓

正确性依据（前三刀的地基 ✓）:
  · 刀1: 层级由 DAG 算出 ✓（同层可并行 ✓ 层间串行 ✓）→ 不会读到未写完的上游产物 ✓
  · 刀2: 每节点独立工作区 ✓ + 完成合并（冲突可见 ✓ 不静默覆盖 ✗）
  · 刀3: NodeRun 记录原子写 ✓（240 次并发 0 半截 ✓）
  · 事件流 SQLite WAL ✓（既有 ✓）

失败语义（与串行内核保持一致 ✓ 不许变 ✗）:
  · 某节点 FAILED → 其【同层】其它节点照常跑完 ✓（它们不依赖它 ✓）
  · 其【下游】→ BLOCKED（依赖未成功 ✓ 不是跳过 ✓ 不是假装 ✓）
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

#: 并发上限默认 2（方案 §5 诚实边界 ✓: 同机多个 codex 会争资源 ✓）
#: 可用环境变量 FACTORY_PARALLEL 覆盖 ✓
DEFAULT_MAX_WORKERS = 2


def resolve_max_workers(explicit: int | None = None) -> int:
    """并发上限: 显式 > 环境变量 > 默认 2 ✓（永远 >= 1 ✓）。"""
    if explicit is not None:
        return max(1, int(explicit))
    try:
        return max(1, int(os.environ.get("FACTORY_PARALLEL", "") or DEFAULT_MAX_WORKERS))
    except ValueError:
        return DEFAULT_MAX_WORKERS


def topological_layers(nodes: list[dict[str, Any]]) -> list[list[str]]:
    """按 depends_on 分层 ✓（防环 ✓ 不阻塞 ✓）。

    与 task_decomposition.compute_parallel_groups 同一语义 ✓
    （那边算【树】的层 ✓ 这边算【运行】的层 ✓ 名字不同因为输入形状不同 ✓）
    """
    ids = [str(n.get("node_id") or "") for n in nodes if isinstance(n, dict)]
    idset = set(ids)
    deps: dict[str, set[str]] = {}
    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid = str(n.get("node_id") or "")
        deps[nid] = {str(d) for d in (n.get("depends_on") or []) if str(d) in idset and str(d) != nid}
    layers: list[list[str]] = []
    remaining = dict(deps)
    done: set[str] = set()
    while remaining:
        layer = sorted(n for n, d in remaining.items() if d <= done)
        if not layer:                                  # 环 → 剩余整体一层 ✓
            layer = sorted(remaining)
        layers.append(layer)
        done |= set(layer)
        for n in layer:
            remaining.pop(n, None)
    return layers


def run_layers(
    nodes: list[dict[str, Any]],
    run_one: Callable[[str], Any],
    *,
    max_workers: int | None = None,
    on_done: Callable[[str, Any], None] | None = None,
) -> list[tuple[str, Any]]:
    """按层执行 ✓: 层内并行（上限 max_workers ✓）· 层间串行 ✓。

    参数:
      run_one(node_id) → 结果（通常返回该节点的 state ✓）
      on_done(node_id, result) → 每完成一个回调 ✓（调用方在此更新 run 记录 ✓）
    返回: [(node_id, result), ...]（与输入顺序无关 ✓ 调用方按 node_id 索引 ✓）

    ★ 层间串行【不可省 ✗】: 同层的依赖已满足 ✓ 下一层要等同层全部落定 ✓
      （否则下游可能读到同层还没写完的产物 ✓ = 随机失败 ✓）
    """
    w = resolve_max_workers(max_workers)
    out: list[tuple[str, Any]] = []
    for layer in topological_layers(nodes):
        with ThreadPoolExecutor(max_workers=w, thread_name_prefix="node") as ex:
            futs = {ex.submit(run_one, nid): nid for nid in layer}
            for fut in futs:
                nid = futs[fut]
                try:
                    res = fut.result()
                except BaseException as exc:  # noqa: BLE001 — 单节点异常不拖垮同层 ✓
                    res = exc
                out.append((nid, res))
                if on_done is not None:
                    on_done(nid, res)
    return out
