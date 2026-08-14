"""factory-console/session/audit.py — 执行审计记录 (S10-049 P5)。

Agent 执行审计 (最小): 每次 agent.execute_task 执行结果 append 到
~/.factory/exec/execution_records.json (workspace 缺省即 data_dir)。

- record_execution(record) — append 一条记录 (原子写: tmp + os.replace;
  目录不存在自动创建; 失败安全 — 审计失败不阻断主流程)
- load_records() — 读回全部记录 (缺文件/损坏 → [], 失败安全)

记录字段 (设计 §2.6): intent/action/agent/task/result/result_id/timestamp
(+ error 失败详情) — 未来 audit/cost/replay 数据源。

设计: docs/sprint10/S10-049-agent-execution-design.md §2.6
边界:
- 只做追加式审计, 不复制/不执行业务 (执行仍由 Action 负责)
- 纯标准库 (json/os/pathlib), 零新依赖
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

#: 默认审计记录文件 (~/.factory/exec/execution_records.json — workspace 缺省 = data_dir)
DEFAULT_RECORDS_FILE = Path.home() / ".factory" / "exec" / "execution_records.json"


def record_execution(record: dict, records_file: Optional[Path] = None) -> None:
    """append 一条执行记录 (原子写; 目录不存在创建; 失败安全 — 审计不阻断执行)。

    records_file 可注入 (测试/隔离工作区); 缺省 → ~/.factory/exec/execution_records.json。
    """
    try:
        path = Path(records_file) if records_file is not None else DEFAULT_RECORDS_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        records = load_records(path)
        records.append(record)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(tmp, path)
    except Exception:  # noqa: BLE001 — 失败安全: 审计失败不影响主流程
        return


def load_records(records_file: Optional[Path] = None) -> list[dict]:
    """读回全部执行记录; 缺文件/损坏/非列表 → [] (失败安全, 永不抛)。"""
    path = Path(records_file) if records_file is not None else DEFAULT_RECORDS_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001 — 失败安全
        return []
