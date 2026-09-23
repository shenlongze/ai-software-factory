"""services.execution.production_run — ProductionRun 的**只读**访问（收缩后）。

★ 2026-09-19 收缩（P0 第二项）—— 原文件 586 行是 `src/ai_factory_os/services/execution/production_run.py`
  整块搬过来的：Workflow 定义 + ProductionRun 状态机 + 串行 DAG + Artifact binding +
  executor factory + 执行器。逐符号核实（模块名 import / 导出符号 / 字符串引用 + 排除同名异物）后：

    真活（2 处真 import）:
      get_production_run  ← services/operations/rollback_service.py:26
                          ← services/execution/production_evaluation.py:23
    真死（0 引用, 已删）:
      create_production_run · list_production_runs · execute_production_run ·
      build_executor_factory · ProductionRunError · PRUN_STATES/PRUN_TRANSITIONS 状态机 ·
      register_workflow / get_workflow（★ 注意: capabilities.py 有**自己的**同名方法, 是异物）·
      _extract_code / _to_patch / _wf_path · 以及 2026-09-19 我为 M3 加的 _iter_by_wave

  ⇒ 结论: 这个文件的"执行面"从来没有消费者（它是老区 S3 的遗留；
    真正在跑的调度是 `bootstrap/scheduler_wiring` + `scheduler_pump` + `core/scheduler`）。
  ⇒ 处置: **只保留读面**（get_production_run + 它依赖的两个路径函数）,
    其余删除 —— 不保留"将来可能用"的死代码。

【为什么还留这个文件】两个真实消费者 import 的就是这个路径, 改路径要动它们 ⇒ 保留文件名最省事。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _workflows_dir(root: Path | str) -> Path:
    return Path(root) / "workflows"


def _prun_path(root: Path | str, run_id: str) -> Path:
    return _workflows_dir(root) / "runs" / f"{run_id}.json"


def get_production_run(root: Path | str, run_id: str) -> dict[str, Any] | None:
    """读一次 ProductionRun 的事实记录（不存在/损坏 ⇒ None, 不抛）。"""
    p = _prun_path(root, run_id)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None
