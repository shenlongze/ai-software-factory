"""factory-org/org/space.py — Project Space 目录 + Workspace Index (S10-009 Task 003)。

设计依据 (project-lifecycle.md §四 Project Space 三类目录 + §八 Migration 方案 A +
S10-009-plan.md Task 3):
- 目录信源: workspace/projects/{slug}/project.json 为 Project 记录信源 (生命周期主体)
- 骨架: project.json + idea/discovery/product/design/architecture/workflow-instance/
  source/artifacts/knowledge/runtime/logs/management (runtime/ 与 logs/ 平级 —
  设计 §四: runtime = AI Runtime Data, log = Audit Data, 互不嵌套)
- workspace index: workspace/projects.json 为纯缓存 (id→slug 映射; 目录扫描可重建;
  读取时目录信源优先 — 删除 index 不影响 load_project; 场景4: 删 index 后 rebuild 恢复)
- lazy migration (§八 方案 A): 旧项目仅在 org/projects.json (ProjectStore 集中式),
  无目录 → migrate_legacy/ensure_space 首次访问回填目录镜像 (幂等, 零风险)
- 隔离: 每项目独立目录; slug 不同互不影响; 禁止跨项目污染 (运行数据落各自
  {slug}/runtime/, 禁止 workspace/runtime/ 跨项目共享)

实现约束 (与 org/store.py 同模式):
- 原子写 = 临时文件 + os.replace (同目录同文件系统)
- 零 Core/console 依赖: 只 import org.projects (Project/ProjectStore)
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from .projects import Project, ProjectStore

#: Project Space 骨架目录 (project-lifecycle.md §四; runtime/ 与 logs/ 平级)。
SPACE_DIRS: tuple[str, ...] = (
    "idea",
    "discovery",
    "product",
    "design",
    "architecture",
    "workflow-instance",
    "source",
    "artifacts",
    "knowledge",
    "runtime",
    "logs",
    "management",
)

_PROJECT_JSON = "project.json"


def _slugify(text: str) -> str:
    """宽松 slug 化 (旧项目 name → 目录名兜底; 非字母数字 → '-', 小写)。"""
    slug = re.sub(r"[^a-z0-9]+", "-", str(text).strip().lower()).strip("-")
    return slug


class ProjectSpaceStore:
    """Project Space 目录 + Workspace Index 门面 (org 层新模块, 不动 console/Core)。

    布局:
        <root>/workspace/projects/{slug}/project.json   # 信源 (Project 记录)
        <root>/workspace/projects/{slug}/{骨架目录}/     # 产品资产/运行时/审计/管理
        <root>/workspace/projects.json                  # index 缓存 (id→slug, 可重建)

    语义:
    - ensure_space: 骨架幂等 (已存在不重建/不覆盖既有内容) + project.json 镜像回填
    - save_project/load_project: {slug}/project.json 信源读写 (全字段 JSON 序列化)
    - index: 纯缓存 — list_index 读缓存, rebuild_index 目录扫描重建,
      get_slug 缓存缺失/未命中自愈重建; 读取路径 (load_project) 不依赖缓存
    - migrate_legacy: 旧项目 (仅 org/projects.json, 无目录) 回填目录镜像, 幂等
    """

    def __init__(self, root: str | Path):
        self._root = Path(root)
        self._workspace = self._root / "workspace"
        self._projects_dir = self._workspace / "projects"
        self._index_path = self._workspace / "projects.json"

    # ------------------------------------------------------------------ 布局
    @property
    def root(self) -> Path:
        return self._root

    @property
    def workspace(self) -> Path:
        return self._workspace

    @property
    def projects_dir(self) -> Path:
        return self._projects_dir

    @property
    def index_path(self) -> Path:
        return self._index_path

    def space_dir(self, slug: str) -> Path:
        """项目空间目录 workspace/projects/{slug}/。"""
        return self._projects_dir / slug

    def has_space(self, slug: str) -> bool:
        """项目空间是否已存在 (骨架已建)。"""
        return self.space_dir(slug).is_dir()

    def rename_space(self, old_slug: str, new_slug: str) -> Path:
        """原子 rename 项目空间目录 (S10-009 Task 5: os.replace — 同文件系统原子)。

        整目录 (project.json + 全部骨架子目录与资产) 一并移动, 内容零丢失;
        os.replace 对目录执行 rename(2) — 目标不存在时原子; 目标已存在 →
        OSError (冲突在 service 层事务预检, 本原语只做原子 rename, 不兜业务)。
        旧目录不存在 → FileNotFoundError (调用方事务回滚兜底)。
        """
        old_dir = self.space_dir(old_slug)
        new_dir = self.space_dir(new_slug)
        os.replace(old_dir, new_dir)
        return new_dir

    # ---------------------------------------------------------- 骨架 / 信源
    def _effective_slug(self, project: Project) -> str:
        """目录名: project.slug 优先; 旧项目 (slug 空) → name slug 化兜底; 再兜底 id。"""
        if project.slug:
            return project.slug
        derived = _slugify(project.name)
        return derived if derived else project.id

    def _ensure_dirs(self, slug: str) -> Path:
        """骨架幂等创建: 目录已存在不重复创建/不报错 (mkdir exist_ok)。"""
        space_dir = self.space_dir(slug)
        space_dir.mkdir(parents=True, exist_ok=True)
        for name in SPACE_DIRS:
            (space_dir / name).mkdir(exist_ok=True)
        return space_dir

    @staticmethod
    def _atomic_write(path: Path, data: dict[str, Any]) -> None:
        """原子写 JSON: 临时文件 + os.replace (同 store.py 模式)。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.parent / f".{path.name}.{os.getpid()}.tmp"
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, path)

    def ensure_space(self, project: Project) -> Path:
        """懒迁移原语: 骨架 + project.json 镜像 (幂等 — 已存在不重建/不覆盖)。

        目录已存在且 project.json 已写 → 原样返回 (既有内容保留, 不重复创建);
        project.json 缺失 → 回填镜像 (旧项目首次访问回填, 零风险)。
        """
        slug = self._effective_slug(project)
        space_dir = self._ensure_dirs(slug)
        project_json = space_dir / _PROJECT_JSON
        if not project_json.exists():
            self._atomic_write(project_json, project.to_dict())
        return space_dir

    def save_project(self, project: Project) -> Path:
        """写 {slug}/project.json (信源, 全字段 JSON 序列化; 骨架幂等保障)。"""
        slug = self._effective_slug(project)
        space_dir = self._ensure_dirs(slug)
        self._atomic_write(space_dir / _PROJECT_JSON, project.to_dict())
        return space_dir

    def load_project(self, slug: str) -> Project | None:
        """读 {slug}/project.json (目录信源优先 — 不依赖 index 缓存)。"""
        project_json = self.space_dir(slug) / _PROJECT_JSON
        if not project_json.is_file():
            return None
        try:
            data = json.loads(project_json.read_text(encoding="utf-8"))
            return Project.model_validate(data)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"corrupt project space: {project_json}: {exc}") from exc

    # -------------------------------------------------------- 空间内文件原语
    # (S10-009 Task 4 — Draft/Discovery 持久化: idea/conversation.json +
    # idea.md + discovery/conversation.json + product-definition.md 均由
    # console service 经这些原语读写, 空间布局知识留在 org 层)

    def read_json(self, slug: str, relpath: str) -> dict[str, Any] | None:
        """读空间内 JSON 文件; 缺失/损坏/非 dict → None (失败安全, 调用方按空处理)。"""
        path = self.space_dir(slug) / relpath
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    def write_json(self, slug: str, relpath: str, data: dict[str, Any]) -> Path:
        """写空间内 JSON 文件 (原子写 — 同 _atomic_write 模式)。"""
        path = self.space_dir(slug) / relpath
        self._atomic_write(path, data)
        return path

    def write_text(self, slug: str, relpath: str, content: str) -> Path:
        """写空间内文本文件 (原子写 — 临时文件 + os.replace; 骨架幂等保障目录)。"""
        path = self.space_dir(slug) / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.parent / f".{path.name}.{os.getpid()}.tmp"
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)
        return path

    # ------------------------------------------------------------ index 缓存
    def list_index(self) -> dict[str, str]:
        """读 index 缓存 (id→slug); 缺失/损坏 → {} (缓存语义: 可重建, 不致命)。"""
        if not self._index_path.is_file():
            return {}
        try:
            data = json.loads(self._index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        projects = data.get("projects") if isinstance(data, dict) else None
        if not isinstance(projects, dict):
            return {}
        return {str(k): str(v) for k, v in projects.items()}

    def rebuild_index(self) -> dict[str, str]:
        """目录扫描重建 index (场景4: 删除 index 后恢复); 返回并落盘 id→slug。"""
        index: dict[str, str] = {}
        if self._projects_dir.is_dir():
            for entry in sorted(self._projects_dir.iterdir()):
                if not entry.is_dir():
                    continue
                project_json = entry / _PROJECT_JSON
                if not project_json.is_file():
                    continue  # 非项目目录/未初始化 → 跳过
                try:
                    data = json.loads(project_json.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    continue
                project_id = data.get("id") if isinstance(data, dict) else None
                if isinstance(project_id, str) and project_id:
                    index[project_id] = entry.name
        self._atomic_write(self._index_path, {"projects": dict(sorted(index.items()))})
        return dict(index)

    def get_slug(self, project_id: str) -> str | None:
        """index 查询 id→slug; 缓存缺失/未命中 → 重建后重查 (自愈缓存)。"""
        index = self.list_index()
        if project_id in index:
            return index[project_id]
        return self.rebuild_index().get(project_id)

    # --------------------------------------------------------- lazy migration
    def migrate_legacy(self, store: ProjectStore) -> int:
        """旧项目 (仅 org/projects.json, 无目录) 回填目录镜像; 返回迁移数 (幂等)。

        已存在目录 → 跳过 (二次调用返回 0); slug 缺省旧项目 → name slug 化目录名。
        """
        migrated = 0
        for project in store.list_projects():
            slug = self._effective_slug(project)
            if self.has_space(slug):
                continue
            self.ensure_space(project)
            migrated += 1
        return migrated
