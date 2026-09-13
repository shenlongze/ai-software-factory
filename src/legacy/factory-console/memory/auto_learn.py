"""factory-console/memory/auto_learn.py — AutoLearner (S10-070 G3 自动沉淀)。

生产链完成后自动沉淀经验 (零手动): 提取 → 存储 → 模式/Agent 画像 →
learning_trace 审计 — 复用 S10-067 LearningEngine 全循环, 薄封装
"自动学习" 语义 + should_learn 判定 + 失败安全。

- learn_from_workspace(workspace) → LearningResult:
    ExperienceExtractor.extract_all → ExperienceStore.add_all (幂等去重) →
    PatternLearner.learn/learn_agent → LearningTrace.record (审计)
  - 失败安全铁律: 学习任何故障 → 不抛, 返回空结果 (经验沉淀不中断生产链)
- should_learn(workspace) → bool:
    工作区存在可提取数据 (execution_records / repair_task /
    replanning_decisions / gap_analysis / validation_result 任一非空)
    — 供薄接点 (actions.execute_project 完成/失败后) 快速判定

边界:
- 复用 memory/ 现有组件 (extraction/experience_store/learning_engine/
  learning_trace) — 不重写; 纯标准库, 零新依赖
- LearningResult: 自含 dataclass (extracted/stored/patterns/profiles/
  trace/workspace + to_dict) — API/CLI/审计统一口径

设计: docs/sprint10/S10-067-memory-learning-design.md §3/§4/§6
     + docs/sprint10/S10-070-gap-design.md §三.3 (G3 Memory 自动沉淀)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from .experience_store import ExperienceStore
from .extraction import ExperienceExtractor
from .learning_engine import LearningEngine, PatternLearner
from .learning_trace import LearningTrace

__all__ = ["AutoLearner", "LearningResult"]

#: 可提取数据资产文件名 (与 ExperienceExtractor 口径一致 — 判定数据源)
_EXTRACTABLE_ASSETS: tuple[str, ...] = (
    "execution_records.json",      # workspace/exec/
    "repair_task.json",            # workspace/projects/<slug>/
    "replanning_decisions.json",   # workspace/projects/<slug>/
    "gap_analysis.json",           # workspace/projects/<slug>/ + teams/
    "validation_result.json",      # workspace/projects/<slug>/
)


@dataclass
class LearningResult:
    """自动学习结果 (S10-070 G3/验收 D): 提取→存储→模式→trace 全链路摘要。

    extracted_count: 提取条数; stored_count: 实际入库条数 (add_all 去重后);
    patterns: 学习到的模式 (dict); agent_profiles: Agent 画像 (dict);
    learned_items: 学习条目 (pattern:/agent: id 列表);
    trace: 最新 learning_trace 审计条目 (dict | None);
    workspace: 学习工作区 (str)。
    """

    extracted_count: int = 0
    stored_count: int = 0
    patterns: list[dict[str, Any]] = field(default_factory=list)
    agent_profiles: list[dict[str, Any]] = field(default_factory=list)
    learned_items: list[str] = field(default_factory=list)
    trace: Optional[dict[str, Any]] = None
    workspace: str = ""

    def to_dict(self) -> dict[str, Any]:
        """→ dict (API/CLI/审计统一口径)。"""
        return asdict(self)


class AutoLearner:
    """自动学习者 (G3): 生产链完成/失败后一键沉淀经验 (失败安全)。

    learn_from_workspace(workspace): 完整循环 (提取→存储→模式→trace),
      任何故障 → 空结果 (不抛, 不中断业务);
    should_learn(workspace): 有可提取数据 → True (薄接点快速判定)。
    """

    def __init__(
        self,
        engine: Optional[LearningEngine] = None,
        extractor: Optional[ExperienceExtractor] = None,
        store: Optional[ExperienceStore] = None,
        learner: Optional[PatternLearner] = None,
        trace: Optional[LearningTrace] = None,
    ) -> None:
        """组件注入 (测试/隔离); 缺省 → 按 workspace 每次装配 (存储对齐)。"""
        self._engine = engine
        self._extractor = extractor if extractor is not None else ExperienceExtractor()
        self._store = store
        self._learner = learner if learner is not None else PatternLearner()
        self._trace = trace

    # ------------------------------------------------------------ 学习

    def learn_from_workspace(
        self, workspace: Any = None
    ) -> LearningResult:
        """自动学习循环 (验收 D): 提取 → 存储 → 模式 + Agent 画像 → trace。

        复用 LearningEngine.run 完整循环 (含 LearningTrace 审计); 返回
        LearningResult (自含 trace 视图)。失败安全: 任何异常 → 空结果。
        """
        ws = Path(workspace) if workspace is not None else Path.home() / ".factory"
        try:
            if self._engine is not None:
                engine = self._engine
                result = engine.run(workspace)
            else:
                # store/trace 与 workspace 对齐装配 (学习数据源 = 存储数据源)
                engine = LearningEngine(
                    store=self._store if self._store is not None else ExperienceStore.from_workspace(ws),
                    extractor=self._extractor,
                    learner=self._learner,
                    trace=self._trace if self._trace is not None else LearningTrace(ws),
                    workspace=ws,
                )
                result = engine.run(ws)
            store = getattr(engine, "store", None)
            stored = len(store.records()) if store is not None else result.extracted_count
            trace_entries = (
                self._trace.records()
                if self._trace is not None
                else LearningTrace(ws).records()
            )
            return LearningResult(
                extracted_count=result.extracted_count,
                stored_count=stored,  # 学习后经验库总条数 (add_all 去重口径)
                patterns=list(result.patterns),
                agent_profiles=list(result.agent_profiles),
                learned_items=list(result.learned_items),
                trace=trace_entries[-1] if trace_entries else None,
                workspace=str(ws),
            )
        except Exception:  # noqa: BLE001 — 失败安全铁律: 学习故障不抛
            return LearningResult(workspace=str(ws))

    # ------------------------------------------------------------ 判定

    def should_learn(self, workspace: Any = None) -> bool:
        """是否有可提取数据 (验收 D): 任一数据资产存在且含非空记录。

        判定口径与 ExperienceExtractor.extract_all 一致 (同数据源清单);
        失败安全: workspace 缺失/损坏 → False (不抛)。
        """
        root = Path(workspace) if workspace is not None else Path.home() / ".factory"
        try:
            # ① 全局执行记录 (exec/execution_records.json)
            if self._asset_has_records(root / "exec" / "execution_records.json"):
                return True
            # ② 项目级资产 (projects/<slug>/*)
            projects_dir = root / "projects"
            if projects_dir.is_dir():
                for slug_dir in sorted(p for p in projects_dir.iterdir() if p.is_dir()):
                    for name in _EXTRACTABLE_ASSETS[1:]:
                        if self._asset_has_records(slug_dir / name):
                            return True
            # ③ 全局缺口资产 (teams/gap_analysis.json)
            if self._asset_has_records(root / "teams" / "gap_analysis.json"):
                return True
        except Exception:  # noqa: BLE001 — 失败安全: 判定故障 → False
            return False
        return False

    @staticmethod
    def _asset_has_records(path: Path) -> bool:
        """资产文件是否含非空记录 (缺失/损坏/空列表/空 dict → False)。"""
        if not Path(path).is_file():
            return False
        try:
            import json

            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — 损坏 → 无可提取
            return False
        if isinstance(data, list):
            return any(isinstance(item, dict) and item for item in data)
        if isinstance(data, dict):
            return bool(data)
        return False
