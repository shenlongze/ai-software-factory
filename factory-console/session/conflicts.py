"""factory-console/session/conflicts.py — FileOwnership + ConflictDetector (S10-056 批次 A)。

文件冲突检测 (设计 §2.7): FileOwnership 记录 task → files 归属;
ConflictDetector 检测同文件多任务修改 → ConflictRecord (status "open" 保留,
只检测不解决 — 边界 §7), 落盘 conflicts.json (~/.factory/teams/)。

组件:
- FileOwnership — claim(project_dir, task_id, files) / owned_by(file) / clear()
- ConflictRecord — {task_a, task_b, file, detected_at, status: "open"}
- ConflictDetector — detect(project_dir, task_id, files) → list[ConflictRecord]
  (同文件已被其他 task claim → 冲突记录, 去重; 未归属文件 → 顺带 claim) /
  list() / save() / load() (失败安全: 缺失/损坏 → 空记录)

设计: docs/sprint10/S10-056-team-design.md §2.7 / §4
边界:
- 纯标准库 (json/pathlib/dataclasses), 零模块依赖; 失败安全, 永不抛
- 只检测不解决: 冲突记录 status 恒为 "open", 不做自动合并/解决
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

#: 默认冲突文件 (~/.factory/teams/conflicts.json — 设计 §4 资产口径)
DEFAULT_CONFLICTS_FILE = Path.home() / ".factory" / "teams" / "conflicts.json"

#: 冲突状态常量 (只检测不解决 — status 恒为 open)
CONFLICT_STATUS_OPEN = "open"


def _now_iso() -> str:
    """UTC 当前时间 ISO 格式 (冲突检测时间戳)。"""
    return datetime.now(timezone.utc).isoformat()


class FileOwnership:
    """task → files 归属记录 (按项目隔离: {project: {file: task_id}})。

    claim(project_dir, task_id, files): 记录归属 (文件归一化为项目相对路径,
    非项目内路径保留原样; 同文件新 task → 覆盖, 记录最新归属)。
    owned_by(file): 查询文件归属 task (跨项目精确匹配 → 文件名兜底);
    未归属 → None。clear(): 清空全部归属。
    """

    def __init__(self, data: Optional[dict[str, Any]] = None) -> None:
        self._ownership: dict[str, dict[str, str]] = {}
        if isinstance(data, dict):
            for project, store in data.items():
                if isinstance(store, dict):
                    self._ownership[str(project)] = {
                        str(k): str(v) for k, v in store.items()
                    }

    @staticmethod
    def _norm(project_dir: Any, file: Any) -> str:
        """文件归一化: 项目内 → 相对路径; 其他 → 原样字符串。"""
        try:
            return str(Path(file).resolve().relative_to(Path(project_dir).resolve()))
        except (ValueError, OSError):  # noqa: BLE001 — 非项目内路径 → 原样
            return str(file)

    def claim(self, project_dir: Any, task_id: str, files: list[str]) -> None:
        """记录 task → files 归属 (文件级幂等覆盖; 缺省 files → 无操作)。"""
        if not files:
            return
        project = str(project_dir)
        store = self._ownership.setdefault(project, {})
        for file in files:
            store[self._norm(project_dir, file)] = str(task_id)

    def owned_by(self, file: Any) -> Optional[str]:
        """文件归属 task_id; 未归属 → None (跨项目精确 → 文件名兜底)。"""
        key = str(file)
        for store in self._ownership.values():
            if key in store:
                return store[key]
        base = Path(key).name
        for store in self._ownership.values():
            if base in store:
                return store[base]
        return None

    def clear(self) -> None:
        """清空全部归属记录。"""
        self._ownership.clear()

    def to_dict(self) -> dict[str, dict[str, str]]:
        """归属快照 (拷贝, 不泄漏内部)。"""
        return {p: dict(s) for p, s in self._ownership.items()}


@dataclass
class ConflictRecord:
    """冲突记录 (设计 §2.7): task_a (先归属者) vs task_b (后检测者) 同文件。

    status 恒为 "open" — 只检测不解决 (边界 §7)。
    """

    task_a: str
    task_b: str
    file: str
    detected_at: str = field(default_factory=_now_iso)
    status: str = CONFLICT_STATUS_OPEN

    def to_dict(self) -> dict[str, Any]:
        """落盘格式: {task_a, task_b, file, detected_at, status} (设计 §2.7)。"""
        return {
            "task_a": self.task_a,
            "task_b": self.task_b,
            "file": self.file,
            "detected_at": self.detected_at,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "ConflictRecord":
        """读回格式 → ConflictRecord; 缺字段失败安全缺省 (status 缺省 open)。"""
        data = data if isinstance(data, dict) else {}
        return cls(
            task_a=str(data.get("task_a") or ""),
            task_b=str(data.get("task_b") or ""),
            file=str(data.get("file") or ""),
            detected_at=str(data.get("detected_at") or _now_iso()),
            status=str(data.get("status") or CONFLICT_STATUS_OPEN),
        )


class ConflictDetector:
    """冲突检测器 (设计 §2.7): 同文件多任务 → ConflictRecord (open, 不解决)。

    detect(project_dir, task_id, files): 对每个文件 — 已被其他 task 归属 →
    冲突记录 (去重: 同 task_a/task_b/file 不重复记录); 未归属 → 顺带 claim
    (当前 task 取得归属)。新冲突自动落盘。只检测不解决 (status 恒 open)。
    """

    DEFAULT_FILE = DEFAULT_CONFLICTS_FILE

    def __init__(
        self,
        conflicts_file: Optional[Path] = None,
        ownership: Optional[FileOwnership] = None,
    ) -> None:
        self._file = (
            Path(conflicts_file) if conflicts_file is not None else self.DEFAULT_FILE
        )
        self._ownership = ownership if ownership is not None else FileOwnership()
        self._records: list[ConflictRecord] = []
        self._load()

    # ------------------------------------------------------------ 检测

    def detect(
        self, project_dir: Any, task_id: str, files: list[str]
    ) -> list[ConflictRecord]:
        """检测文件冲突 (同文件已被其他 task claim → 记录; 未归属 → claim)。"""
        new_records: list[ConflictRecord] = []
        for file in files or []:
            owner = self._ownership.owned_by(file)
            if owner is None:
                self._ownership.claim(project_dir, task_id, [file])
            elif owner != str(task_id):
                record = ConflictRecord(
                    task_a=owner, task_b=str(task_id), file=str(file)
                )
                if not self._contains(record):
                    self._records.append(record)
                    new_records.append(record)
        if new_records:
            self._save()
        return new_records

    def _contains(self, record: ConflictRecord) -> bool:
        """同 (task_a/task_b/file) 记录是否已存在 (去重)。"""
        return any(
            r.task_a == record.task_a
            and r.task_b == record.task_b
            and r.file == record.file
            for r in self._records
        )

    # ------------------------------------------------------------ 查询/落盘

    def list(self) -> list[dict[str, Any]]:
        """全部冲突记录 (检测顺序)。"""
        return [r.to_dict() for r in self._records]

    def _load(self) -> None:
        data: Any = None
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — 失败安全: 缺失/损坏 → 空记录
            data = None
        if isinstance(data, list):
            self._records = [
                ConflictRecord.from_dict(r) for r in data if isinstance(r, dict)
            ]
        else:
            self._records = []

    def load(self, file: Optional[Path] = None) -> "ConflictDetector":
        """(重)加载冲突记录 (缺省当前文件); 返回 self 支持链式。"""
        if file is not None:
            self._file = Path(file)
        self._load()
        return self

    def _save(self) -> Path:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(
            json.dumps(
                [r.to_dict() for r in self._records], ensure_ascii=False, indent=2
            )
            + "\n",
            encoding="utf-8",
        )
        return self._file

    def save(self, file: Optional[Path] = None) -> Path:
        """落盘 conflicts.json (可指定文件); 返回文件路径。"""
        if file is not None:
            self._file = Path(file)
        return self._save()
