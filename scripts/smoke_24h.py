#!/usr/bin/env python3
"""scripts/smoke_24h.py — P0-4/C-5 24h 长跑 (S10-121)。

24h 长跑变体: 等价于 `smoke_longrun.py --duration 86400 --heartbeat 300`。

⚠️ 诚实标注: 本脚本提供但**未真跑 24h** — 实际执行前请确认运行环境可承受
24h 连续运行 (建议 tmux/nohup + 临时 workspace); 跑满 24h 后
.eval/longrun_result.json status=completed, EvalSuite longevity.longrun 才判通过;
未跑满 → 如实标【待长跑】(不伪造)。

用法:
    python scripts/smoke_24h.py [--workspace <dir>] [--heartbeat 300]

边界: 复用 smoke_longrun 主循环; 默认临时 workspace 零污染真实数据。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from smoke_longrun import LONGRUN_24H_S, run_longrun


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="K-5 24h 长跑 (标待长跑直到跑满)")
    parser.add_argument("--workspace", default=None, help="workspace 目录 (缺省 = 临时目录)")
    parser.add_argument("--heartbeat", type=int, default=300, help="心跳间隔秒数 (缺省 300 = 5min)")
    args = parser.parse_args(argv)
    if args.workspace:
        ws = Path(args.workspace)
        ws.mkdir(parents=True, exist_ok=True)
    else:
        import tempfile
        ws = Path(tempfile.mkdtemp(prefix="factory-24h-"))
    print("⚠️ 24h 长跑: 脚本已提供但未真跑满 24h — 如实标【待长跑】直到 duration>=86400s 完成。")
    result = run_longrun(
        duration=int(LONGRUN_24H_S),
        heartbeat=args.heartbeat,
        workspace=ws,
        label="24h",
    )
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
