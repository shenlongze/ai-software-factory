"""services/approval_runtime — 审批运行时（绞杀者模式第一刀）。

新实现替换 `factory approval` CLI 链（原: factory-exec/exec/approval.py）。
- 契约: ai_factory_os.contracts.governance.GovernanceGate
- 存储: 沿用原格式 `<exec_dir>/approvals.json`（{"approvals": {id: {...}}}）
- 规则: 原样复现 classify_risk（分级审批）
"""
from __future__ import annotations

from .gate import ApprovalGate, ApprovalRuntimeError
from .rules import classify_risk
from .store import ApprovalStore

__all__ = ["ApprovalGate", "ApprovalRuntimeError", "ApprovalStore", "classify_risk"]
