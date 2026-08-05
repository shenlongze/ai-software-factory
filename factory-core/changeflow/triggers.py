"""changeflow/triggers.py — ChangeTriggerRegistry: 触发器注册/查询/持久化
(JSON 文件, Phase 6E, ADR-0020)。

设计依据:
- phase6e-status.md: ChangeTrigger 注册/查询 (JSON 持久化 .factory/changeflow/
  triggers.json)。
- 风格同 change.service.ChangeStore / git.service.GitChangeStore: JSON 列表文件
  原子写 (tmp + os.replace); 损坏读 → [] (失败安全: 触发器是驱动配置, 损坏
  不拖垮工厂 — 评估按无触发器 SKIP 处理, 与 ADR-0019 快照语义一致)。
- 缺省路径 ~/.factory/changeflow/triggers.json (与 CLI DEFAULT_ROOT 一致,
  不依赖 cwd — backend-developer skill store 路径陷阱); 调用方显式传
  <root>/changeflow。
- 事件: register/remove 写路径经注入 logger 发 change.trigger.created /
  change.trigger.viewed (读命令在 CLI 层发, 同既有边界); logger 可缺省。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from events.models import Event

from .events import record_change_trigger_created
from .models import ChangeTrigger


class ChangeTriggerRegistryError(Exception):
    """ChangeTriggerRegistry 基础异常。"""


class ChangeTriggerExistsError(ChangeTriggerRegistryError):
    """触发器 id 已存在 (register 冲突)。"""


class ChangeTriggerNotFoundError(ChangeTriggerRegistryError):
    """触发器 id 不存在 (remove/get)。"""


class ChangeTriggerRegistry:
    """ChangeTrigger 注册表: JSON 列表文件持久化 + 事件 (change.trigger.created)。

    path 接受目录 (→ <dir>/triggers.json) 或文件路径; 缺省 =
    ~/.factory/changeflow/triggers.json。
    """

    filename = "triggers.json"

    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            self.path = Path.home() / ".factory" / "changeflow" / self.filename
        else:
            p = Path(path)
            self.path = p / self.filename if p.suffix != ".json" else p

    # ------------------------------------------------------------------ 读写

    def load(self) -> list[ChangeTrigger]:
        """全部触发器 (按 id 排序); 文件缺失 → [], 损坏 → [] (失败安全)。"""
        if not self.path.is_file():
            return []
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return []
        if not isinstance(data, list):
            return []
        triggers: list[ChangeTrigger] = []
        for item in data:
            if isinstance(item, dict):
                try:
                    triggers.append(ChangeTrigger.model_validate(item))
                except (ValueError, TypeError):
                    continue  # 单条损坏跳过, 不拖垮整库 (失败安全)
        return sorted(triggers, key=lambda t: t.id)

    def _write_all(self, triggers: list[ChangeTrigger]) -> None:
        """原子落盘 (tmp + os.replace)。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                [t.to_dict() for t in triggers],
                f, ensure_ascii=False, indent=2,
            )
        os.replace(tmp, self.path)

    # ------------------------------------------------------------------ 写路径

    def register(
        self, trigger: ChangeTrigger, *, logger: Any = None,
    ) -> tuple[ChangeTrigger, Event | None]:
        """注册触发器; id 冲突抛 ChangeTriggerExistsError; 发 change.trigger.created。

        存储先落地、事件后发 (与 AgentRegistry 模式一致, ADR-0004 决策 2)。
        """
        if self.get(trigger.id) is not None:
            raise ChangeTriggerExistsError(f"change trigger already exists: {trigger.id}")
        triggers = self.load()
        triggers.append(trigger)
        self._write_all(triggers)
        ev = (
            record_change_trigger_created(logger, trigger=trigger)
            if logger is not None else None
        )
        return trigger, ev

    def remove(
        self, trigger_id: str, *, logger: Any = None,
    ) -> tuple[ChangeTrigger, Event | None]:
        """移除触发器; 不存在抛 ChangeTriggerNotFoundError。

        事件: 读路径约定 — remove 为写路径, 但任务事件集 (ADR-0020) 只定义
        created/viewed/evaluated/workflow.*; 移除是配置管理操作, 复用 viewed
        审计不准确 — 故本方法不发事件 (KISS: 移除后列表查询即反映, 配置操作
        由 CLI 层经 triggers list 审计追踪)。返回 (trigger, None) 保持元组签名。
        """
        triggers = self.load()
        for i, t in enumerate(triggers):
            if t.id == trigger_id:
                removed = triggers.pop(i)
                self._write_all(triggers)
                return removed, None
        raise ChangeTriggerNotFoundError(f"change trigger not found: {trigger_id}")

    # ------------------------------------------------------------------ 查询

    def get(self, trigger_id: str) -> ChangeTrigger | None:
        """按 id 取触发器; 不存在返回 None。"""
        for t in self.load():
            if t.id == trigger_id:
                return t
        return None

    def list(self) -> list[ChangeTrigger]:
        """全部触发器 (按 id 排序)。"""
        return self.load()

    def matching(self, *, project_id: str, task_type: str) -> list[ChangeTrigger]:
        """命中任务的触发器 (项目/类型维度; 无匹配 → 空 — 评估 SKIP)。"""
        return [
            t for t in self.load()
            if t.matches(project_id=project_id, task_type=task_type)
        ]

    def ids(self) -> list[str]:
        """现有触发器 id 列表 (排序)。"""
        return [t.id for t in self.load()]
