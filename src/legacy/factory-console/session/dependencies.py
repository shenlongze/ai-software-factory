"""factory-console/session/dependencies.py — TaskDependencyGraph (S10-056 批次 A)。

任务依赖 DAG 数据结构 (设计 §2.4): task → [depends_on] 有向边,
落盘 task_dependencies.json (~/.factory/teams/)。保留顺序执行兼容
(dependencies 为空 → 原顺序); 只做数据结构 + 基础拓扑排序 (Kahn),
不实现复杂调度 (边界 §7)。

组件:
- TaskDependencyGraph — add_dependency/get/has/to_dict/from_dict/load/save +
  topological_order(tasks) (无环稳定拓扑; 空依赖 → 输入原顺序; 环 → 失败安全
  剩余节点按原顺序追加)
- S10-060 (Autonomous Replanning) 扩展 — 动态 DAG 修改 (设计 §P2):
  add_task/remove_task/modify_task + add_dependency (带环检测, 成环 → 拒绝并
  返回 False, reason="cyclic dependency") + remove_dependency +
  recalculate_order (topological_order 别名) + cycle_detect (DFS 可达性)

设计: docs/sprint10/S10-056-team-design.md §2.4 / §3;
docs/sprint10/S10-060-replanning-design.md §3 (P2)
边界:
- 纯标准库 (json/pathlib), 零模块依赖; 失败安全 (缺失/损坏 → 空图, 永不抛)
- 图只在输入任务集合内取边 (图外任务/依赖不影响拓扑结果)
- 向后兼容: add_dependency 旧无返回值 → 现返回 bool (False = 环拒绝);
  既有无返回值调用不受影响
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

    def add_dependency(self, task: str, depends_on: str) -> bool:
        """task 依赖 depends_on (depends_on 先执行); 同依赖重复添加 → 幂等。

        S10-060 (设计 §P2 Cycle Protection): 添加前检测是否形成环 (DFS 可达性 —
        T1→T2→T3→T1 这类循环) → 成环 → 拒绝 (不添加) 并返回 False;
        添加成功 → True。向后兼容: 旧无返回值调用不受影响。
        """
        key = str(task)
        dep = str(depends_on)
        if key == dep:
            return False  # 自依赖 = 平凡环
        if self.cycle_detect(key, dep):
            return False  # 形成环 → 拒绝 (reason="cyclic dependency")
        deps = self._deps.setdefault(key, [])
        if dep not in deps:
            deps.append(dep)
        return True

    def add_task(self, task: str, depends_on: Optional[list[str]] = None) -> bool:
        """注册任务节点 (S10-060 动态 DAG): 空依赖注册; 已存在 → False (幂等)。

        可选 depends_on 初始依赖 (带环检测: 任一边成环 → 不注册, 返回 False)。
        """
        key = str(task)
        if key in self._deps:
            return False
        deps = [str(d) for d in (depends_on or []) if not isinstance(d, dict)]
        for dep in deps:
            if self.cycle_detect(key, dep):
                return False  # 初始依赖成环 → 拒绝注册 (cyclic dependency)
        self._deps[key] = deps
        return True

    def remove_task(self, task: str) -> bool:
        """移除任务节点 (S10-060 动态 DAG): 节点条目 + 其它任务的依赖引用一并清理。

        任务不在图中 → False (无操作); 移除后依赖它的任务不再引用它
        (依赖不成立由 ReplanningEngine BLOCK_TASK 消费)。
        """
        key = str(task)
        if key not in self._deps and not any(
            key in deps for deps in self._deps.values()
        ):
            return False
        self._deps.pop(key, None)
        for deps in self._deps.values():
            if key in deps:
                deps.remove(key)
        return True

    def modify_task(self, task: str, new_name: Optional[str] = None) -> bool:
        """重命名任务节点 (S10-060 动态 DAG): 节点条目 + 引用同步更新。

        无效参数 (new_name 空/相同/不存在任务/目标已存在) → False (拒绝, 不合并)。
        """
        key = str(task)
        if new_name is None or not str(new_name).strip():
            return False
        new_key = str(new_name)
        if new_key == key:
            return False
        if key not in self._deps and not any(
            key in deps for deps in self._deps.values()
        ):
            return False
        if new_key in self._deps:
            return False  # 目标节点已存在 → 拒绝 (避免隐式合并语义)
        deps = self._deps.pop(key, [])
        self._deps[new_key] = deps
        for d in self._deps.values():
            if key in d:
                d[d.index(key)] = new_key
        return True

    def remove_dependency(self, task: str, depends_on: str) -> bool:
        """移除 task 对 depends_on 的依赖 (S10-060 动态 DAG); 不存在 → False。"""
        key = str(task)
        dep = str(depends_on)
        deps = self._deps.get(key)
        if not deps or dep not in deps:
            return False
        deps.remove(dep)
        return True

    def cycle_detect(self, task: str, depends_on: str) -> bool:
        """添加 task→depends_on 依赖 (新边 depends_on → task) 是否形成环 (S10-060)。

        DFS 可达性: 若图中已存在路径 task → ... → depends_on (沿依赖边方向
        被依赖 → 依赖者), 则新边 closes the loop → True (成环)。
        自依赖 (task == depends_on) → True (平凡环)。
        """
        key = str(task)
        dep = str(depends_on)
        if key == dep:
            return True
        return self._reachable(key, dep)

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

    def recalculate_order(self, tasks: list[str]) -> list[str]:
        """重算执行顺序 (S10-060 动态 DAG — topological_order 别名/增强)。

        DAG 变更 (add/remove/modify/add_dependency/remove_dependency) 后调用,
        重排执行队列; 环 → 失败安全追加 (同 topological_order)。
        """
        return self.topological_order(tasks)

    def _reachable(self, start: str, target: str) -> bool:
        """DFS 可达性: start 是否可达 target (沿依赖边方向: 被依赖 → 依赖者)。

        cycle_detect 依赖: 新边 depends_on → task 成环 ⇔ task 可达 depends_on。
        """
        stack = [start]
        visited: set[str] = set()
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            # 后继 = 依赖 node 的任务 (node 是其 depends_on)
            for task, deps in self._deps.items():
                if node in deps and task not in visited:
                    if task == target:
                        return True
                    stack.append(task)
        return False

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
