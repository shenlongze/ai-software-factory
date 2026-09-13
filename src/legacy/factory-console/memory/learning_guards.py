"""factory-console/memory/learning_guards.py — K-3 M4-2 学习护栏 (S10-119, 最高优先级)。

护栏 = 让 Agent 变强且可控的第一道闸: 任何学习路径 (入库/引用/画像/快照)
都挂在 LearningGuards 之下, 可开关、可回退、有预算上限。

- enabled()             总开关 (缺省 True; 配置可关 — workspace/memory/
                        learning_state.json {"enabled": false} → 学习/引用零行为变化)
- sample_credible(n)    样本可信度: n >= MIN_SAMPLES=3 才"主导" (低样本降权/不主导)
- sample_quality_ok(q)  sample 质量: quality_score >= MIN_QUALITY=0.5 才写入
                        (低质量样本不写 — 诚实, 不污染经验库)
- budget_ok(usage)      学习存储预算: 经验条数/快照数超上限 → False + 告警
                        (阻断学习写入/快照, 可解释 last_alert)
- snapshot(workspace)   学习状态快照 (experience_store/agent_profiles/
                        decision_memory/learning_trace + 开关状态) → 可一键回退
- rollback(snapshot)    一键回退 (覆盖当前学习状态文件 → 还原快照时点)

设计: docs/sprint10/S10-119-k3-learning-loop-plan.md §1.1 (M4-2, 最高优先级)
边界:
- 纯标准库 (json/shutil/datetime/pathlib), 零第三方依赖
- 失败安全铁律: 配置损坏/缺失 → 缺省 (True 开启), 不因护栏自身故障阻断业务
- 学习导致的画像/经验快照 → 可一键回退 (snapshot/rollback)
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

#: 学习总开关缺省值 (True = 默认开启; 关闭 → 学习/引用零行为变化)
LEARNING_ENABLED_DEFAULT = True

#: 样本可信度阈值 (样本数 < 阈值 → 不主导/降权 — 少量样本不宣称高置信)
MIN_SAMPLES = 3

#: 样本质量阈值 (quality_score < 阈值 → 低质量样本不写入经验库)
MIN_QUALITY = 0.5

#: 学习存储预算缺省值 (超上限 → budget_ok False + 告警, 阻断学习写入/快照)
LEARNING_BUDGET_DEFAULTS: dict[str, int] = {
    "max_experiences": 1000,   # 经验库最大条数
    "max_snapshots": 20,       # 学习状态快照最大份数
}

#: 学习状态配置文件 (总开关/预算可配置 — workspace/memory/learning_state.json)
LEARNING_STATE_FILE_NAME = "learning_state.json"

#: 学习状态快照目录 (workspace/.factory_learning_snapshots/<ts>/)
LEARNING_SNAPSHOT_DIR_NAME = ".factory_learning_snapshots"

#: 学习状态资产 (snapshot/rollback 覆盖范围 — 画像/经验/决策记忆/审计轨迹)
LEARNING_STATE_FILES: tuple[str, ...] = (
    "experience_store.json",
    "agent_profiles.json",
    "decision_memory.json",
    "learning_trace.json",
    LEARNING_STATE_FILE_NAME,
)


def _now_iso() -> str:
    """UTC 当前时间 ISO 格式 (快照时间戳)。"""
    return datetime.now(timezone.utc).isoformat()


def learning_state_file(workspace: Any = None) -> Path:
    """workspace/memory/learning_state.json (缺省 ~/.factory/memory/)。"""
    from .experience_store import memory_dir

    return memory_dir(workspace) / LEARNING_STATE_FILE_NAME


def learning_snapshot_dir(workspace: Any = None) -> Path:
    """workspace/.factory_learning_snapshots (快照根目录)。"""
    root = Path(workspace) if workspace is not None else Path.home() / ".factory"
    return root / LEARNING_SNAPSHOT_DIR_NAME


def load_learning_config(workspace: Any = None) -> dict[str, Any]:
    """读学习配置 (失败安全: 缺失/损坏 → 缺省开启, 不抛)。"""
    path = learning_state_file(workspace)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:  # noqa: BLE001 — 失败安全: 损坏配置 → 缺省
        pass
    return {}


def save_learning_config(config: dict[str, Any], workspace: Any = None) -> Path:
    """写学习配置 (失败安全: 落盘异常不抛, 返回路径)。"""
    path = learning_state_file(workspace)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(config, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001 — 失败安全
        pass
    return path


class LearningGuards:
    """学习护栏 (M4-2, 最高优先级): 总开关/样本可信度/质量/预算/快照回退。

    所有学习路径先过 enabled() (总开关) — 关闭 → 零行为变化 (向后兼容断言);
    写入路径过 sample_quality_ok (低质量不写); 引用路径过 sample_credible
    (低样本不主导); 存储路径过 budget_ok (超预算阻断+告警); 学习状态
    snapshot/rollback 一键回退。
    """

    def __init__(
        self,
        *,
        enabled: Optional[bool] = None,
        min_samples: Optional[int] = None,
        min_quality: Optional[float] = None,
        budget: Optional[dict[str, int]] = None,
        workspace: Any = None,
    ) -> None:
        """显式参数优先; 缺省 → 常量 + workspace 配置 (workspace 缺省 ~/.factory)。"""
        self.workspace = Path(workspace) if workspace is not None else Path.home() / ".factory"
        config = load_learning_config(self.workspace)
        self._enabled_override = enabled
        self._enabled = (
            bool(enabled)
            if enabled is not None
            else bool(config.get("enabled", LEARNING_ENABLED_DEFAULT))
        )
        self.min_samples = (
            int(min_samples) if min_samples is not None else int(
                config.get("min_samples", MIN_SAMPLES)
            )
        )
        self.min_quality = (
            float(min_quality)
            if min_quality is not None
            else float(config.get("min_quality", MIN_QUALITY))
        )
        raw_budget = budget if budget is not None else config.get("budget") or {}
        self.budget: dict[str, int] = {
            **LEARNING_BUDGET_DEFAULTS,
            **{k: int(v) for k, v in raw_budget.items() if isinstance(raw_budget, dict)},
        }
        #: 最近一次护栏告警 (可解释 — budget_ok False 时读取)
        self.last_alert: str = ""
        #: 最近一次 budget_ok 判定详情
        self.last_budget_check: dict[str, Any] = {}

    # ------------------------------------------------------------ 总开关

    def enabled(self) -> bool:
        """总开关 (缺省 True; 配置可关 — learning_state.json {"enabled": false})。

        关闭 → 学习/引用/画像刷新全跳过 (零行为变化, 向后兼容断言)。
        """
        return self._enabled

    # ------------------------------------------------------------ 样本可信度

    def sample_credible(self, n: int) -> bool:
        """样本可信度: n >= min_samples (缺省 3) 才"主导"。

        少量样本 (n < 阈值) → False → 引用路径降权/不主导 (少量样本不宣称
        高置信 — 同 PatternLearner confidence 语义)。
        """
        try:
            count = int(n)
        except (TypeError, ValueError):  # noqa: BLE001 — 非法 n → 不主导 (保守)
            return False
        return count >= self.min_samples

    # ------------------------------------------------------------ 样本质量

    def sample_quality_ok(self, q: Any) -> bool:
        """样本质量闸: quality_score >= min_quality (缺省 0.5) 才写入经验库。

        q 缺失/非法 (None/非数值) → False (诚实: 无质量分不写, 不臆造可信度)。
        """
        try:
            value = float(q)
        except (TypeError, ValueError):  # noqa: BLE001 — 无分/损坏 → 不写
            return False
        if value != value:  # NaN
            return False
        return value >= self.min_quality

    # ------------------------------------------------------------ 存储预算

    def budget_ok(self, usage: Any) -> bool:
        """学习存储预算: 经验条数/快照数超上限 → False + 告警 (阻断写入/快照)。

        usage: {"experiences": N, "snapshots": M} (缺失维度 → 0, 不判超)。
        失败安全: 非法 usage → 按缺省判定 (超限维 → False + 告警, 不抛)。
        """
        if not isinstance(usage, dict):
            usage = {}
        experiences = int(usage.get("experiences") or 0)
        snapshots = int(usage.get("snapshots") or 0)
        max_exp = int(self.budget.get("max_experiences") or 0)
        max_snap = int(self.budget.get("max_snapshots") or 0)
        over_exp = max_exp > 0 and experiences > max_exp
        over_snap = max_snap > 0 and snapshots > max_snap
        self.last_budget_check = {
            "experiences": experiences,
            "snapshots": snapshots,
            "max_experiences": max_exp,
            "max_snapshots": max_snap,
            "over_experiences": over_exp,
            "over_snapshots": over_snap,
        }
        if over_exp or over_snap:
            parts = []
            if over_exp:
                parts.append(f"经验条数 {experiences} > 上限 {max_exp}")
            if over_snap:
                parts.append(f"快照数 {snapshots} > 上限 {max_snap}")
            self.last_alert = (
                "学习预算超限: " + ", ".join(parts) + " — 阻断学习写入/快照"
            )
            return False
        self.last_alert = ""
        return True

    # ------------------------------------------------------------ 快照/回退

    def _usage_from_workspace(self, workspace: Any = None) -> dict[str, int]:
        """当前工作区学习用量 (经验条数 + 快照份数; 失败安全 → 0)。"""
        ws = Path(workspace) if workspace is not None else self.workspace
        experiences = 0
        try:
            from .experience_store import experience_store_file

            path = experience_store_file(ws)
            if path.is_file():
                data = json.loads(path.read_text(encoding="utf-8"))
                experiences = len(data) if isinstance(data, list) else 0
        except Exception:  # noqa: BLE001 — 失败安全
            experiences = 0
        snapshots = 0
        snap_root = learning_snapshot_dir(ws)
        try:
            snapshots = (
                len([p for p in snap_root.iterdir() if p.is_dir()])
                if snap_root.is_dir()
                else 0
            )
        except Exception:  # noqa: BLE001 — 失败安全
            snapshots = 0
        return {"experiences": experiences, "snapshots": snapshots}

    def snapshot(self, workspace: Any = None) -> Path:
        """学习状态快照 (画像/经验/决策记忆/轨迹 + 开关配置) → 快照目录。

        - 目录: workspace/.factory_learning_snapshots/<ts>/
        - 复制 memory/ 下 LEARNING_STATE_FILES 全部学习资产 (缺失文件跳过)
        - 先过 budget_ok (快照数超上限 → 拒绝快照, 返回当前快照目录 — 不静默)
        返回快照目录路径 (失败安全: 复制异常 → 已建目录, 不抛)。
        """
        ws = Path(workspace) if workspace is not None else self.workspace
        usage = self._usage_from_workspace(ws)
        if not self.budget_ok(usage):
            # 超预算 → 不新增快照 (阻断) + 告警 (last_alert 已记录)
            return learning_snapshot_dir(ws)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        target = learning_snapshot_dir(ws) / stamp
        try:
            target.mkdir(parents=True, exist_ok=True)
            mem_dir = ws / "memory"
            for name in LEARNING_STATE_FILES:
                src = mem_dir / name
                if src.is_file():
                    shutil.copy2(src, target / name)
        except Exception:  # noqa: BLE001 — 失败安全: 快照部分成功不抛
            pass
        return target

    def rollback(self, snapshot_path: Any) -> None:
        """一键回退: 快照目录 → 覆盖当前学习状态文件 (还原快照时点)。

        - 快照目录缺失/无学习资产 → 静默跳过 (失败安全, 不抛)
        - 覆盖范围 = LEARNING_STATE_FILES (画像/经验/决策记忆/轨迹/开关)
        """
        snap = Path(snapshot_path) if snapshot_path is not None else None
        if snap is None or not snap.is_dir():
            return
        mem_dir = snap.parent.parent / "memory"
        try:
            mem_dir.mkdir(parents=True, exist_ok=True)
            for name in LEARNING_STATE_FILES:
                src = snap / name
                if src.is_file():
                    shutil.copy2(src, mem_dir / name)
        except Exception:  # noqa: BLE001 — 失败安全: 回退部分成功不抛
            pass


__all__ = [
    "LEARNING_BUDGET_DEFAULTS",
    "LEARNING_ENABLED_DEFAULT",
    "LEARNING_SNAPSHOT_DIR_NAME",
    "LEARNING_STATE_FILE_NAME",
    "LEARNING_STATE_FILES",
    "MIN_QUALITY",
    "MIN_SAMPLES",
    "LearningGuards",
    "learning_snapshot_dir",
    "learning_state_file",
    "load_learning_config",
    "save_learning_config",
]
