"""runtime/store.py — RuntimeStore: JSON 文件持久化 (单文件三节, 原子写, 标准库零依赖)。

设计依据:
- phase4b1-status.md: JSON 持久化 — `.factory/runtimes/runtimes.json` + executions 记录,
  原子写 os.replace, 损坏报错 (参照 workflows/store.py 模式)。
- 文件格式 (单文件三节, KISS):
  ```json
  {
    "runtimes":   {"R-001": {RuntimeInfo dict}, ...},
    "executions": {"EX-001": {ExecutionRequest dict}, ...},
    "results":    {"EX-001": {ExecutionResult dict}, ...}
  }
  ```
  results 以 request_id 为键 (一次执行至多一个结果, upsert 幂等; 见 ADR-0006 决策 3)。
- 原子写: 临时文件 + os.replace; 单进程本地使用, 不做文件锁。
- 损坏文件 (JSON 解析失败 / 模型校验失败 / 结构不符) → 抛 CorruptRuntimeStoreError,
  绝不静默返回空。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from .types import ExecutionRequest, ExecutionResult, RuntimeInfo

_SECTIONS = ("runtimes", "executions", "results")


class RuntimeStoreError(Exception):
    """RuntimeStore 基础异常。"""


class CorruptRuntimeStoreError(RuntimeStoreError):
    """存储文件损坏 (JSON 解析失败 / 结构不符 / 模型校验失败)。"""


class RuntimeStore:
    """Runtime 注册信息 + 执行请求/结果的 JSON 文件库 (单文件三节)。"""

    filename = "runtimes.json"

    def __init__(self, runtimes_dir: str | Path):
        self._dir = Path(runtimes_dir)

    @property
    def dir(self) -> Path:
        return self._dir

    @property
    def path(self) -> Path:
        return self._dir / self.filename

    # ------------------------------------------------------------------ 读

    def _read_all(self) -> dict:
        """读整库为 {节名: {id: dict}}; 文件不存在返回空库。"""
        if not self.path.exists():
            return {s: {} for s in _SECTIONS}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CorruptRuntimeStoreError(f"corrupt runtime store: {self.path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise CorruptRuntimeStoreError(f"corrupt runtime store: {self.path}: expected JSON object")
        for key in _SECTIONS:
            if not isinstance(raw.get(key), dict):
                raise CorruptRuntimeStoreError(
                    f"corrupt runtime store: {self.path}: missing or invalid section {key!r}"
                )
        return raw

    def _load(self, model: type[BaseModel], data: Any) -> BaseModel:
        try:
            return model.model_validate(data)
        except ValidationError as exc:
            raise CorruptRuntimeStoreError(f"corrupt runtime store: {self.path}: {exc}") from exc

    def get_runtime(self, runtime_id: str) -> RuntimeInfo | None:
        """按 id 取 Runtime; 不存在返回 None。"""
        data = self._read_all()["runtimes"].get(runtime_id)
        if data is None:
            return None
        return self._load(RuntimeInfo, data)  # type: ignore[return-value]

    def list_runtimes(self) -> list[RuntimeInfo]:
        """全部 Runtime (按 id 排序)。"""
        runtimes = [self._load(RuntimeInfo, data) for data in self._read_all()["runtimes"].values()]
        return sorted(runtimes, key=lambda r: r.id)  # type: ignore[return-value]

    def get_execution(self, execution_id: str) -> ExecutionRequest | None:
        """按 id 取执行请求; 不存在返回 None。"""
        data = self._read_all()["executions"].get(execution_id)
        if data is None:
            return None
        return self._load(ExecutionRequest, data)  # type: ignore[return-value]

    def list_executions(self, *, task_id: str | None = None) -> list[ExecutionRequest]:
        """全部执行请求 (按 id 排序), 可选按任务过滤。"""
        requests = []
        for data in self._read_all()["executions"].values():
            req = self._load(ExecutionRequest, data)
            if task_id is not None and req.task_id != task_id:  # type: ignore[union-attr]
                continue
            requests.append(req)
        return sorted(requests, key=lambda r: r.id)  # type: ignore[union-attr]

    def get_result(self, request_id: str) -> ExecutionResult | None:
        """按 request_id 取执行结果 (一次执行至多一个); 不存在返回 None。"""
        data = self._read_all()["results"].get(request_id)
        if data is None:
            return None
        return self._load(ExecutionResult, data)  # type: ignore[return-value]

    def list_results(self) -> list[ExecutionResult]:
        """全部执行结果 (按 request_id 排序)。"""
        results = [self._load(ExecutionResult, data) for data in self._read_all()["results"].values()]
        return sorted(results, key=lambda r: r.request_id)  # type: ignore[return-value]

    # ------------------------------------------------------------------ 写

    def save_runtime(self, runtime: RuntimeInfo) -> None:
        """upsert Runtime 身份记录。"""
        raw = self._read_all()
        raw["runtimes"][runtime.id] = runtime.to_dict()
        self._write_all(raw)

    def remove_runtime(self, runtime_id: str) -> bool:
        """删除 Runtime; 不存在返回 False。"""
        raw = self._read_all()
        if runtime_id not in raw["runtimes"]:
            return False
        del raw["runtimes"][runtime_id]
        self._write_all(raw)
        return True

    def save_execution(self, request: ExecutionRequest) -> None:
        """upsert 执行请求 (状态推进也走此路径: 保存新 status 即覆盖)。"""
        raw = self._read_all()
        raw["executions"][request.id] = request.to_dict()
        self._write_all(raw)

    def save_result(self, result: ExecutionResult) -> None:
        """upsert 执行结果 (以 request_id 为键: 一次执行至多一个结果, 幂等覆盖)。"""
        raw = self._read_all()
        raw["results"][result.request_id] = result.to_dict()
        self._write_all(raw)

    def _write_all(self, data: dict) -> None:
        """原子写整库: 临时文件 + os.replace, 避免半写文件; 各节按 id 排序 (审计友好)。"""
        self._dir.mkdir(parents=True, exist_ok=True)
        tmp = self._dir / f".{self.filename}.{os.getpid()}.tmp"
        payload = {s: {k: data[s][k] for k in sorted(data[s])} for s in _SECTIONS}
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, self.path)

    # ------------------------------------------------------------------ 便捷

    def runtime_ids(self) -> list[str]:
        """现有 Runtime id 列表 (排序)。"""
        return sorted(self._read_all()["runtimes"])

    def execution_ids(self) -> list[str]:
        """现有执行请求 id 列表 (排序)。"""
        return sorted(self._read_all()["executions"])

    def next_runtime_id(self, prefix: str = "R-") -> str:
        """自动编号: 取现有最大数字后缀 +1 (如 R-001 → R-002)。"""
        return self._next_id(prefix, self.runtime_ids())

    def next_execution_id(self, prefix: str = "EX-") -> str:
        """自动编号: 取现有最大数字后缀 +1 (如 EX-001 → EX-002)。"""
        return self._next_id(prefix, self.execution_ids())

    @staticmethod
    def _next_id(prefix: str, ids: list[str]) -> str:
        max_n = 0
        for item_id in ids:
            rest = item_id[len(prefix):] if item_id.startswith(prefix) else ""
            if rest.isdigit():
                max_n = max(max_n, int(rest))
        return f"{prefix}{max_n + 1:03d}"


#: ★ 运行时状态的唯一目录名 —— 权威依据: ADR-0006
#:   "执行记录归属: 指令要求 `.factory/runtimes/runtimes.json` + executions 记录"
RUNTIME_DIR_NAME = "runtimes"


def open_runtime_store(root: str | Path) -> RuntimeStore:
    """★ 全仓唯一的 RuntimeStore 装配点（目录名只在此定义一次）。

    为什么必须有它（2026-09-19 实测教训 —— 不重复造轮子的反面案例）:
      仓库里曾有 **6 处绕过装配、直接 `RuntimeStore(root / "runtime")`** 并写错了目录名
      （少一个 s）:  scheduler_pump.py ×4 · console_view.py（舰队视图）· healing.py（自愈）。
      ⇒ 后果（三个能力**静默失效**, 读空目录不报错）:
         · 舰队视图永远显示"没人干活"     · 自愈永远认为"没有卡住的任务"
         · pump 与 CLI 的数据**互不可见**
      而 CLI 侧因为早就有 `_open_runtime_store`（一处定义 + 14 处引用）**从未写错**。
      ⇒ 修法（本函数）: 把装配点从 apps 下移到 src（apps 可依赖 src, 反之不行）,
        全仓统一走这里 ⇒ 目录名**结构上不可能再不一致**。
    """
    return RuntimeStore(Path(root) / RUNTIME_DIR_NAME)
