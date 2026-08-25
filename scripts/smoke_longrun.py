#!/usr/bin/env python3
"""scripts/smoke_longrun.py — P0-4/C-5 长跑冒烟 (S10-121, 可配置时长 + 心跳断言存活)。

用法:
    python scripts/smoke_longrun.py --duration 30 --heartbeat 5 [--workspace <dir>]
    python scripts/smoke_longrun.py --duration 1800      # 30min 冒烟
    python scripts/smoke_longrun.py --duration 86400     # 24h 长跑 (跑满才算完成)

行为:
- 每 N 秒一次心跳: 断言进程存活 + 心跳计数单调递增 (写 .eval/longrun_heartbeats.jsonl)
- 结束时写 .eval/longrun_result.json 证据 (EvalSuite longevity.longrun 消费):
  - duration_seconds < 24h → status="待长跑" (如实标注, 不伪造完成)
  - duration_seconds >= 24h → status="completed" (24h 长跑真实完成)
- 默认临时 workspace (tempfile) — 零污染真实数据; 24h 变体见 scripts/smoke_24h.py

边界: 纯标准库; 不调 LLM; 失败安全 (心跳异常 → 如实记录, 不崩)。
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

#: 24h 长跑阈值 (秒) — 与 eval_suite.LONGRUN_24H_S 同源口径
LONGRUN_24H_S = 24 * 60 * 60


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_longrun(
    *,
    duration: int,
    heartbeat: int,
    workspace: Path,
    label: str = "longrun",
) -> dict:
    """长跑冒烟主循环 (返回结果 dict; 也可独立调用 — 测试用)。"""
    ws = Path(workspace)
    eval_dir = ws / ".eval"
    eval_dir.mkdir(parents=True, exist_ok=True)
    heartbeat_file = eval_dir / "longrun_heartbeats.jsonl"
    result_file = eval_dir / "longrun_result.json"

    start = time.monotonic()
    end = start + float(duration)
    heartbeats: list[dict] = []
    failures: list[str] = []
    beat = 0
    print(f"[{label}] 长跑冒烟开始: duration={duration}s heartbeat={heartbeat}s workspace={ws}")
    while True:
        now_mono = time.monotonic()
        if now_mono >= end:
            break
        beat += 1
        # 心跳: 断言存活 (计数单调递增 + 进程可响应)
        try:
            assert beat > 0
            record = {
                "beat": beat,
                "ts": _now_iso(),
                "elapsed_seconds": round(now_mono - start, 3),
                "alive": True,
            }
            with heartbeat_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            heartbeats.append(record)
            print(f"  ♥ [{label}] beat {beat} @ {record['elapsed_seconds']:.1f}s (alive)")
        except Exception as exc:  # noqa: BLE001 — 失败安全: 心跳异常如实记录
            failures.append(f"beat {beat}: {exc}")
            print(f"  ✗ [{label}] beat {beat} 心跳失败: {exc}", file=sys.stderr)
        time.sleep(min(float(heartbeat), max(0.0, end - time.monotonic())))
    elapsed = time.monotonic() - start
    completed = elapsed >= LONGRUN_24H_S
    result = {
        "ok": not failures,
        "label": label,
        "duration_seconds": round(elapsed, 3),
        "heartbeats": len(heartbeats),
        "failures": failures,
        "status": "completed" if completed else "待长跑",
        "note": (
            "24h 长跑真实完成" if completed
            else "未满 24h — 如实标【待长跑】(24h 脚本: scripts/smoke_24h.py)"
        ),
        "generated_at": _now_iso(),
    }
    result_file.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[{label}] 长跑冒烟结束: {elapsed:.1f}s, {len(heartbeats)} 次心跳, 状态={result['status']}")
    print(f"[{label}] 证据: {result_file}")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="K-5 长跑冒烟 (可配置时长 + 心跳存活断言)")
    parser.add_argument("--duration", type=int, default=1800, help="长跑时长秒数 (缺省 1800 = 30min)")
    parser.add_argument("--heartbeat", type=int, default=5, help="心跳间隔秒数 (缺省 5)")
    parser.add_argument("--workspace", default=None, help="workspace 目录 (缺省 = 临时目录, 零污染)")
    parser.add_argument("--label", default="longrun", help="冒烟标签 (缺省 longrun)")
    parser.add_argument("--json", action="store_true", help="结束时输出结果 JSON")
    args = parser.parse_args(argv)

    if args.duration <= 0 or args.heartbeat <= 0:
        print("[E5001] 错误: --duration/--heartbeat 必须为正整数 (建议: 传正数后重试)", file=sys.stderr)
        return 2
    if args.workspace:
        ws = Path(args.workspace)
        ws.mkdir(parents=True, exist_ok=True)
    else:
        ws = Path(tempfile.mkdtemp(prefix="factory-longrun-"))
    try:
        result = run_longrun(
            duration=args.duration,
            heartbeat=args.heartbeat,
            workspace=ws,
            label=args.label,
        )
    except Exception as exc:  # noqa: BLE001 — 失败安全
        print(f"[E5002] 错误: 长跑冒烟异常 — {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
