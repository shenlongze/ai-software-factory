"""factory-console/retry_policy.py — S20.5 Verification Retry Contract。

单一 policy 来源:
- MAX_VERIFICATION_ATTEMPTS: 默认 3 (bounded, 不硬编码在多个地方)
- is_retryable_verification(check): 失败分类
  RETRYABLE:   infra/subprocess 中断 (exit_code 特殊值/timeout/runner 不可用)
  NON_RETRYABLE: syntax failure / pytest assertion failure / deterministic fail

原则:
- retry count bounded (MAX_VERIFICATION_ATTEMPTS)
- non-retryable → 直接 FAILED (不 retry)
- retry 历史 append-only (verification_attempts)
"""
from __future__ import annotations

from typing import Any

#: 默认最大 verification attempts (bounded retry)
MAX_VERIFICATION_ATTEMPTS = 3

#: retryable exit codes (subprocess 中断类)
RETRYABLE_EXIT_CODES = {-1, 124, 137, 143}  # 信号终止 / timeout / killed

#: retryable 关键词 (runner 不可用 / timeout / 环境类)
RETRYABLE_KEYWORDS = ("timeout", "timed out", "command not found",
                      "runner unavailable", "killed", "segmentation", "resource temporarily")


def is_retryable_verification(check: dict[str, Any]) -> bool:
    """分类 verification check 失败是否可重试。

    RETRYABLE:   infra/timeout/runner (exit_code 特殊值或错误信息关键词)
    NON_RETRYABLE: syntax/pytest assertion/deterministic fail
    """
    exit_code = int(check.get("exit_code") or 0)
    stderr = str(check.get("stderr") or "")
    stdout = str(check.get("stdout") or "")
    combined = (stderr + " " + stdout).lower()
    if exit_code in RETRYABLE_EXIT_CODES:
        return True
    for kw in RETRYABLE_KEYWORDS:
        if kw in combined:
            return True
    return False
