"""factory-console/memory/experience_store.py — ExperienceStore (S10-067 G2)。

经验持久化: experience_store.json (workspace/memory/) + 失败安全读写。

设计: docs/sprint10/S10-067-memory-learning-design.md §2
组件:
- ExperienceStore — add(record) / records(type=None, project=None) /
  stats() / save / load → experience_store.json
边界:
- 纯标准库 (json/pathlib), 零模块依赖
- 失败安全: 缺失/损坏文件 → 空记录; 落盘异常 → 静默 (不中断学习流)
- add 去重 (同 id 覆盖更新 — 提取幂等); type 非法 → ValueError (校验铁律)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .experience import ExperienceRecord, ensure_type

#: 经验库目录 (workspace/memory/ — S10-067 资产空间)
MEMORY_DIR_NAME = "memory"

#: 经验库文件名 (workspace/memory/experience_store.json)
EXPERIENCE_STORE_FILE_NAME = "experience_store.json"

#: 缺省工厂根 (~/.factory — 与 commands/audit 数据空间同口径)
DEFAULT_WORKSPACE = Path.home() / ".factory"


def memory_dir(workspace: Any = None) -> Path:
    """workspace/memory 目录 (缺省 → ~/.factory/memory)。"""
    root = Path(workspace) if workspace is not None else DEFAULT_WORKSPACE
    return root / MEMORY_DIR_NAME


def experience_store_file(workspace: Any = None) -> Path:
    """workspace/memory/experience_store.json (缺省工厂根)。"""
    return memory_dir(workspace) / EXPERIENCE_STORE_FILE_NAME


class ExperienceStore:
    """经验库 (G2): 内存记录 + experience_store.json 持久化 (失败安全)。

    add(record): 同 id 覆盖更新 (提取幂等 — 重跑不产生重复经验) + 落盘;
    records(type=None, project=None): 过滤视图 (类型/项目);
    stats(): 按类型/成功/Agent 聚合统计;
    save()/load(): 落盘/读取 (缺失/损坏 → 空列表, 不抛)。
    """

    def __init__(self, path: Any = None) -> None:
        self.path: Path = (
            Path(path) if path is not None else experience_store_file()
        )
        self._records: list[ExperienceRecord] = []
        self.load()

    # ------------------------------------------------------------ 读写

    def load(self) -> list[ExperienceRecord]:
        """读 experience_store.json → 记录列表 (缺失/损坏 → [] 失败安全)。"""
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — 失败安全: 缺失/损坏 → 空
            self._records = []
            return self._records
        loaded: list[ExperienceRecord] = []
        if isinstance(data, list):
            for item in data:
                try:
                    loaded.append(ExperienceRecord.from_dict(item))
                except Exception:  # noqa: BLE001 — 单条损坏跳过, 不整体失败
                    continue
        self._records = loaded
        return self._records

    def save(self) -> Path:
        """落盘 experience_store.json (父目录自动创建; 失败安全: 异常不抛)。"""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(
                    [r.to_dict() for r in self._records],
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001 — 失败安全: 落盘失败不中断学习流
            pass
        return self.path

    # ------------------------------------------------------------ 变更

    def add(self, record: Any) -> ExperienceRecord:
        """新增经验 (G2): 校验类型 → 同 id 覆盖 → 落盘 → 返回记录。

        type 非法 → ValueError (校验铁律); 其余字段由 from_dict 兜底。
        """
        if isinstance(record, ExperienceRecord):
            item = record
        else:
            item = ExperienceRecord.from_dict(record)
        ensure_type(item.type)
        replaced = False
        for i, existing in enumerate(self._records):
            if existing.id == item.id:
                self._records[i] = item
                replaced = True
                break
        if not replaced:
            self._records.append(item)
        self.save()
        return item

    def add_all(self, records: list[Any]) -> int:
        """批量新增 (提取器聚合入口 — 去重后返回实际新增/更新条数)。"""
        added = 0
        for record in records or []:
            try:
                self.add(record)
                added += 1
            except Exception:  # noqa: BLE001 — 单条失败跳过 (失败安全)
                continue
        return added

    # ------------------------------------------------------------ 查询

    def records(
        self, type: Optional[str] = None, project: Optional[str] = None
    ) -> list[ExperienceRecord]:
        """过滤视图: 类型/项目过滤 (None = 不过滤); 保持存储顺序。"""
        out = self._records
        if type is not None:
            out = [r for r in out if r.type == str(type)]
        if project is not None:
            out = [r for r in out if r.project == str(project)]
        return list(out)

    def get(self, record_id: str) -> Optional[ExperienceRecord]:
        """按 id 取记录 (未找到 → None)。"""
        for r in self._records:
            if r.id == str(record_id):
                return r
        return None

    def stats(self) -> dict[str, Any]:
        """经验统计 (G2/验收): 总量 + 按类型 + 按成功 + 按 Agent。"""
        by_type: dict[str, int] = {}
        by_success = {"success": 0, "failed": 0}
        by_agent: dict[str, int] = {}
        for r in self._records:
            by_type[r.type] = by_type.get(r.type, 0) + 1
            if r.success:
                by_success["success"] += 1
            else:
                by_success["failed"] += 1
            if r.agent:
                by_agent[r.agent] = by_agent.get(r.agent, 0) + 1
        return {
            "total": len(self._records),
            "by_type": dict(sorted(by_type.items())),
            "by_success": by_success,
            "by_agent": dict(sorted(by_agent.items())),
            "file": str(self.path),
        }

    @classmethod
    def from_workspace(cls, workspace: Any = None) -> "ExperienceStore":
        """workspace 装配 (workspace/memory/experience_store.json)。"""
        return cls(experience_store_file(workspace))
