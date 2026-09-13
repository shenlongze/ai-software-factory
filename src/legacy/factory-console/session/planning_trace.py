"""factory-console/session/planning_trace.py — PlanningTrace (S10-062 批次 A)。

LLM Planning 基础设施 (GAP G6, 设计 §9): 每次 LLM planning 调用的可审计
轨迹 — provider/model/operation/input_hash/output/parsed_result/confidence/
token_usage/latency/fallback_used/validation_result/final_decision,
append 落盘 planning_trace.json (项目级 projects/<slug>/planning_trace.json,
缺省 ~/.factory/teams/planning_trace.json)。

安全边界 (设计 §9 — 不记录 API key / 敏感信息):
- 顶层字段显式白名单 (ALLOWED_KEYS): 未知键一律不落盘
- input 原文不落盘 — 只存 sha256 input_hash (hash_input 摘要)
- output/parsed_result/validation_result/final_decision 落盘前递归脱敏
  (sanitize: 键名命中敏感词 → 删除; 嵌套 dict/list 递归)
- token_usage 归一化 {input_tokens, output_tokens, total_tokens} (int)

失败安全: 读 (缺失/损坏 → []) / 写 (目录不可写等 → 不抛, 记录仍返回)。

边界 (批次 A 基础设施):
- 纯标准库 (json/hashlib/datetime/pathlib/copy), 零新依赖,
  不修改任何现有模块; 不调 LLM (调用方负责)

设计: docs/sprint10/S10-062-llm-planning-design.md §9-§10
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

#: 轨迹资产文件名 (项目级 projects/<slug>/planning_trace.json)
TRACE_FILE_NAME = "planning_trace.json"

#: 缺省轨迹资产文件 (~/.factory/teams/planning_trace.json — 设计 §9 口径;
#: 项目级记录 → projects/<slug>/planning_trace.json, 由调用方显式指定)
DEFAULT_TRACE_FILE = Path.home() / ".factory" / "teams" / "planning_trace.json"

#: 顶层字段白名单 (设计 §9 — 未知键不落盘; 敏感信息不落盘)
ALLOWED_KEYS: tuple[str, ...] = (
    "operation",
    "provider",
    "model",
    "input_hash",
    "output",
    "parsed_result",
    "confidence",
    "token_usage",
    "latency",
    "fallback_used",
    "validation_result",
    "final_decision",
    # S10-063: 关联字段 (cost ledger 聚合 / audit correlation)
    "task_id",
    "agent_id",
    "project_id",
    "parent_execution_id",
)

#: 敏感键精确名 (脱敏: 键名小写/下划线归一后 ∈ 该集合 → 删除)
SENSITIVE_KEYS_EXACT: frozenset[str] = frozenset({
    "token", "key", "auth", "secret", "password", "api_key", "apikey",
})

#: 敏感键子串 (脱敏: 键名小写/下划线归一后含任一子串 → 删除)
SENSITIVE_KEY_SUBSTRINGS: tuple[str, ...] = (
    "api_key", "apikey", "secret", "password", "authorization",
    "access_token", "refresh_token", "id_token", "auth_token", "bearer",
    "credential", "private_key", "client_secret",
)

#: 敏感字段集合 (record 直接参数: input_ 原文 / *_key 类)
SENSITIVE_ARGS: frozenset[str] = frozenset({
    "input", "api_key", "api_key_ref", "key", "secret", "password",
})

#: token_usage 归一化键 (int)
TOKEN_USAGE_KEYS: tuple[str, ...] = (
    "input_tokens", "output_tokens", "total_tokens",
)


def _now_iso() -> str:
    """UTC 当前时间 ISO 格式 (记录时间戳)。"""
    return datetime.now(timezone.utc).isoformat()


class PlanningTrace:
    """LLM planning 调用轨迹 (设计 §9): record → planning_trace.json (append)。

    record(...) — 组装归一化轨迹记录 (白名单键 + trace_id/timestamp),
    append 落盘 (失败安全, 不抛); hash_input(input) — sha256 摘要 (不存原文);
    sanitize(obj) — 递归脱敏 (敏感键删除); previous_records()/load() —
    读回全部记录 (缺失/损坏 → [], 失败安全); for_project(project_dir) —
    项目级轨迹实例 (projects/<slug>/planning_trace.json)。
    """

    FILE_NAME = TRACE_FILE_NAME

    def __init__(self, file: Optional[Path] = None) -> None:
        self._file = Path(file) if file is not None else DEFAULT_TRACE_FILE

    # ------------------------------------------------------------ record

    def record(
        self,
        operation: str = "",
        provider: str = "",
        model: str = "",
        input_hash: Optional[str] = None,
        output: Any = None,
        parsed_result: Any = None,
        confidence: float = 0.0,
        token_usage: Any = None,
        latency: float = 0.0,
        fallback_used: bool = False,
        validation_result: Any = None,
        final_decision: Any = None,
        input: Any = None,
        # S10-063: 关联字段 (cost ledger 聚合 / audit correlation)
        task_id: str = "",
        agent_id: str = "",
        project_id: str = "",
        parent_execution_id: str = "",
    ) -> dict[str, Any]:
        """组装 + append 落盘一条规划轨迹 (设计 §9 全字段 + trace_id/timestamp)。

        input_hash: 显式摘要 (sha256 hex); 未给且给 input → hash_input(input)
        计算 (input 原文不落盘 — 只存摘要); 均未给 → ""。
        output/parsed_result/validation_result/final_decision: 落盘前经
        sanitize 递归脱敏 (敏感键删除)。
        token_usage: dict {input_tokens, output_tokens, total_tokens} 或 int
        → 归一化 {input_tokens, output_tokens, total_tokens} (缺省 0)。
        confidence: 四舍五入 2 位; latency: float 秒; fallback_used: bool。

        返回归一化记录 dict (即使落盘失败也返回 — 失败安全)。
        """
        digest = input_hash
        if digest is None and input is not None:
            digest = self.hash_input(input)
        digest = str(digest or "")

        usage = self._normalize_usage(token_usage)
        record: dict[str, Any] = {
            "operation": str(operation or ""),
            "provider": str(provider or ""),
            "model": str(model or ""),
            "input_hash": digest,
            "output": self.sanitize(output),
            "parsed_result": self.sanitize(parsed_result),
            "confidence": round(float(confidence or 0.0), 2),
            "token_usage": usage,
            "latency": round(float(latency or 0.0), 4),
            "fallback_used": bool(fallback_used),
            "validation_result": self.sanitize(validation_result),
            "final_decision": self.sanitize(final_decision),
            # S10-063: 关联字段
            "task_id": str(task_id or ""),
            "agent_id": str(agent_id or ""),
            "project_id": str(project_id or ""),
            "parent_execution_id": str(parent_execution_id or ""),
            "trace_id": str(uuid.uuid4()),
            "timestamp": _now_iso(),
        }
        # 白名单之外绝不落盘 (防御性: 仅保留 ALLOWED_KEYS + trace_id/timestamp)
        record = {
            k: v for k, v in record.items()
            if k in ALLOWED_KEYS or k in ("trace_id", "timestamp")
        }
        records = self.previous_records()
        records.append(record)
        self.save(records)
        return record

    # ------------------------------------------------------------ 读/写

    def save(self, records: Any) -> None:
        """整表落盘 (失败安全: 读写异常 → 不抛)。"""
        if not isinstance(records, list):
            records = []
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            self._file.write_text(
                json.dumps(records, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001 — 失败安全: 落盘失败不中断调用流
            pass

    def load(self) -> list[dict[str, Any]]:
        """读回全部轨迹记录 (缺失/损坏 → [], 失败安全)。"""
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [
                    self._normalize(d) for d in data if isinstance(d, dict)
                ]
        except Exception:  # noqa: BLE001 — 失败安全: 缺失/损坏 → 空记录
            pass
        return []

    def previous_records(self) -> list[dict[str, Any]]:
        """读回全部轨迹记录 (load 别名 — 与 GapAnalyzer.previous_analyses 对齐)。"""
        return self.load()

    def records_for(self, operation: str) -> list[dict[str, Any]]:
        """某 operation 的全部历史轨迹记录。"""
        key = str(operation)
        return [r for r in self.load() if r.get("operation") == key]

    def records_file(self) -> Path:
        """当前落盘文件路径。"""
        return Path(self._file)

    @classmethod
    def for_project(cls, project_dir: Any) -> "PlanningTrace":
        """项目级轨迹实例 → projects/<slug>/planning_trace.json。"""
        return cls(file=Path(project_dir) / TRACE_FILE_NAME)

    # ------------------------------------------------------------ 脱敏/hash

    @classmethod
    def sanitize(cls, obj: Any) -> Any:
        """递归脱敏: 键名命中敏感词 → 删除该键 (dict/list 递归, 其余原样)。"""
        if isinstance(obj, dict):
            out: dict[str, Any] = {}
            for k, v in obj.items():
                key = str(k).lower().replace("-", "_")
                if cls._is_sensitive_key(key):
                    continue
                out[str(k)] = cls.sanitize(v)
            return out
        if isinstance(obj, list):
            return [cls.sanitize(v) for v in obj]
        return obj

    @staticmethod
    def hash_input(input: Any) -> str:
        """sha256 摘要 (设计 §9: 不存原文敏感内容 — 只存摘要)。

        dict/list → 稳定序列化 (sort_keys); 其余 → str。确定性。
        """
        if isinstance(input, (dict, list)):
            payload = json.dumps(input, ensure_ascii=False, sort_keys=True)
        else:
            payload = str(input or "")
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------ 内部

    @classmethod
    def _is_sensitive_key(cls, key: str) -> bool:
        """键名是否敏感 (精确名或子串命中 — 脱敏判定)。"""
        if key in SENSITIVE_KEYS_EXACT:
            return True
        return any(sub in key for sub in SENSITIVE_KEY_SUBSTRINGS)

    @classmethod
    def _normalize_usage(cls, token_usage: Any) -> dict[str, int]:
        """token_usage 归一化 {input_tokens, output_tokens, total_tokens} (int)。"""
        if isinstance(token_usage, dict):
            return {
                k: int(token_usage.get(k) or 0) for k in TOKEN_USAGE_KEYS
            }
        if isinstance(token_usage, (int, float)):
            total = int(token_usage or 0)
            return {"input_tokens": 0, "output_tokens": total, "total_tokens": total}
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    @classmethod
    def _normalize(cls, data: dict[str, Any]) -> dict[str, Any]:
        """历史记录归一化 (缺失字段缺省 + 白名单过滤 + 脱敏 — 前向兼容)。"""
        record: dict[str, Any] = {
            "operation": str(data.get("operation") or ""),
            "provider": str(data.get("provider") or ""),
            "model": str(data.get("model") or ""),
            "input_hash": str(data.get("input_hash") or ""),
            "output": cls.sanitize(data.get("output")),
            "parsed_result": cls.sanitize(data.get("parsed_result")),
            "confidence": round(float(data.get("confidence") or 0.0), 2),
            "token_usage": cls._normalize_usage(data.get("token_usage")),
            "latency": round(float(data.get("latency") or 0.0), 4),
            "task_id": str(data.get("task_id") or ""),
            "agent_id": str(data.get("agent_id") or ""),
            "project_id": str(data.get("project_id") or ""),
            "parent_execution_id": str(data.get("parent_execution_id") or ""),
            "fallback_used": bool(data.get("fallback_used")),
            "validation_result": cls.sanitize(data.get("validation_result")),
            "final_decision": cls.sanitize(data.get("final_decision")),
            "trace_id": str(data.get("trace_id") or ""),
            "timestamp": str(data.get("timestamp") or ""),
        }
        return {
            k: v for k, v in record.items()
            if k in ALLOWED_KEYS or k in ("trace_id", "timestamp")
        }
