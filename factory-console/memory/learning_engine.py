"""factory-console/memory/learning_engine.py — PatternLearner + LearningEngine (S10-067 G4/G6)。

模式学习 + Agent 画像 (G4/G6):
- PatternLearner.learn(records)      → 成功/失败模式 (topic 分组 + success_rate +
  confidence, 例: database_pattern "类似项目数据库设计不足 → 60% 返工")
- PatternLearner.learn_agent(records) → Agent 能力画像 (total_tasks/
  success_count/success_rate/common_problems/best_domains)
- LearningEngine.run(workspace)      → 完整学习循环: 提取 → 存储 → 学习 →
  learning_trace 审计 → LearningResult

设计: docs/sprint10/S10-067-memory-learning-design.md §4
边界:
- 纯标准库 (re/dataclasses), 零模块依赖; 失败安全 (空记录 → 空结果)
- 确定性规则学习 (关键词信号 → topic), 不调 LLM (GAP 五不该)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

from .experience import (
    DEBUG_EXPERIENCE,
    FAILURE_PATTERN,
    PLANNING_EXPERIENCE,
    SUCCESS_PATTERN,
    ExperienceRecord,
)
from .experience_store import ExperienceStore, experience_store_file
from .extraction import ExperienceExtractor
from .learning_trace import LearningTrace

#: 模式主题信号表 (确定性规则 — 关键词命中 → topic; 顺序 = 优先级)
#: 每项: (topic, (关键词...)) — 匹配 problem/result/context/task 文本
TOPIC_SIGNALS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("database", ("数据库", "database", "db", "持久化", "persistence", "存储", "落盘")),
    ("api", ("api", "接口", "endpoint", "路由")),
    ("test", ("测试", "test", "验证", "validation", "pytest", "用例")),
    ("auth", ("登录", "auth", "认证", "login", "权限", "会话")),
    ("ui", ("界面", "ui", "前端", "页面", "flutter", "component", "组件")),
    ("deployment", ("部署", "deploy", "上线", "环境", "配置", "config", "密钥", "key")),
    ("provider", ("provider", "llm", "anthropic", "openai", "deepseek", "api key")),
    ("planning", ("计划", "plan", "缺口", "gap", "重规划", "replan")),
    ("integration", ("集成", "integration", "联调", "依赖")),
)

#: 兜底主题 (无信号命中)
DEFAULT_TOPIC = "other"

#: 模式名映射 (中文可读名)
_TOPIC_NAMES: dict[str, str] = {
    "database": "数据库设计",
    "api": "API 接口",
    "test": "测试验证",
    "auth": "登录认证",
    "ui": "UI 界面",
    "deployment": "部署配置",
    "provider": "LLM Provider",
    "planning": "规划缺口",
    "integration": "集成联调",
    DEFAULT_TOPIC: "其他",
}

#: confidence 上限 (信号强度封顶 — 少量样本不宣称高置信)
MAX_CONFIDENCE = 0.95
#: 基础置信 (首条样本)
BASE_CONFIDENCE = 0.4
#: 每增 1 条样本的置信增量
CONFIDENCE_STEP = 0.1


def _topic_of(record: ExperienceRecord) -> str:
    """记录 → 主题 (problem/result/context/task 信号命中; 无 → other)。"""
    text = " ".join(
        [
            record.problem,
            record.result,
            record.context,
            record.task,
            record.action,
        ]
    ).lower()
    for topic, signals in TOPIC_SIGNALS:
        for signal in signals:
            if signal in text:
                return topic
    return DEFAULT_TOPIC


@dataclass
class Pattern:
    """学习到的模式 (G4): topic 分组 + 统计 + confidence。"""

    pattern_id: str
    name: str
    description: str
    success_rate: float
    count: int
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentProfile:
    """Agent 能力画像 (G6): 任务量/成功率/常见问题/最佳领域。"""

    agent_id: str
    role: str
    total_tasks: int
    success_count: int
    success_rate: float
    common_problems: list[str]
    best_domains: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LearningResult:
    """学习循环结果 (G4/G6 — API/CLI 响应口径)。"""

    extracted_count: int
    patterns: list[dict[str, Any]]
    agent_profiles: list[dict[str, Any]]
    learned_items: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PatternLearner:
    """模式学习器 (G4/G6): 经验 → 模式 / Agent 画像 (确定性规则)。"""

    # ------------------------------------------------------------ 模式

    def learn(self, records: list[ExperienceRecord]) -> list[Pattern]:
        """经验 → 成功/失败模式 (topic 分组 + success_rate + confidence)。

        每组: count (样本量), success_rate (成功占比), confidence =
        min(0.95, 0.4 + 0.1 * count) — 样本越多越可信 (封顶 0.95)。
        排序: confidence 降序 → count 降序 (确定性)。
        """
        groups: dict[str, list[ExperienceRecord]] = {}
        for record in records or []:
            groups.setdefault(_topic_of(record), []).append(record)
        patterns: list[Pattern] = []
        for topic, recs in groups.items():
            count = len(recs)
            success_count = sum(1 for r in recs if r.success)
            success_rate = round(success_count / count, 4) if count else 0.0
            confidence = round(
                min(MAX_CONFIDENCE, BASE_CONFIDENCE + CONFIDENCE_STEP * count), 4
            )
            name = _TOPIC_NAMES.get(topic, topic)
            failure_hint = ""
            failed = [r for r in recs if not r.success]
            if failed:
                sample = failed[0].problem
                failure_hint = f"; 典型失败: {sample[:40]}"
            patterns.append(
                Pattern(
                    pattern_id=f"{topic}_pattern",
                    name=f"{name}模式",
                    description=(
                        f"{name}相关经验 {count} 条 (成功 {success_count}, "
                        f"成功率 {success_rate:.0%}){failure_hint}"
                    ),
                    success_rate=success_rate,
                    count=count,
                    confidence=confidence,
                )
            )
        patterns.sort(key=lambda p: (-p.confidence, -p.count, p.pattern_id))
        return patterns

    # ------------------------------------------------------------ Agent 画像

    def learn_agent(self, records: list[ExperienceRecord]) -> list[AgentProfile]:
        """经验 → Agent 能力画像 (G6): 按 agent 分组聚合。

        common_problems: 失败记录 problem 去重取前 3 (截断 40 字);
        best_domains: 该 Agent 成功率 100% 的主题 (按样本量降序);
        role: 记录中首个非空 role; 无记录 agent → 不进画像。
        """
        groups: dict[str, list[ExperienceRecord]] = {}
        for record in records or []:
            agent = record.agent or "unknown"
            groups.setdefault(agent, []).append(record)
        profiles: list[AgentProfile] = []
        for agent, recs in groups.items():
            total = len(recs)
            success_count = sum(1 for r in recs if r.success)
            success_rate = round(success_count / total, 4) if total else 0.0
            role = next((r.role for r in recs if r.role), "")
            problems: list[str] = []
            for r in recs:
                if r.success:
                    continue
                problem = (r.problem or "").strip()
                if problem and problem not in problems:
                    problems.append(problem[:40])
                if len(problems) >= 3:
                    break
            domains: dict[str, int] = {}
            for r in recs:
                topic = _topic_of(r)
                if r.success:
                    domains[topic] = domains.get(topic, 0) + 1
            best = [
                topic
                for topic, count in sorted(
                    domains.items(), key=lambda kv: (-kv[1], kv[0])
                )
            ]
            profiles.append(
                AgentProfile(
                    agent_id=agent,
                    role=role,
                    total_tasks=total,
                    success_count=success_count,
                    success_rate=success_rate,
                    common_problems=problems,
                    best_domains=best,
                )
            )
        profiles.sort(key=lambda p: (-p.total_tasks, p.agent_id))
        return profiles


class LearningEngine:
    """学习引擎 (G4-G8): 完整学习循环 run(workspace)。

    提取 (ExperienceExtractor) → 存储 (ExperienceStore) → 学习
    (PatternLearner 模式 + Agent 画像) → 审计 (LearningTrace)。
    """

    def __init__(
        self,
        store: Optional[ExperienceStore] = None,
        extractor: Optional[ExperienceExtractor] = None,
        learner: Optional[PatternLearner] = None,
        trace: Optional[LearningTrace] = None,
        workspace: Any = None,
    ) -> None:
        self.store = store if store is not None else ExperienceStore.from_workspace(workspace)
        self.extractor = extractor if extractor is not None else ExperienceExtractor()
        self.learner = learner if learner is not None else PatternLearner()
        self.trace = trace if trace is not None else LearningTrace(workspace)

    def run(self, workspace: Any = None) -> LearningResult:
        """学习循环 (验收 C): 提取 → 存储 → 模式 + Agent 画像 → 审计。"""
        extracted = self.extractor.extract_all(workspace)
        added = self.store.add_all(extracted)
        patterns = self.learner.learn(extracted)
        profiles = self.learner.learn_agent(extracted)
        learned_items = [f"pattern:{p.pattern_id}" for p in patterns] + [
            f"agent:{p.agent_id}" for p in profiles
        ]
        avg_confidence = (
            round(sum(p.confidence for p in patterns) / len(patterns), 4)
            if patterns
            else 0.0
        )
        self.trace.record(
            source="learning_engine.run",
            learned=added,
            confidence=avg_confidence,
            impact=f"{len(patterns)} patterns + {len(profiles)} agent profiles",
            details={
                "workspace": str(
                    Path(workspace) if workspace is not None else Path.home() / ".factory"
                ),
                "extracted_count": len(extracted),
                "pattern_ids": [p.pattern_id for p in patterns],
                "agent_ids": [p.agent_id for p in profiles],
            },
        )
        return LearningResult(
            extracted_count=len(extracted),
            patterns=[p.to_dict() for p in patterns],
            agent_profiles=[p.to_dict() for p in profiles],
            learned_items=learned_items,
        )
