"""factory-console/session/dependencies.py — TaskDependencyGraph (S10-056 批次 A)。

任务依赖 DAG 数据结构 (设计 §2.4): task → [depends_on] 有向边,
落盘 task_dependencies.json (~/.factory/teams/)。保留顺序执行兼容
(dependencies 为空 → 原顺序); 只做数据结构 + 基础拓扑排序 (Kahn),
不实现复杂调度 (边界 §7)。

组件:
- TaskDependencyGraph — add_dependency/get/has/to_dict/from_dict/load/save +
  topological_order(tasks) (无环稳定拓扑; 空依赖 → 输入原顺序; 环 → 失败安全
  剩余节点按原顺序追加)

设计: docs/sprint10/S10-056-team-design.md §2.4 / §3
边界:
- 纯标准库 (json/pathlib), 零模块依赖; 失败安全 (缺失/损坏 → 空图, 永不抛)
- 图只在输入任务集合内取边 (图外任务/依赖不影响拓扑结果)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

#: 默认依赖文件 (~/.factory/teams/task_dependencies.json — 设计 §4 资产口径)
DEFAULT_DEPENDENCIES_FILE = Path.home() / ".factory" / "teams" / "task_dependencies.json"


class TaskDependencyGraph:
    """任务依赖图: {task: [depends_on...]} (depends_on 必须先于 task 执行)。

    topological_order(tasks): Kahn 拓扑排序 — 依赖边 (depends_on → task) 取
    输入集合内部分; 入度 0 节点按输入顺序出队 (稳定); 无依赖 → 原顺序
    (顺序执行兼容); 环 → 剩余节点按原顺序追加 (失败安全, 不抛)。
    """

    DEFAULT_FILE = DEFAULT_DEPENDENCIES_FILE

    def __init__(
        self, dependencies: Optional[dict[str, list[str]]] = None
    ) -> None:
        self._deps: dict[str, list[str]] = {}
        for task, deps in (dependencies or {}).items():
            self._deps[str(task)] = [
                str(d) for d in (deps or []) if not isinstance(d, dict)
            ]

    # ------------------------------------------------------------ 变更/查询

    def add_dependency(self, task: str, depends_on: str) -> None:
        """task 依赖 depends_on (depends_on 先执行); 同依赖重复添加 → 幂等。"""
        key = str(task)
        dep = str(depends_on)
        deps = self._deps.setdefault(key, [])
        if dep not in deps:
            deps.append(dep)

    def get(self, task: str) -> list[str]:
        """task 的直接依赖列表 (未注册 → 空列表, 拷贝返回)。"""
        return list(self._deps.get(str(task), []))

    def has(self, task: str) -> bool:
        """task 是否在依赖图中 (有依赖声明或依赖被依赖)。"""
        key = str(task)
        if key in self._deps:
            return True
        return any(key in deps for deps in self._deps.values())

    # ------------------------------------------------------------ 序列化

    def to_dict(self) -> dict[str, list[str]]:
        """落盘格式: {task: [depends_on...]} (拷贝, 不泄漏内部)。"""
        return {k: list(v) for k, v in self._deps.items()}

    @classmethod
    def from_dict(cls, data: Any) -> "TaskDependencyGraph":
        """任意结构 → 图; 非 dict → 空图 (失败安全)。"""
        if not isinstance(data, dict):
            return cls()
        return cls(data)

    @classmethod
    def load(cls, file: Optional[Path] = None) -> "TaskDependencyGraph":
        """读 task_dependencies.json → 图; 缺失/损坏 → 空图 (失败安全)。"""
        path = Path(file) if file is not None else cls.DEFAULT_FILE
        data: Any = None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — 失败安全: 缺失/损坏 → 空图
            data = None
        return cls.from_dict(data)

    def save(self, file: Optional[Path] = None) -> Path:
        """落盘 task_dependencies.json (父目录自动创建; 中文可读)。"""
        path = Path(file) if file is not None else self.DEFAULT_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    # ------------------------------------------------------------ 拓扑排序

    def topological_order(self, tasks: list[str]) -> list[str]:
        """Kahn 拓扑排序 (稳定): 依赖先于被依赖者; 无依赖 → 输入原顺序。

        只取输入集合内的边; 图外任务/依赖忽略; 环 → 剩余节点按输入顺序
        追加 (失败安全, 保证全部任务都返回)。
        """
        order = [str(t) for t in (tasks or [])]
        if not order:
            return []
        node_set = set(order)
        indegree = {task: 0 for task in order}
        dependents: dict[str, list[str]] = {task: [] for task in order}
        for task, deps in self._deps.items():
            if task not in node_set:
                continue
            for dep in deps:
                if dep in node_set and dep != task:
                    dependents[dep].append(task)
                    indegree[task] += 1
        queue = [t for t in order if indegree[t] == 0]
        result: list[str] = []
        while queue:
            node = queue.pop(0)
            result.append(node)
            for nxt in dependents[node]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    queue.append(nxt)
        for task in order:
            if task not in result:
                result.append(task)
        return result
