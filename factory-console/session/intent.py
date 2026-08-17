"""factory-console/session/intent.py — Intent Layer 基础 (S10-047 Task 005)。

自然语言入口: 解析为结构化 Intent (绝不生成/执行 shell 命令)。
设计: docs/sprint10/S10-046-intent-layer-design.md (§2 Intent Object / §4 注册表 / §6 边界)

组件:
- IntentObject — 结构化意图 (intent_type/params/constraints/confidence/raw)
- IntentParser (ABC) — 解析接口; 未来 LLMIntentParser 的扩展点
  (LLM 只输出结构化 Intent, 见设计 §3 Q1 — 不生成命令字符串)
- KeywordIntentParser — 当前规则 mock (关键词子串 → intent_type, 不调 LLM),
  供会话联调与测试; LLM 版后续 Task 以同接口替换

边界 (S10-046 §6):
- Intent 只映射到注册 Intent 类型 (create_project/run_task/show_cost/show_status),
  不生成/执行任意命令
- 本 Task 不调 LLM、不引入依赖 (纯标准库); 未识别 → None (请求澄清, 不猜测)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

#: Intent 类型注册表 (S10-046 §4 初始子集 — 本 Task 涉及 4 类 + S10-048 P0 list_projects)
INTENT_CREATE_PROJECT = "create_project"
INTENT_RUN_TASK = "run_task"
INTENT_SHOW_COST = "show_cost"
INTENT_SHOW_STATUS = "show_status"
INTENT_FACTORY_BUDGET = "factory_budget"
INTENT_LIST_PROJECTS = "list_projects"
#: S10-050 P1: 产品意图 (用户想创造什么 — 走 DISCOVERY 多轮, 见 conversation.py)
INTENT_CREATE_PRODUCT = "create_product"
#: S10-051 P1: 工程管线意图 (生成 PRD / 准备工程 — 规则生成, 不调 LLM)
INTENT_GENERATE_PRD = "generate_prd"
#: S10-053 P4: 质量修复意图 (修复失败任务 — RepairManager, 确认门后执行)
INTENT_REPAIR_TASK = "repair_task"
INTENT_PREPARE_PROJECT = "prepare_project"
#: S10-052 P3: 执行编排意图 (开始开发 / 进度查询 — Orchestrator Actions)
INTENT_EXECUTE_PROJECT = "execute_project"
INTENT_PROJECT_PROGRESS = "project_progress"
#: S10-055 Task 005: 项目验收意图 (通过验收 → USER_ACCEPTANCE → DELIVERED)
INTENT_ACCEPT_PROJECT = "accept_project"
#: S10-055 Task 005/006: Workforce Intelligence 意图
#: (查看团队 → 团队状态; 谁负责 → 最近任务 Agent; 为什么选择 → 计划 reason)
INTENT_WORKFORCE = "workforce"
INTENT_TASK_OWNER = "task_owner"
INTENT_AGENT_REASON = "agent_reason"
#: S10-056: Agent Team 意图 (团队协作视图 / 创建团队 — 扩展 workforce 语义,
#: 与 workforce 兼容: "查看团队" 仍归 workforce, team 关键词不抢既有映射)
INTENT_TEAM = "team"
#: S10-056 批次 B: Team Execution 意图 (集成层)
#: 团队执行 → execute_project(mode="team"); 团队依赖 → 依赖图视图;
#: 团队冲突 → 冲突记录视图 (router → team_execute/team_dependencies/team_conflicts)
INTENT_TEAM_EXECUTE = "team_execute"
INTENT_TEAM_DEPENDENCIES = "team_dependencies"
INTENT_TEAM_CONFLICTS = "team_conflicts"
#: S10-065 批次 B: 引导式自然语言意图 (集成层 — 旧关键词不动, 纯新增)
#: 用户自然对话入口: 想法 → 发现会话; 继续 → 恢复执行; 为什么停了 → 评审视图;
#: 查看进度 → 生产视图; 接受/拒绝/取消 → 人工评审决策 (ReviewGate 包装)
INTENT_DISCOVERY_START = "discovery_start"
INTENT_RESUME_PROJECT = "resume_project"
INTENT_REVIEW_VIEW = "review_view"
INTENT_PRODUCTION_SESSION_VIEW = "production_session_view"
INTENT_REVIEW_APPROVE = "review_approve"
INTENT_REVIEW_REJECT = "review_reject"
INTENT_REVIEW_CANCEL = "review_cancel"
#: S10-066: 产品智能意图 (分析产品/市场/画像/MVP/价值 — ProductIntelligenceEngine)
INTENT_PRODUCT_INTELLIGENCE = "product_intelligence"
INTENT_PRODUCT_MARKET = "product_market"
INTENT_PRODUCT_PERSONA = "product_persona"
INTENT_PRODUCT_MVP = "product_mvp"
INTENT_PRODUCT_VALUE = "product_value"
#: S10-067: Memory Learning 意图 (经验搜索/学习/统计/Agent 画像/导出 — 完整
#: 学习循环的 CLI 入口: 提取 → 学习 → 检索 → 推荐 → 影响未来)
INTENT_MEMORY_SEARCH = "memory_search"
INTENT_MEMORY_LEARN = "memory_learn"
INTENT_MEMORY_STATS = "memory_stats"
INTENT_MEMORY_ANALYZE_AGENT = "memory_analyze_agent"
INTENT_MEMORY_EXPORT = "memory_export"
#: S10-068: Debug Intelligence 意图 (分析错误 → DebugDecision; 历史/推荐/统计
#: — DebugEngine 的 CLI 入口: 错误理解 → 根因 → 历史经验 → 修复策略)
INTENT_DEBUG_ANALYZE = "debug_analyze"
INTENT_DEBUG_HISTORY = "debug_history"
INTENT_DEBUG_RECOMMEND = "debug_recommend"
INTENT_DEBUG_STATS = "debug_stats"
#: S10-068 Part 2: Autonomous Debug & Repair 意图 (会话/根因/修复/验证/继续 —
#: DebugPipeline 的 CLI 入口: 完整闭环 start→analyze→repair→validate→resume)
INTENT_DEBUG_SESSION = "debug_session"
INTENT_DEBUG_ROOT_CAUSE = "debug_root_cause"
INTENT_DEBUG_REPAIR = "debug_repair"
INTENT_DEBUG_VALIDATE = "debug_validate"
INTENT_DEBUG_RESUME = "debug_resume"
#: S10-069: Audit Intelligence 意图 (审计记录/追踪/决策链/为什么/成本/导出/统计
#: — AuditStore + AuditExplain 的 CLI 入口: 统一审计查询与可解释性)
INTENT_AUDIT_EVENTS = "audit_events"
INTENT_AUDIT_TRACE = "audit_trace"
INTENT_AUDIT_CHAIN = "audit_chain"
INTENT_AUDIT_DECISION = "audit_decision"
INTENT_AUDIT_EXPLAIN = "audit_explain"
INTENT_AUDIT_TASK = "audit_task"
INTENT_AUDIT_AGENT = "audit_agent"
INTENT_AUDIT_COST = "audit_cost"
INTENT_AUDIT_EXPORT = "audit_export"
INTENT_AUDIT_STATS = "audit_stats"

#: KeywordIntentParser 关键词规则表 (顺序 = 优先级, 确定性无歧义):
#: (关键词元组, intent_type, 参数键 — 命中后取关键词后剩余文本作为参数值)
_KEYWORD_RULES: tuple[tuple[tuple[str, ...], str, Optional[str]], ...] = (
    # S10-055 Task 005: 项目验收意图 — 最高优先级 (确认门后 DELIVERED)
    (("通过验收", "验收通过", "确认交付", "接受交付"), INTENT_ACCEPT_PROJECT, None),
    # S10-069: Audit Intelligence 意图 (纯新增, 旧关键词不动)。优先级要点:
    # - 必须在 show_cost ("成本/费用") 之前: "成本审计/查看项目成本审计" 含
    #   "成本", 不被 show_cost 抢;
    # - 必须在 agent_reason ("为什么选择") 之前: "为什么选择这个Agent" 不被抢;
    # - 必须在 create_project ("创建") 之前: "为什么创建这个任务" 不被抢;
    # - "为什么停了/为什么停止" 保留给 review_view (S10-065 基线口径),
    #   审计用 "为什么项目停了/为什么任务停了" (与基线不共享子串, 零冲突);
    # - "审计决策链" 在 "审计决策" 之前 (前者含后者, 最具体优先);
    # - "查看审计记录" 在 "审计记录" 之前 (同前缀最具体优先)。
    (("查看审计记录", "审计记录", "查看审计"), INTENT_AUDIT_EVENTS, None),
    (("审计追踪", "查看审计链路"), INTENT_AUDIT_TRACE, "trace_id"),
    (("审计决策链",), INTENT_AUDIT_CHAIN, "trace_id"),
    (("审计决策",), INTENT_AUDIT_DECISION, None),
    (("为什么创建这个任务", "为什么创建该任务"), INTENT_AUDIT_EXPLAIN, "task_id"),
    (
        ("为什么选择这个Agent", "为什么选择该Agent", "为什么选择这个agent", "为什么选择该agent"),
        INTENT_AUDIT_EXPLAIN,
        "agent_id",
    ),
    (("为什么项目停了", "为什么任务停了"), INTENT_AUDIT_EXPLAIN, None),
    (("审计任务",), INTENT_AUDIT_TASK, "task_id"),
    (("审计Agent", "审计agent"), INTENT_AUDIT_AGENT, "agent_id"),
    (("查看项目成本审计", "成本审计"), INTENT_AUDIT_COST, "project_id"),
    (("导出审计",), INTENT_AUDIT_EXPORT, None),
    (("审计统计",), INTENT_AUDIT_STATS, None),
    # S10-056 批次 B: Team Execution 意图 — 必须在 INTENT_TEAM ("团队") 与
    # INTENT_WORKFORCE 泛化关键词之前 ("团队执行/团队依赖/团队冲突" 含 "团队",
    # 不被 "团队" 泛化规则抢; "冲突" 不被 run_task "修复" 抢)
    (("团队执行", "团队开发", "团队开始开发"), INTENT_TEAM_EXECUTE, None),
    (("团队依赖", "依赖关系", "任务依赖", "依赖图"), INTENT_TEAM_DEPENDENCIES, None),
    (("团队冲突", "文件冲突", "冲突检测", "冲突"), INTENT_TEAM_CONFLICTS, None),
    # S10-056: Agent Team 意图 — 在 workforce 之前 ("团队协作/绩效" 等专属语义
    # 不被 workforce 泛化关键词 "团队" 抢; "创建团队" 不被 create_project "创建" 抢)
    (("创建团队",), INTENT_TEAM, "name"),
    (("团队协作", "协作视图", "团队绩效", "团队负载", "团队管理"), INTENT_TEAM, None),
    # S10-055 Task 005/006: Workforce 意图 — 在 show_status ("状态") 之前
    # ("团队状态" 含 "状态" 不被抢; "谁负责" 不被 run_task 抢; "为什么选择" 独立)
    (("查看团队", "团队状态", "团队成员", "团队情况", "团队"), INTENT_WORKFORCE, None),
    (("谁负责", "谁在做", "谁开发"), INTENT_TASK_OWNER, None),
    (("为什么选择", "为什么是", "为什么选"), INTENT_AGENT_REASON, None),
    # S10-053 P4: 质量修复意图 — 必须在 run_task ("修复" 关键词) 之前 (优先级更高)
    (("修复失败任务", "修复任务", "重试失败任务"), INTENT_REPAIR_TASK, None),
    # S10-068: Debug Intelligence 意图 (纯新增, 旧关键词不动)。顺序要点:
    # - 必须在 run_task ("修复") 之前: "修复建议" 含 "修复", 不被 run_task 抢;
    # - 具体前缀在前: "debug历史/推荐/统计" 含 "debug", 不被 analyze 裸 "debug" 抢
    #   (历史/推荐/统计规则在前, analyze 的裸 "debug" 规则在后 — 最具体优先);
    # - "为什么失败" 与既有 "为什么选择/为什么停了" 无共享子串, 独立映射。
    (("查看调试经验", "debug历史", "调试历史"), INTENT_DEBUG_HISTORY, None),
    (("修复建议", "debug推荐", "调试推荐", "推荐修复"), INTENT_DEBUG_RECOMMEND, None),
    (("debug统计", "调试统计", "调试数据"), INTENT_DEBUG_STATS, None),
    (("分析错误", "为什么失败", "错误分析", "调试分析", "debug", "检查一下失败原因", "检查失败原因"), INTENT_DEBUG_ANALYZE, "error_message"),
    # S10-068 Part 2: Autonomous Debug & Repair 意图 (纯新增, 旧关键词不动)。
    # 优先级要点 (必须在 run_task "修复" 与 resume_project "继续" 之前):
    # - "自动修复/验证修复" 含 "修复", 不被 run_task 抢;
    # - "继续调试" 含 "继续", 不被 resume_project 的裸 "继续" 抢;
    # - "调试会话" 与 analyze 的 "调试分析" 无共享子串, 独立映射。
    (("开始调试", "调试会话"), INTENT_DEBUG_SESSION, "error_message"),
    (("找一下根因", "根因分析", "查根因", "根因是什么"), INTENT_DEBUG_ROOT_CAUSE, "error_message"),
    (("自动修复", "自动修复错误"), INTENT_DEBUG_REPAIR, None),
    (("验证修复", "验证一下修复"), INTENT_DEBUG_VALIDATE, None),
    (("继续调试",), INTENT_DEBUG_RESUME, None),
    (("花了多少", "成本", "费用"), INTENT_SHOW_COST, None),
    # S10-049 P0: +"实现" (验收: "帮我实现登录功能" → run_task, objective="登录功能")
    (("加", "修复", "写", "实现"), INTENT_RUN_TASK, "objective"),
    (("项目列表", "有哪些项目", "列出项目"), INTENT_LIST_PROJECTS, None),
    (("状态", "看看"), INTENT_SHOW_STATUS, None),
    (("查看预算", "预算情况", "预算"), INTENT_FACTORY_BUDGET, None),
    # S10-051 P1: 工程管线意图 — 优先级在 create_product 之前
    # ("我想生成PRD" 不被 "我想" 抢; "准备开发一个APP" 不被 "开发一个" 抢)
    (("生成PRD", "生成需求文档", "PRD"), INTENT_GENERATE_PRD, None),
    (("准备开发", "生成工程计划", "工程计划", "准备工程"), INTENT_PREPARE_PROJECT, None),
    # S10-052 P3: 执行编排意图 — 优先级在 create_product 之前
    # ("开始开发这个产品" 不被 "产品" 抢; "执行项目" 不被 run_task 抢)
    (("开始开发", "开始执行", "执行项目", "开始开发这个产品"), INTENT_EXECUTE_PROJECT, None),
    (("项目进度", "进度如何", "执行到哪了"), INTENT_PROJECT_PROGRESS, None),
    # S10-053 P4: 质量修复意图 — 修复失败任务 (RepairManager, 确认门)
    (("修复失败任务", "修复任务", "重试失败任务"), INTENT_REPAIR_TASK, None),
    # S10-065 批次 B: 引导式自然语言 (集成层 — 旧关键词不动, 纯新增)。
    # 优先级在 create_product ("我想") 之前: "我想做X" 的前缀与既有 "我想"
    # 规则共享子串 — 新增关键词避开基线测试口径 (见 test_session_product /
    # test_session_intent 优先级回归), 基线短语映射零变化。
    # "开始做/让我做X" → 引导 DiscoverySession; "我想做X" 仍走既有
    # create_product 产品流程 (conversation 接管, 兼容基线)。
    (("开始做", "让我做"), INTENT_DISCOVERY_START, "idea"),
    (("继续执行", "继续开发", "继续", "resume"), INTENT_RESUME_PROJECT, None),
    (("为什么停了", "为什么停止", "为什么暂停"), INTENT_REVIEW_VIEW, None),
    (("查看进度", "现在做到哪了", "做到哪了"), INTENT_PRODUCTION_SESSION_VIEW, None),
    # S10-066: 产品智能意图 (ProductIntelligenceEngine)
    (("分析产品", "产品分析", "产品智能"), INTENT_PRODUCT_INTELLIGENCE, None),
    (("产品市场", "市场分析", "有没有市场", "市场怎么样"), INTENT_PRODUCT_MARKET, None),
    (("产品画像", "用户画像"), INTENT_PRODUCT_PERSONA, None),
    (("MVP规划", "MVP拆分", "MVP计划"), INTENT_PRODUCT_MVP, None),
    (("产品价值", "价值评分"), INTENT_PRODUCT_VALUE, None),
    # S10-067: Memory Learning 意图 (经验智能 — 纯新增, 旧关键词不动)。
    # 优先级在 create_product ("我想"/"产品") 与 create_project ("创建") 之前:
    # "我想搜索经验" 不被 "我想" 抢; "学习" 不与 run_task (写/修复/实现/加)
    # 共享子串; "分析Agent" 不与其他 "分析" 类规则冲突 (无裸 "分析" 规则)。
    (("搜索经验", "查找经验", "查经验", "学到了什么", "有什么经验"), INTENT_MEMORY_SEARCH, "query"),
    (("学习经验", "经验学习", "学习"), INTENT_MEMORY_LEARN, None),
    (("经验统计",), INTENT_MEMORY_STATS, None),
    (
        ("分析Agent", "分析agent", "Agent成长", "agent成长", "Agent分析", "agent分析"),
        INTENT_MEMORY_ANALYZE_AGENT,
        "agent_id",
    ),
    (("导出经验",), INTENT_MEMORY_EXPORT, None),
    # S10-050 P1: 产品意图 (想法级) — "我想/做一款/产品/想法/创业" → create_product
    # (idea 参数 = 关键词后剩余文本; 优先级在 run_task/show_status 之后,
    #  "我想看看状态" → show_status、"我想加个功能" → run_task 不被抢)
    (("我想", "做一款", "产品", "想法", "创业"), INTENT_CREATE_PRODUCT, "idea"),
    (("创建", "做一个", "开发一个"), INTENT_CREATE_PROJECT, "name"),
    # S10-065 批次 B: 评审确认意图 (Review UX — 纯新增, 旧关键词不动)。
    # 必须在 accept_project ("接受交付") 之后: "接受交付" 仍归 accept_project,
    # 裸 "接受" → review_approve; "帮我做X" 放在 "做一个/开发一个" 之后 —
    # "帮我做一个电商 APP" 仍归 create_project/product (基线口径), 不抢既有映射。
    (("接受", "批准", "同意", "approve"), INTENT_REVIEW_APPROVE, None),
    (("拒绝", "reject"), INTENT_REVIEW_REJECT, None),
    (("取消", "cancel"), INTENT_REVIEW_CANCEL, None),
    (("帮我做",), INTENT_DISCOVERY_START, "idea"),
)

#: 产品意图判别标记 ("做一个"/"开发一个" 后接标记 → create_product;
#: 否则归 create_project — S10-050 P1 区分 "做产品" vs "做项目")
_PRODUCT_MARKERS: tuple[str, ...] = ("APP", "产品", "想法", "创业", "款")


@dataclass
class IntentObject:
    """结构化意图 (S10-046 §2): 解析结果, 非 shell 命令。

    intent_type: 注册 Intent 类型 (create_project/run_task/show_cost/show_status)
    params:      参数 (如 {"name": "APP", "objective": "测试", "period": "session"})
    constraints: 约束 (如 provider/agent/budget_usd — 后续 Policy Check 使用)
    confidence:  解析置信度 0-1 (LLM 版为模型置信度; 规则 mock 确定性匹配 = 1.0)
    raw:         原始输入 (审计)
    """

    intent_type: str
    params: dict[str, Any] = field(default_factory=dict)
    constraints: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    raw: str = ""
    source: str = ""  # S10-048 §2.2: "cli" | "chat" | "agent" | "api" | "session" (会话派发时注入)
    metadata: dict[str, Any] = field(default_factory=dict)  # 扩展: user_id/workspace/session_id

    @property
    def type(self) -> str:
        """intent_type 别名 (验收口径: type/confidence/parameters/raw)。"""
        return self.intent_type

    @property
    def parameters(self) -> dict[str, Any]:
        """params 别名 (验收口径: type/confidence/parameters/raw)。"""
        return self.params


class IntentParser(ABC):
    """Intent 解析接口 (未来 LLM 扩展点, S10-046 §3 Q1)。

    唯一契约: parse(text) -> IntentObject | None — 未识别 → None (由上层请求
    澄清, 绝不猜测执行)。LLMIntentParser (后续 Task 实现): LLM 结构化输出
    (JSON mode / function calling, 输出 {"intent_type", "params", "constraints"}),
    结果仍封装为 IntentObject — 不生成 shell 命令字符串。
    """

    @abstractmethod
    def parse(self, text: str) -> Optional[IntentObject]:
        """解析自然语言输入 → 结构化 Intent; 未识别 → None。"""


class KeywordIntentParser(IntentParser):
    """规则 mock 解析器 (不调 LLM): 关键词子串匹配 → 结构化 Intent。

    命中规则 → IntentObject (confidence=1.0 — 确定性规则匹配);
    未命中/空输入 → None (未识别)。规则见 _KEYWORD_RULES (顺序 = 优先级)。
    """

    def __init__(
        self, rules: Optional[tuple[tuple[tuple[str, ...], str, Optional[str]], ...]] = None
    ) -> None:
        self._rules = rules if rules is not None else _KEYWORD_RULES

    def parse(self, text: str) -> Optional[IntentObject]:
        raw = text.strip() if text else ""
        if not raw:
            return None
        for keywords, intent_type, param_key in self._rules:
            for keyword in keywords:
                if keyword not in raw:
                    continue
                hint = raw.split(keyword, 1)[1].strip() if param_key else ""
                # S10-050 P1: "做一个"/"开发一个" 后接产品标记 → create_product
                # (区分 "做产品" vs "做项目"; 无标记 → 归 create_project, 基线不回归)
                if intent_type == INTENT_CREATE_PROJECT and keyword in ("做一个", "开发一个"):
                    if hint.startswith(_PRODUCT_MARKERS):
                        intent_type = INTENT_CREATE_PRODUCT
                        param_key = "idea"
                params: dict[str, Any] = {}
                if intent_type == INTENT_SHOW_COST:
                    # 设计 §2 示例口径: show_cost {period: "session"}
                    params["period"] = "session"
                elif param_key:
                    if hint:
                        params[param_key] = hint
                return IntentObject(
                    intent_type=intent_type,
                    params=params,
                    constraints={},
                    confidence=1.0,
                    raw=raw,
                )
        return None
