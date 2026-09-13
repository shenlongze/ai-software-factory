"""factory-console/session/product_intelligence.py — ProductIntelligenceEngine (S10-066)。

产品智能分析引擎: ProductIntent → 8 模块结构化分析 (GAP G1-G8):
  industry_analysis (G1 行业理解) / competitor_analysis (G2 竞品分析) /
  user_personas (G3 用户画像) / requirement_conflicts (G4 需求冲突检测) /
  product_value_score (G5 价值判断) / mvp_plan (G6 MVP 规划) /
  business_analysis (G7 商业分析) / market_analysis (G8 市场分析)。

双模式 (设计 §2, S10-062 fallback 模式):
- LLM 模式: analyze(..., llm_provider=可调用/ReasoningProvider) → 结构化输出
  (JSON 契约 → 校验 → 构建报告); 任何失败 (调用异常/解析失败/schema 缺失/
  非法值) → 自动 fallback deterministic (LLM 挂不影响系统)。
- deterministic 模式: 规则/模板 — product_intent 字段 → 各模块分析
  (problem→pain_points; user→user_types/personas; core_features→MVP 拆分:
  前 1-2 功能→MVP, 其余→V2, 平台/扩展类→Future; platform→冲突检测等)。

持久化: save(workspace, report) / load(workspace, product) → 产品目录
  product_intelligence.json (projects/<slug>/ 或直接产品目录, 失败安全 → None)。

边界:
- 纯标准库 + 只读引用 session/product.ProductIntent; 零新依赖
- 不抓取真实市场数据 (LLM 知识 + 规则模板 — GAP 五不该); 不修改任何现有模块
- llm_provider 鸭子类型: 可调用 (prompt[, operation]) -> str|dict, 或带
  llm_fn/_llm_fn 属性的对象 (ReasoningProvider 实例直接可传 — S10-062 复用)

设计: docs/sprint10/S10-066-gap-analysis.md (G1-G8) +
      docs/sprint10/S10-066-product-intelligence-design.md (§2 Core)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from .product import ProductIntent

#: 智能分析资产文件名 (产品目录 product_intelligence.json — 设计 §2 资产口径)
INTELLIGENCE_FILE_NAME = "product_intelligence.json"

#: 通用痛点兜底 (problem 无法拆分时)
_GENERIC_PAIN_POINTS: tuple[str, ...] = (
    "现有方案操作繁琐, 学习成本高",
    "信息分散, 缺乏统一管理入口",
    "人工处理效率低, 易出错",
    "缺乏实时/自动化的反馈闭环",
)

#: 行业关键词 → 行业名 (deterministic 规则; 命中计数最高者胜)
_INDUSTRY_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("教育", "学习", "课程", "考试", "培训", "老师", "学生", "题库"), "教育"),
    (("电商", "购物", "商城", "卖", "订单", "商品", "店铺", "网购"), "电商零售"),
    (("金融", "理财", "记账", "投资", "股票", "保险", "支付", "账单"), "金融科技"),
    (("医疗", "健康", "医生", "看病", "体检", "健身", "运动", "睡眠"), "医疗健康"),
    (("社交", "聊天", "社区", "交友", "朋友圈", "消息", "互动"), "社交"),
    (("办公", "协作", "文档", "会议", "项目管理", "任务", "工作", "效率"), "企业办公/协作"),
    (("游戏", "娱乐", "休闲", "益智", "对战"), "游戏娱乐"),
    (("餐饮", "外卖", "美食", "菜谱", "餐厅", "点餐"), "本地生活"),
    (("出行", "导航", "打车", "地图", "旅游", "行程"), "出行旅游"),
    (("工具", "记录", "笔记", "提醒", "日历", "计算", "清单"), "效率工具"),
)

#: 盈利模式关键词 (deterministic — 命中即加入 revenue_models)
_BUSINESS_MODEL_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("订阅", "会员", "月费", "年费"), "订阅制 (会员/周期付费)"),
    (("广告", "流量", "曝光"), "广告变现"),
    (("抽成", "佣金", "交易", "手续费", "平台抽"), "交易佣金/平台抽成"),
    (("免费", "增值"), "免费 + 增值服务 (Freemium)"),
    (("企业", "公司", "团队", "B2B"), "企业许可 / B2B 销售"),
    (("买断", "一次性", "付费下载"), "一次性买断"),
    (("数据", "报告", "分析"), "数据/报告增值服务"),
)

#: 用户类型关键词 (deterministic — user 字段命中 → user_types)
_USER_TYPE_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("学生", "大学生", "考生", "考研"), "学生群体"),
    (("家长", "父母", "宝妈"), "家长/家庭用户"),
    (("教师", "老师", "讲师", "教练"), "教师/教练群体"),
    (("企业", "公司", "团队", "员工", "白领", "上班族", "职场"), "企业/职场用户"),
    (("开发者", "程序员", "工程师", "技术"), "开发者"),
    (("商家", "店主", "卖家", "老板", "商户"), "商家群体"),
    (("老人", "中老年", "银发"), "中老年用户"),
    (("健身", "运动", "跑步", "骑手"), "运动爱好者"),
    (("个人", "普通人", "消费者", "大众", "用户"), "个人消费者"),
)

#: 行业 → 常见功能 (deterministic 模板; 未命中 → 通用功能)
_COMMON_FEATURES: dict[str, list[str]] = {
    "教育": ["课程/内容管理", "学习进度跟踪", "在线测验/练习", "成绩与报告"],
    "电商零售": ["商品展示", "购物车", "在线支付", "订单管理", "物流跟踪"],
    "金融科技": ["账户管理", "交易记录", "数据报表", "安全认证"],
    "医疗健康": ["健康档案", "数据记录", "提醒打卡", "报告分析"],
    "社交": ["用户主页", "动态/消息", "互动点赞", "好友关系"],
    "企业办公/协作": ["任务管理", "文档协作", "会议/日程", "权限与审批"],
    "游戏娱乐": ["核心玩法", "关卡/进度", "成就系统", "排行榜"],
    "本地生活": ["门店/商品浏览", "下单预约", "评价体系", "优惠营销"],
    "出行旅游": ["搜索/路线", "预订下单", "行程管理", "位置服务"],
    "效率工具": ["数据录入", "分类管理", "提醒通知", "搜索/导出"],
}

#: 技术趋势关键词 (deterministic — 命中即加入 tech_trends)
_TECH_TREND_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("AI", "智能", "算法", "推荐", "生成", "大模型"), "AI 能力嵌入 (推荐/生成/自动化)"),
    (("大数据", "数据", "分析", "报表"), "数据驱动决策"),
    (("云", "SaaS", "多端", "同步"), "云原生 / SaaS 化"),
    (("移动", "手机", "APP", "小程序"), "移动优先"),
    (("物联网", "IoT", "硬件", "设备"), "IoT 物联"),
    (("区块链", "Web3"), "区块链/Web3"),
)

#: 竞品原型 (行业 → 典型竞品; deterministic 模板 — 非真实爬取)
_COMPETITOR_ARCHETYPES: dict[str, list[dict[str, Any]]] = {
    "教育": [
        {"name": "行业头部教育平台", "category": "综合教育",
         "strengths": ["内容资源丰富", "品牌认知度高"],
         "weaknesses": ["功能重、模板化", "个性化服务不足"]},
        {"name": "免费工具型产品", "category": "效率工具",
         "strengths": ["免费易用", "流量入口多"],
         "weaknesses": ["深度功能缺失", "数据服务薄弱"]},
    ],
    "电商零售": [
        {"name": "综合电商平台", "category": "综合电商",
         "strengths": ["流量巨大", "供应链完善"],
         "weaknesses": ["中小商家扶持弱", "抽成较高"]},
        {"name": "垂直电商/私域工具", "category": "垂直电商",
         "strengths": ["垂直场景专注", "运营灵活"],
         "weaknesses": ["规模有限", "获客依赖内容"]},
    ],
    "金融科技": [
        {"name": "银行/持牌金融 App", "category": "金融服务",
         "strengths": ["合规可信", "资金实力强"],
         "weaknesses": ["体验传统", "创新速度慢"]},
        {"name": "互联网记账/理财工具", "category": "个人金融工具",
         "strengths": ["轻量易用", "数据可视化好"],
         "weaknesses": ["变现路径单一", "信任门槛高"]},
    ],
    "医疗健康": [
        {"name": "健康类综合平台", "category": "健康管理",
         "strengths": ["内容/服务生态全"],
         "weaknesses": ["数据闭环弱", "个性化欠缺"]},
        {"name": "智能硬件厂商生态", "category": "硬件+App",
         "strengths": ["硬件数据入口", "品牌绑定"],
         "weaknesses": ["跨品牌不互通", "软件体验一般"]},
    ],
    "社交": [
        {"name": "头部社交平台", "category": "综合社交",
         "strengths": ["用户规模大", "关系链成熟"],
         "weaknesses": ["功能泛化", "垂直场景不深"]},
        {"name": "垂直兴趣社区", "category": "垂直社区",
         "strengths": ["圈层精准", "粘性高"],
         "weaknesses": ["增长天花板低", "商业化较弱"]},
    ],
    "企业办公/协作": [
        {"name": "综合协作套件", "category": "协作平台",
         "strengths": ["生态完善", "企业背书强"],
         "weaknesses": ["上手成本高", "定制化贵"]},
        {"name": "轻量单点工具", "category": "效率工具",
         "strengths": ["轻量快", "价格低"],
         "weaknesses": ["协同能力弱", "数据孤岛"]},
    ],
    "游戏娱乐": [
        {"name": "头部休闲游戏", "category": "休闲游戏",
         "strengths": ["流量分发强", "玩法成熟"],
         "weaknesses": ["同质化严重", "买量成本高"]},
    ],
    "本地生活": [
        {"name": "本地生活巨头平台", "category": "综合平台",
         "strengths": ["流量与履约能力强"],
         "weaknesses": ["商户抽成高", "小商户关注少"]},
        {"name": "独立品牌私域工具", "category": "私域运营",
         "strengths": ["低抽成", "客户资产自有"],
         "weaknesses": ["获客依赖自营"]},
    ],
    "出行旅游": [
        {"name": "综合出行/OTA 平台", "category": "出行平台",
         "strengths": ["资源覆盖广", "价格优势"],
         "weaknesses": ["服务同质", "佣金高"]},
    ],
    "效率工具": [
        {"name": "系统自带/通用工具", "category": "效率工具",
         "strengths": ["免费预装", "入口便捷"],
         "weaknesses": ["功能基础", "跨设备弱"]},
        {"name": "付费专业工具", "category": "专业工具",
         "strengths": ["深度功能", "生态插件"],
         "weaknesses": ["价格门槛", "学习曲线"]},
    ],
}

#: 通用竞品兜底 (行业未命中)
_GENERIC_COMPETITORS: list[dict[str, Any]] = [
    {"name": "同类通用产品", "category": "直接竞品",
     "strengths": ["已有用户基础", "功能相对成熟"],
     "weaknesses": ["场景泛化", "垂直深度不足"]},
    {"name": "免费替代方案", "category": "替代方案",
     "strengths": ["免费/低成本"],
     "weaknesses": ["维护不稳定", "数据安全存疑"]},
]

#: 未来/扩展功能关键词 (core_features 拆分 → Future)
_FUTURE_KEYWORDS: tuple[str, ...] = (
    "管理后台", "后台管理", "数据看板", "报表", "多语言", "国际化",
    "插件", "开放平台", "开放API", "API", "小程序", "数据统计",
    "智能推荐", "AI生成", "推荐算法", "社区", "商城", "广告",
)


def _now_iso() -> str:
    """UTC 当前时间 ISO 格式 (报告时间戳)。"""
    return datetime.now(timezone.utc).isoformat()


def _slugify(text: str) -> str:
    """宽松 slug 化 (产品名 → 目录名; 同 actions._slugify 口径但保留中文,
    中文产品名目录可直接定位 — 本地实现防循环导入)。"""
    slug = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", str(text or "").strip().lower()).strip("-")
    return slug


def _text(value: Any) -> str:
    """字段 → 规范化文本 (None/列表 → 空串/拼接)。"""
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(str(v) for v in value if str(v).strip())
    return str(value).strip()


def _split_pain_points(problem: str) -> list[str]:
    """problem → 痛点列表: 按标点拆分 + 通用兜底 (deterministic 规则)。"""
    raw = _text(problem)
    if not raw:
        return list(_GENERIC_PAIN_POINTS)
    parts = [
        p.strip().strip("，。；、,.;:：") for p in re.split(r"[，。；、,.;:：\n]", raw) if p.strip()
    ]
    pains = [p for p in parts if len(p) >= 2]
    if not pains:
        pains = [raw]
    if len(pains) < 2:
        pains = pains + list(_GENERIC_PAIN_POINTS[: 2 - len(pains)])
    return pains[:4]


def _match_keywords(text: str, table: tuple[tuple[tuple[str, ...], str], ...]) -> list[str]:
    """关键词命中 (多条目可同时命中 — 顺序 = 表顺序, 确定性)。"""
    hits: list[str] = []
    for keywords, label in table:
        if any(kw in text for kw in keywords):
            if label not in hits:
                hits.append(label)
    return hits


def _best_industry(text: str) -> str:
    """行业判定: 命中关键词计数最高者; 并列 → 表序优先; 未命中 → \"\"""。"""
    best, best_count = "", 0
    for keywords, industry in _INDUSTRY_KEYWORDS:
        count = sum(1 for kw in keywords if kw in text)
        if count > best_count:
            best, best_count = industry, count
    return best


# ---------------------------------------------------------------- 8 模块模型

@dataclass
class IndustryAnalysis:
    """G1 行业理解: 行业/商业模式/用户类型/常见功能/痛点/技术趋势。"""

    industry: str = ""
    business_models: list[str] = field(default_factory=list)
    user_types: list[str] = field(default_factory=list)
    common_features: list[str] = field(default_factory=list)
    pain_points: list[str] = field(default_factory=list)
    tech_trends: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "industry": self.industry,
            "business_models": list(self.business_models),
            "user_types": list(self.user_types),
            "common_features": list(self.common_features),
            "pain_points": list(self.pain_points),
            "tech_trends": list(self.tech_trends),
        }

    @classmethod
    def from_dict(cls, data: Any) -> "IndustryAnalysis":
        d = data if isinstance(data, dict) else {}
        return cls(
            industry=_text(d.get("industry")),
            business_models=[_text(x) for x in (d.get("business_models") or []) if x is not None],
            user_types=[_text(x) for x in (d.get("user_types") or []) if x is not None],
            common_features=[_text(x) for x in (d.get("common_features") or []) if x is not None],
            pain_points=[_text(x) for x in (d.get("pain_points") or []) if x is not None],
            tech_trends=[_text(x) for x in (d.get("tech_trends") or []) if x is not None],
        )


@dataclass
class CompetitorAnalysis:
    """G2 竞品分析: 竞品列表 (dict) / 自身优势 / 差异化机会。"""

    competitors: list[dict[str, Any]] = field(default_factory=list)
    advantages: list[str] = field(default_factory=list)
    differentiation_opportunities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "competitors": [dict(c) for c in self.competitors],
            "advantages": list(self.advantages),
            "differentiation_opportunities": list(self.differentiation_opportunities),
        }

    @classmethod
    def from_dict(cls, data: Any) -> "CompetitorAnalysis":
        d = data if isinstance(data, dict) else {}
        competitors = []
        for c in (d.get("competitors") or []):
            if isinstance(c, dict):
                competitors.append({
                    "name": _text(c.get("name")),
                    "category": _text(c.get("category")),
                    "strengths": [_text(x) for x in (c.get("strengths") or []) if x is not None],
                    "weaknesses": [_text(x) for x in (c.get("weaknesses") or []) if x is not None],
                })
        return cls(
            competitors=competitors,
            advantages=[_text(x) for x in (d.get("advantages") or []) if x is not None],
            differentiation_opportunities=[
                _text(x) for x in (d.get("differentiation_opportunities") or []) if x is not None
            ],
        )


@dataclass
class UserPersona:
    """G3 用户画像: 名称/描述/使用场景/痛点。"""

    name: str = ""
    description: str = ""
    scenarios: list[str] = field(default_factory=list)
    pain_points: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "scenarios": list(self.scenarios),
            "pain_points": list(self.pain_points),
        }

    @classmethod
    def from_dict(cls, data: Any) -> "UserPersona":
        d = data if isinstance(data, dict) else {}
        return cls(
            name=_text(d.get("name")),
            description=_text(d.get("description")),
            scenarios=[_text(x) for x in (d.get("scenarios") or []) if x is not None],
            pain_points=[_text(x) for x in (d.get("pain_points") or []) if x is not None],
        )


@dataclass
class RequirementConflict:
    """G4 需求冲突: 描述/严重度/影响字段/建议。"""

    description: str = ""
    severity: str = "low"
    affected_fields: list[str] = field(default_factory=list)
    suggestion: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "severity": self.severity,
            "affected_fields": list(self.affected_fields),
            "suggestion": self.suggestion,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "RequirementConflict":
        d = data if isinstance(data, dict) else {}
        sev = _text(d.get("severity")) or "low"
        if sev not in ("low", "medium", "high"):
            sev = "low"
        return cls(
            description=_text(d.get("description")),
            severity=sev,
            affected_fields=[_text(x) for x in (d.get("affected_fields") or []) if x is not None],
            suggestion=_text(d.get("suggestion")),
        )


@dataclass
class ProductValueScore:
    """G5 价值评分: 0-100 分 + 用户价值/技术价值/理由。"""

    score: int = 0
    user_value: str = ""
    technical_value: str = ""
    justification: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": int(self.score),
            "user_value": self.user_value,
            "technical_value": self.technical_value,
            "justification": self.justification,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "ProductValueScore":
        d = data if isinstance(data, dict) else {}
        try:
            score = max(0, min(100, int(float(d.get("score") or 0))))
        except (TypeError, ValueError):
            score = 0
        return cls(
            score=score,
            user_value=_text(d.get("user_value")),
            technical_value=_text(d.get("technical_value")),
            justification=_text(d.get("justification")),
        )


@dataclass
class MvpPlan:
    """G6 MVP 规划: mvp/v2/future 三阶段功能拆分。"""

    mvp: list[str] = field(default_factory=list)
    v2: list[str] = field(default_factory=list)
    future: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mvp": list(self.mvp),
            "v2": list(self.v2),
            "future": list(self.future),
        }

    @classmethod
    def from_dict(cls, data: Any) -> "MvpPlan":
        d = data if isinstance(data, dict) else {}
        return cls(
            mvp=[_text(x) for x in (d.get("mvp") or []) if x is not None],
            v2=[_text(x) for x in (d.get("v2") or []) if x is not None],
            future=[_text(x) for x in (d.get("future") or []) if x is not None],
        )


@dataclass
class BusinessAnalysis:
    """G7 商业分析: 盈利模式/成本结构/用户获取/商业风险。"""

    revenue_models: list[str] = field(default_factory=list)
    cost_structure: list[str] = field(default_factory=list)
    user_acquisition: list[str] = field(default_factory=list)
    business_risks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "revenue_models": list(self.revenue_models),
            "cost_structure": list(self.cost_structure),
            "user_acquisition": list(self.user_acquisition),
            "business_risks": list(self.business_risks),
        }

    @classmethod
    def from_dict(cls, data: Any) -> "BusinessAnalysis":
        d = data if isinstance(data, dict) else {}
        return cls(
            revenue_models=[_text(x) for x in (d.get("revenue_models") or []) if x is not None],
            cost_structure=[_text(x) for x in (d.get("cost_structure") or []) if x is not None],
            user_acquisition=[_text(x) for x in (d.get("user_acquisition") or []) if x is not None],
            business_risks=[_text(x) for x in (d.get("business_risks") or []) if x is not None],
        )


@dataclass
class MarketAnalysis:
    """G8 市场分析: 市场规模/用户趋势/机会窗口。"""

    market_size: str = ""
    user_trends: list[str] = field(default_factory=list)
    opportunity_window: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_size": self.market_size,
            "user_trends": list(self.user_trends),
            "opportunity_window": self.opportunity_window,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "MarketAnalysis":
        d = data if isinstance(data, dict) else {}
        return cls(
            market_size=_text(d.get("market_size")),
            user_trends=[_text(x) for x in (d.get("user_trends") or []) if x is not None],
            opportunity_window=_text(d.get("opportunity_window")),
        )


#: 市场规模定性分级 (行业 → 量级描述 — deterministic 模板)
_MARKET_SIZE_TIERS: dict[str, str] = {
    "教育": "大市场 (百亿级): 教育与培训数字化渗透率持续提升",
    "电商零售": "大市场 (万亿级): 电商渗透率仍在增长, 垂直/私域空间大",
    "金融科技": "大市场 (万亿级): 个人与小微企业金融数字化加速",
    "医疗健康": "大市场 (千亿级): 健康管理需求长期增长",
    "社交": "大市场 (百亿级): 垂直社交仍有细分机会",
    "企业办公/协作": "大市场 (百亿级): 企业 SaaS 付费意愿增强",
    "游戏娱乐": "中市场 (百亿级): 休闲游戏竞争激烈, 内容差异化是核心",
    "本地生活": "区域性市场: 本地化运营深度决定胜负",
    "出行旅游": "大市场 (千亿级): 出行数字化成熟, 细分场景有机会",
    "效率工具": "中市场: 工具类产品用户基数大但付费转化需运营",
}

#: 市场趋势 (命中关键词 → user_trends; 通用趋势兜底)
_MARKET_TREND_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("AI", "智能", "推荐", "生成"), "AI 应用普及, 智能化体验成为标配"),
    (("移动", "APP", "手机", "小程序"), "移动化/小程序化使用习惯成熟"),
    (("企业", "团队", "办公"), "远程协作与数字化办公常态化"),
    (("社交", "社区", "互动"), "圈层化社区与内容互动兴起"),
    (("健康", "运动", "睡眠"), "健康意识提升, 自我量化管理流行"),
)

#: LLM 模式输出必需顶层键 (8 模块 — schema 校验, 缺失 → fallback)
_LLM_REPORT_KEYS: tuple[str, ...] = (
    "industry_analysis", "competitor_analysis", "user_personas",
    "requirement_conflicts", "product_value_score", "mvp_plan",
    "business_analysis", "market_analysis",
)

#: JSON 提取正则 (markdown code fence 内 JSON / 裸 JSON 对象 — 同 reasoning 解析)
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class ProductIntelligenceReport:
    """S10-066 产品智能报告: 产品名/时间戳 + 8 模块 + to_dict/from_dict。"""

    product_name: str = ""
    timestamp: str = ""
    industry_analysis: IndustryAnalysis = field(default_factory=IndustryAnalysis)
    competitor_analysis: CompetitorAnalysis = field(default_factory=CompetitorAnalysis)
    user_personas: list[UserPersona] = field(default_factory=list)
    requirement_conflicts: list[RequirementConflict] = field(default_factory=list)
    product_value_score: ProductValueScore = field(default_factory=ProductValueScore)
    mvp_plan: MvpPlan = field(default_factory=MvpPlan)
    business_analysis: BusinessAnalysis = field(default_factory=BusinessAnalysis)
    market_analysis: MarketAnalysis = field(default_factory=MarketAnalysis)

    def to_dict(self) -> dict[str, Any]:
        """→ dict (落盘 product_intelligence.json / API 响应)。"""
        return {
            "product_name": self.product_name,
            "timestamp": self.timestamp or _now_iso(),
            "industry_analysis": self.industry_analysis.to_dict(),
            "competitor_analysis": self.competitor_analysis.to_dict(),
            "user_personas": [p.to_dict() for p in self.user_personas],
            "requirement_conflicts": [c.to_dict() for c in self.requirement_conflicts],
            "product_value_score": self.product_value_score.to_dict(),
            "mvp_plan": self.mvp_plan.to_dict(),
            "business_analysis": self.business_analysis.to_dict(),
            "market_analysis": self.market_analysis.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Any) -> "ProductIntelligenceReport":
        """dict → 报告 (缺失字段默认 — 前向兼容/失败安全)。"""
        d = data if isinstance(data, dict) else {}
        personas = []
        for p in (d.get("user_personas") or []):
            if isinstance(p, dict):
                personas.append(UserPersona.from_dict(p))
        conflicts = []
        for c in (d.get("requirement_conflicts") or []):
            if isinstance(c, dict):
                conflicts.append(RequirementConflict.from_dict(c))
        return cls(
            product_name=_text(d.get("product_name")),
            timestamp=_text(d.get("timestamp")),
            industry_analysis=IndustryAnalysis.from_dict(d.get("industry_analysis")),
            competitor_analysis=CompetitorAnalysis.from_dict(d.get("competitor_analysis")),
            user_personas=personas,
            requirement_conflicts=conflicts,
            product_value_score=ProductValueScore.from_dict(d.get("product_value_score")),
            mvp_plan=MvpPlan.from_dict(d.get("mvp_plan")),
            business_analysis=BusinessAnalysis.from_dict(d.get("business_analysis")),
            market_analysis=MarketAnalysis.from_dict(d.get("market_analysis")),
        )


# ---------------------------------------------------------------- 引擎

class ProductIntelligenceEngine:
    """产品智能引擎 (设计 §2): 8 模块分析 + LLM/deterministic 双模式 + fallback。

    analyze(product_intent, *, llm_provider=None) -> ProductIntelligenceReport:
    - llm_provider=None → deterministic 模式 (规则/模板)
    - llm_provider 提供 → LLM 模式 (结构化输出); 失败 → deterministic fallback
    - product_intent: ProductIntent 或 dict (ProductIntent.from_dict 兼容)
    """

    # ------------------------------------------------------------ 入口

    def analyze(
        self,
        product_intent: Any,
        *,
        llm_provider: Any = None,
    ) -> ProductIntelligenceReport:
        """完整 8 模块分析 (LLM 模式 + fallback; 缺省 deterministic)。"""
        intent = self._intent(product_intent)
        if llm_provider is not None:
            try:
                return self._analyze_llm(intent, llm_provider)
            except Exception:  # noqa: BLE001 — LLM 任何失败 → deterministic (S10-062 模式)
                return self._analyze_deterministic(intent)
        return self._analyze_deterministic(intent)

    def _analyze_deterministic(self, intent: ProductIntent) -> ProductIntelligenceReport:
        """deterministic 模式: 8 模块规则分析 (单一事实来源 — 单模块方法复用)。"""
        industry = self.analyze_industry(intent)
        competitor = self.analyze_competitor(intent)
        personas = self.analyze_persona(intent)
        conflicts = self.detect_conflicts(intent)
        value = self.score_value(intent)
        mvp = self.plan_mvp(intent)
        business = self.analyze_business(intent)
        market = self.analyze_market(intent)
        return ProductIntelligenceReport(
            product_name=intent.name or "(未命名)",
            timestamp=_now_iso(),
            industry_analysis=industry,
            competitor_analysis=competitor,
            user_personas=personas,
            requirement_conflicts=conflicts,
            product_value_score=value,
            mvp_plan=mvp,
            business_analysis=business,
            market_analysis=market,
        )

    # ------------------------------------------------------------ LLM 模式

    @classmethod
    def _llm_fn(cls, provider: Any) -> Callable[..., Any]:
        """provider → 可调用 llm_fn (鸭子类型: 可调用 / llm_fn / _llm_fn)。"""
        if callable(provider):
            return provider
        fn = getattr(provider, "llm_fn", None) or getattr(provider, "_llm_fn", None)
        if callable(fn):
            return fn
        # S10-066 修复: ReasoningProvider 实例 (_llm_fn 可能 None → 用其默认真实调用)
        if hasattr(provider, "_llm_fn") and hasattr(provider, "_default_llm_fn"):
            default_fn = provider._default_llm_fn()
            if callable(default_fn):
                return default_fn
        raise TypeError(
            "llm_provider 必须为可调用 (prompt[, operation]) -> str|dict, "
            "或带 llm_fn 的对象 (如 ReasoningProvider 实例)"
        )

    def _analyze_llm(self, intent: ProductIntent, provider: Any) -> ProductIntelligenceReport:
        """LLM 模式: prompt → llm_fn → JSON 解析 → schema 校验 → 构建报告。

        任何失败 → 抛 (analyze 捕获 → deterministic fallback)。
        """
        fn = self._llm_fn(provider)
        prompt = self.build_llm_prompt(intent)
        raw = self._invoke_llm(fn, prompt)
        parsed = self._parse_json(raw)
        if not isinstance(parsed, dict):
            raise ValueError(f"LLM 输出非 JSON 对象 (类型 {type(parsed).__name__})")
        missing = [k for k in _LLM_REPORT_KEYS if k not in parsed]
        if missing:
            raise ValueError(f"LLM 输出缺 8 模块字段: {missing}")
        score = parsed.get("product_value_score")
        if isinstance(score, dict):
            try:
                s = int(float(score.get("score") or 0))
            except (TypeError, ValueError):
                s = -1
            if s < 0 or s > 100:
                raise ValueError(f"product_value_score.score 必须 ∈ [0,100] (got {s})")
        else:
            raise ValueError("product_value_score 必须为对象")
        return self._report_from_llm(intent, parsed)

    @staticmethod
    def _invoke_llm(fn: Callable[..., Any], prompt: str) -> Any:
        """调用 llm_fn: 兼容 (prompt, operation) 与 (prompt) 两种签名。"""
        try:
            return fn(prompt, "product_intelligence")
        except TypeError:
            return fn(prompt)

    def build_llm_prompt(self, intent: ProductIntent) -> str:
        """LLM prompt 组装: JSON 契约 (8 模块结构 + 评分约束)。"""
        lines = [
            "你是 AI Software Factory 的产品智能分析引擎。只输出严格 JSON, 不要输出任何额外文本。",
            "任务: 基于产品意图, 输出完整产品智能分析报告 JSON:",
            '{',
            '  "industry_analysis": {"industry": str, "business_models": [str], "user_types": [str], "common_features": [str], "pain_points": [str], "tech_trends": [str]},',
            '  "competitor_analysis": {"competitors": [{"name": str, "category": str, "strengths": [str], "weaknesses": [str]}], "advantages": [str], "differentiation_opportunities": [str]},',
            '  "user_personas": [{"name": str, "description": str, "scenarios": [str], "pain_points": [str]}],',
            '  "requirement_conflicts": [{"description": str, "severity": "low|medium|high", "affected_fields": [str], "suggestion": str}],',
            '  "product_value_score": {"score": int(0-100), "user_value": str, "technical_value": str, "justification": str},',
            '  "mvp_plan": {"mvp": [str], "v2": [str], "future": [str]},',
            '  "business_analysis": {"revenue_models": [str], "cost_structure": [str], "user_acquisition": [str], "business_risks": [str]},',
            '  "market_analysis": {"market_size": str, "user_trends": [str], "opportunity_window": str}',
            "}",
            "约束: score 必须 ∈ [0,100]; severity 必须为 low/medium/high; 全部字段必须为字符串或字符串数组。",
            "产品意图 (JSON):",
            json.dumps(intent.to_dict(), ensure_ascii=False),
        ]
        return "\n".join(lines)

    def _report_from_llm(self, intent: ProductIntent, parsed: dict[str, Any]) -> ProductIntelligenceReport:
        """LLM 输出 → 报告 (逐模块 from_dict; 失败安全默认)。"""
        return ProductIntelligenceReport(
            product_name=_text(parsed.get("product_name")) or intent.name or "(未命名)",
            timestamp=_now_iso(),
            industry_analysis=IndustryAnalysis.from_dict(parsed.get("industry_analysis")),
            competitor_analysis=CompetitorAnalysis.from_dict(parsed.get("competitor_analysis")),
            user_personas=[
                UserPersona.from_dict(p) for p in (parsed.get("user_personas") or [])
                if isinstance(p, dict)
            ],
            requirement_conflicts=[
                RequirementConflict.from_dict(c) for c in (parsed.get("requirement_conflicts") or [])
                if isinstance(c, dict)
            ],
            product_value_score=ProductValueScore.from_dict(parsed.get("product_value_score")),
            mvp_plan=MvpPlan.from_dict(parsed.get("mvp_plan")),
            business_analysis=BusinessAnalysis.from_dict(parsed.get("business_analysis")),
            market_analysis=MarketAnalysis.from_dict(parsed.get("market_analysis")),
        )

    @classmethod
    def _parse_json(cls, raw: Any) -> Any:
        """结构化输出解析: str (裸 JSON / markdown fence) / dict / bytes。"""
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, bytes):
            try:
                raw = raw.decode("utf-8")
            except (UnicodeDecodeError, AttributeError):  # noqa: BLE001
                return raw
        if not isinstance(raw, str):
            return raw
        text = raw.strip()
        if not text:
            return raw
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        match = _JSON_OBJECT_RE.search(text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return raw
        return raw

    # ------------------------------------------------------------ 单模块 (deterministic)

    @staticmethod
    def _intent(product_intent: Any) -> ProductIntent:
        """入参归一: ProductIntent 原样; dict → from_dict (失败安全)。"""
        if isinstance(product_intent, ProductIntent):
            return product_intent
        return ProductIntent.from_dict(product_intent)

    def analyze_industry(self, product_intent: Any) -> IndustryAnalysis:
        """G1 行业理解 (deterministic): 关键词规则 + 模板。"""
        intent = self._intent(product_intent)
        name = _text(intent.name)
        problem = _text(intent.problem)
        user = _text(intent.user)
        features_text = " ".join(intent.core_features)
        corpus = f"{name} {problem} {features_text}"

        industry = _best_industry(corpus)
        models = _match_keywords(corpus + " " + user, _BUSINESS_MODEL_KEYWORDS)
        if not models:
            models = ["免费 + 增值服务 (Freemium) (模板兜底)"]
        user_types = _match_keywords(user, _USER_TYPE_KEYWORDS)
        if not user_types and user:
            user_types = [f"{user[:12]} 群体"]
        common_features = list(_COMMON_FEATURES.get(industry, [
            "核心业务闭环", "用户账户与数据管理", "基础设置与帮助",
        ]))
        pain_points = _split_pain_points(problem)
        trends = _match_keywords(corpus, _TECH_TREND_KEYWORDS)
        for trend in ("个性化体验", "移动化/多端协同"):
            if trend not in trends:
                trends.append(trend)
        return IndustryAnalysis(
            industry=industry,
            business_models=models,
            user_types=user_types,
            common_features=common_features,
            pain_points=pain_points,
            tech_trends=trends,
        )

    def analyze_competitor(self, product_intent: Any) -> CompetitorAnalysis:
        """G2 竞品分析 (deterministic): 行业原型 + 自身优势 + 差异化机会。"""
        intent = self._intent(product_intent)
        industry = _best_industry(
            f"{_text(intent.name)} {_text(intent.problem)} {' '.join(intent.core_features)}"
        )
        competitors = [
            dict(c) for c in _COMPETITOR_ARCHETYPES.get(industry, _GENERIC_COMPETITORS)
        ]
        advantages: list[str] = []
        if intent.core_features:
            advantages.append("核心功能聚焦: " + ", ".join(intent.core_features[:3]))
        if intent.platform:
            advantages.append(f"平台定位明确: {intent.platform}")
        if not advantages:
            advantages.append("需求场景清晰, 专注解决单一核心问题")
        differentiation: list[str] = []
        if intent.core_features:
            differentiation.append("围绕「" + intent.core_features[0] + "」做深做透, 形成垂直差异化")
        if industry:
            differentiation.append(f"针对 {industry} 细分人群提供更贴合场景的体验")
        differentiation.append("以更轻量的交付与更快的迭代速度抢占早期用户")
        return CompetitorAnalysis(
            competitors=competitors,
            advantages=advantages,
            differentiation_opportunities=differentiation,
        )

    def analyze_persona(self, product_intent: Any) -> list[UserPersona]:
        """G3 用户画像 (deterministic): user 字段拆分 → 1-3 画像。"""
        intent = self._intent(product_intent)
        user = _text(intent.user)
        problem = _text(intent.problem)
        pains = _split_pain_points(problem)
        if not user:
            return [UserPersona(
                name="目标用户 (未指定)",
                description="产品尚未明确目标用户, 建议补充用户画像。",
                scenarios=self._scenarios_for(intent),
                pain_points=pains,
            )]
        segments = [
            s.strip() for s in re.split(r"[、，,;；/和与及\s]+", user) if s.strip()
        ]
        if not segments:
            segments = [user]
        personas: list[UserPersona] = []
        for seg in segments[:3]:
            personas.append(UserPersona(
                name=f"{seg}用户",
                description=f"目标用户: {seg}; 关注「{problem[:24] if problem else '核心问题'}」的解决。",
                scenarios=self._scenarios_for(intent),
                pain_points=pains,
            ))
        return personas

    @staticmethod
    def _scenarios_for(intent: ProductIntent) -> list[str]:
        """使用场景 (deterministic): platform + 功能推导。"""
        platform = _text(intent.platform)
        scenarios: list[str] = []
        if platform:
            if "web" in platform or "网页" in platform or "pc" in platform.lower():
                scenarios.append("办公/PC 场景: 桌面浏览器内高效处理")
            if "mobile" in platform or "手机" in platform or "app" in platform.lower():
                scenarios.append("移动场景: 通勤/碎片时间随时使用")
            if "desktop" in platform.lower() or "桌面" in platform:
                scenarios.append("专业工作台场景: 长时间深度使用")
        if not scenarios:
            scenarios.append("日常场景: 按需打开, 快速完成任务")
        if intent.core_features:
            scenarios.append("围绕「" + intent.core_features[0] + "」的核心使用流程")
        return scenarios[:3]

    def detect_conflicts(self, product_intent: Any) -> list[RequirementConflict]:
        """G4 需求冲突检测 (deterministic 规则): 平台/功能/规模三类冲突。"""
        intent = self._intent(product_intent)
        platform = _text(intent.platform).lower()
        features = [str(f) for f in intent.core_features]
        features_text = " ".join(features)
        conflicts: list[RequirementConflict] = []

        def add(description: str, severity: str, fields: list[str], suggestion: str) -> None:
            conflicts.append(RequirementConflict(
                description=description, severity=severity,
                affected_fields=fields, suggestion=suggestion,
            ))

        # 规则 1: web + 离线功能 → high (设计验收口径)
        if "web" in platform and any(("离线" in f or "offline" in f.lower()) for f in features):
            add("Web 平台与「离线使用」功能冲突: 浏览器端离线能力受限",
                "high", ["platform", "core_features"],
                "建议明确离线范围 (如 PWA/本地缓存) 或改用桌面/移动端承载离线场景")
        # 规则 2: mobile + 桌面功能 → high
        if ("mobile" in platform or "手机" in platform) and any(
            ("桌面" in f or "desktop" in f.lower() or "PC版" in f) for f in features
        ):
            add("移动端与「桌面/PC 版」功能冲突: 平台定位矛盾",
                "high", ["platform", "core_features"],
                "建议收敛单一主平台, 或明确双端差异化分工")
        # 规则 3: 实时同步 + 离线 并存 → medium
        if any(("实时" in f or "同步" in f or "协作" in f) for f in features) and any(
            "离线" in f for f in features
        ):
            add("「实时同步/协作」与「离线使用」并存: 数据一致性设计复杂",
                "medium", ["core_features"],
                "建议定义同步策略 (最终一致/冲突合并), MVP 阶段优先其一")
        # 规则 4: desktop + 移动支付 → medium
        if ("desktop" in platform or "桌面" in platform) and any(
            ("支付" in f or "扫码" in f) for f in features
        ):
            add("桌面端与「移动支付/扫码」场景冲突: 支付链路需引导手机完成",
                "medium", ["platform", "core_features"],
                "建议补充扫码联动或改用网页支付聚合")
        # 规则 5: 功能重复 (归一化后相同) → low
        seen: dict[str, str] = {}
        for f in features:
            norm = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", str(f).lower())
            if not norm:
                continue
            if norm in seen:
                add(f"核心功能重复: 「{seen[norm]}」与「{f}」语义重叠",
                    "low", ["core_features"],
                    "建议合并为一个功能项, 避免需求冗余")
            else:
                seen[norm] = f
        # 规则 6: 功能数量过多 → low (范围风险)
        if len(features) > 8:
            add(f"核心功能多达 {len(features)} 项: 范围过大, MVP 交付风险高",
                "low", ["core_features"],
                "建议按 MVP 规划收敛前 1-2 个核心功能先行交付")
        return conflicts

    def score_value(self, product_intent: Any) -> ProductValueScore:
        """G5 价值评分 (deterministic): 完整性/特征/冲突扣分 → 0-100。"""
        intent = self._intent(product_intent)
        score = 30
        reasons: list[str] = ["基础分 30"]
        problem = _text(intent.problem)
        user = _text(intent.user)
        features = list(intent.core_features)
        if problem:
            score += 15
            reasons.append("问题清晰 +15")
        if user:
            score += 15
            reasons.append("目标用户明确 +15")
        if features:
            score += 15
            reasons.append(f"核心功能明确 ({len(features)} 项) +15")
            if len(features) >= 3:
                score += 5
                reasons.append("功能覆盖面较好 +5")
        if _text(intent.platform):
            score += 10
            reasons.append("平台定位明确 +10")
        if _text(intent.name):
            score += 5
            reasons.append("产品命名明确 +5")
        industry = _best_industry(f"{problem} {_text(intent.name)} {' '.join(features)}")
        if industry:
            score += 5
            reasons.append(f"行业方向可识别 ({industry}) +5")
        conflicts = self.detect_conflicts(intent)
        for c in conflicts:
            penalty = {"high": 10, "medium": 5, "low": 2}.get(c.severity, 2)
            score -= penalty
            reasons.append(f"冲突扣分 ({c.severity}) -{penalty}")
        score = max(0, min(100, score))
        user_value = (
            f"解决「{problem[:40]}」的核心痛点, 面向 {user or '目标用户'} 提供明确价值"
            if problem else "问题描述不完整, 用户价值待补充"
        )
        technical_value = (
            f"涉及 {len(features)} 项核心功能" + (f", 平台 {intent.platform}" if intent.platform else "")
            + (f", 含 {industry} 领域实践" if industry else "")
        )
        return ProductValueScore(
            score=score,
            user_value=user_value,
            technical_value=technical_value,
            justification="; ".join(reasons),
        )

    def plan_mvp(self, product_intent: Any) -> MvpPlan:
        """G6 MVP 规划 (deterministic): 前 1-2 功能→MVP, 其余→V2, 平台/扩展→Future。"""
        intent = self._intent(product_intent)
        features = [str(f) for f in intent.core_features]
        mvp: list[str] = []
        v2: list[str] = []
        future: list[str] = []
        for index, feature in enumerate(features):
            if index < 2:
                mvp.append(feature)
            elif any(kw in feature for kw in _FUTURE_KEYWORDS):
                future.append(feature)
            else:
                v2.append(feature)
        if not mvp:
            mvp.append("核心业务闭环 (最小可用流程)")
        if not features:
            v2.append("账户与数据管理")
            future.append("多端扩展 / 开放平台")
        return MvpPlan(mvp=mvp, v2=v2, future=future)

    def analyze_business(self, product_intent: Any) -> BusinessAnalysis:
        """G7 商业分析 (deterministic): 盈利模式/成本/获客/风险模板。"""
        intent = self._intent(product_intent)
        corpus = f"{_text(intent.name)} {_text(intent.problem)} {' '.join(intent.core_features)}"
        revenue = _match_keywords(corpus, _BUSINESS_MODEL_KEYWORDS)
        if not revenue:
            revenue = ["订阅制 / 增值服务 (模板兜底 — 需进一步验证付费意愿)"]
        costs = ["开发与人力成本", "服务器与云服务成本", "获客与推广成本", "运营与客服成本"]
        if any(("硬件" in f or "设备" in f or "IoT" in f) for f in intent.core_features):
            costs.append("硬件/物料成本")
        platform = _text(intent.platform)
        if platform:
            if "web" in platform:
                costs.append("渠道分成与平台合规成本 (应用内支付/审核)")
            elif "mobile" in platform or "手机" in platform:
                costs.append("应用商店分成与审核合规成本")
        acquisition: list[str] = []
        if "mobile" in platform or "app" in platform.lower() or "手机" in platform:
            acquisition.append("应用商店 ASO 与投放")
        if "web" in platform or "网页" in platform:
            acquisition.append("搜索引擎/内容 SEO")
        if "desktop" in platform or "桌面" in platform:
            acquisition.append("企业渠道与口碑转介绍")
        if not acquisition:
            acquisition.append("社交媒体与内容营销")
            acquisition.append("口碑与转介绍")
        if "社交" in corpus or "社区" in corpus:
            acquisition.append("社区运营与裂变传播")
        risks = ["同质化竞争激烈, 差异化不足则难获客"]
        if not revenue or "兜底" in revenue[0]:
            risks.append("变现路径不清晰, 依赖后续验证")
        if "支付" in " ".join(intent.core_features):
            risks.append("支付合规与资金安全要求高")
        if "企业" in _text(intent.user) or "B2B" in corpus:
            risks.append("B2B 销售周期长, 依赖标杆客户")
        return BusinessAnalysis(
            revenue_models=revenue,
            cost_structure=costs,
            user_acquisition=acquisition,
            business_risks=risks,
        )

    def analyze_market(self, product_intent: Any) -> MarketAnalysis:
        """G8 市场分析 (deterministic): 规模分级 + 趋势 + 机会窗口。"""
        intent = self._intent(product_intent)
        corpus = f"{_text(intent.name)} {_text(intent.problem)} {' '.join(intent.core_features)}"
        industry = _best_industry(corpus)
        market_size = _MARKET_SIZE_TIERS.get(industry, "细分/长尾市场: 需先验证目标人群规模与付费意愿")
        if industry:
            market_size += f" (行业判定: {industry})"
        trends = _match_keywords(corpus, _MARKET_TREND_KEYWORDS)
        for trend in ("个性化与智能化体验成为主流", "用户更看重数据自主与隐私"):
            if trend not in trends:
                trends.append(trend)
        conflicts = self.detect_conflicts(intent)
        has_high = any(c.severity == "high" for c in conflicts)
        if has_high:
            window = "机会窗口存在但需先解决高优先级冲突: 平台/功能定位收敛后可快速验证"
        else:
            window = "窗口期判断: 细分场景仍处早期, 先发者有机会建立心智; 建议 3 个月内完成 MVP 验证"
        return MarketAnalysis(
            market_size=market_size,
            user_trends=trends,
            opportunity_window=window,
        )

    # ------------------------------------------------------------ 持久化

    @staticmethod
    def _resolve_product_dir(workspace: Any, name: str) -> Path:
        """产品目录解析: workspace 本身是产品目录 → 原样; 否则 projects/<slug>。"""
        ws = Path(workspace or ".")
        if (ws / "product.json").is_file() or not (ws / "projects").is_dir():
            return ws
        slug = _slugify(name)
        if not slug:
            return ws
        return ws / "projects" / slug

    def save(self, workspace: Any, report: ProductIntelligenceReport) -> Optional[Path]:
        """落盘 product_intelligence.json (失败安全 → None)。

        workspace: 产品目录 (projects/<slug>) 或仓库根 (自动定位 projects/<slug>)。
        """
        try:
            target = self._resolve_product_dir(workspace, report.product_name)
            target.mkdir(parents=True, exist_ok=True)
            path = target / INTELLIGENCE_FILE_NAME
            path.write_text(
                json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            return path
        except Exception:  # noqa: BLE001 — 失败安全铁律: 落盘异常 → None 不抛
            return None

    def load(
        self,
        workspace: Any,
        product: Any = None,
    ) -> Optional[ProductIntelligenceReport]:
        """读取 product_intelligence.json (失败安全 → None)。

        product: ProductIntent (name 用于 slug 定位); 也可传 None (workspace 即产品目录)。
        """
        try:
            name = ""
            if isinstance(product, ProductIntent):
                name = product.name or ""
            elif isinstance(product, dict):
                name = str(product.get("name") or "")
            target = self._resolve_product_dir(workspace, name)
            path = target / INTELLIGENCE_FILE_NAME
            data = json.loads(path.read_text(encoding="utf-8"))
            report = ProductIntelligenceReport.from_dict(data)
            if report.product_name and name and report.product_name != name:
                report.product_name = name  # 名称对齐 (产品重命名场景, 失败安全)
            return report
        except Exception:  # noqa: BLE001 — 失败安全铁律: 读取异常 → None 不抛
            return None

    # ------------------------------------------------------------ 渲染

    @staticmethod
    def to_markdown(report: ProductIntelligenceReport) -> str:
        """报告 → 用户可读 Markdown (完整 8 模块)。"""
        lines = [
            f"# 产品智能分析: {report.product_name}",
            f"> 分析时间: {report.timestamp or _now_iso()}",
            "",
            "## 1. 行业理解",
            f"- 行业: {report.industry_analysis.industry or '(未识别)'}",
            f"- 商业模式: {_join(report.industry_analysis.business_models)}",
            f"- 用户类型: {_join(report.industry_analysis.user_types)}",
            f"- 常见功能: {_join(report.industry_analysis.common_features)}",
            f"- 痛点: {_join(report.industry_analysis.pain_points)}",
            f"- 技术趋势: {_join(report.industry_analysis.tech_trends)}",
            "",
            "## 2. 竞品分析",
        ]
        comp = report.competitor_analysis
        if comp.competitors:
            for c in comp.competitors:
                lines.append(f"- **{c.get('name') or '(未命名)'}** ({c.get('category') or ''}): "
                             f"优势 {_join(c.get('strengths'))}; 劣势 {_join(c.get('weaknesses'))}")
        else:
            lines.append("- (暂无竞品数据)")
        lines.append(f"- 自身优势: {_join(comp.advantages)}")
        lines.append(f"- 差异化机会: {_join(comp.differentiation_opportunities)}")
        lines += ["", "## 3. 用户画像"]
        if report.user_personas:
            for p in report.user_personas:
                lines.append(f"- **{p.name}**: {p.description} 场景: {_join(p.scenarios)}")
        else:
            lines.append("- (暂无画像)")
        lines += ["", "## 4. 需求冲突检测"]
        if report.requirement_conflicts:
            for c in report.requirement_conflicts:
                lines.append(f"- [{c.severity}] {c.description} → 建议: {c.suggestion}")
        else:
            lines.append("- 未检测到明显需求冲突")
        value = report.product_value_score
        lines += [
            "", "## 5. 价值评分",
            f"- 评分: **{value.score}/100**",
            f"- 用户价值: {value.user_value}",
            f"- 技术价值: {value.technical_value}",
            f"- 理由: {value.justification}",
            "", "## 6. MVP 规划",
            f"- MVP: {_join(report.mvp_plan.mvp)}",
            f"- V2: {_join(report.mvp_plan.v2)}",
            f"- Future: {_join(report.mvp_plan.future)}",
        ]
        biz = report.business_analysis
        lines += [
            "", "## 7. 商业分析",
            f"- 盈利模式: {_join(biz.revenue_models)}",
            f"- 成本结构: {_join(biz.cost_structure)}",
            f"- 用户获取: {_join(biz.user_acquisition)}",
            f"- 商业风险: {_join(biz.business_risks)}",
        ]
        market = report.market_analysis
        lines += [
            "", "## 8. 市场分析",
            f"- 市场规模: {market.market_size}",
            f"- 用户趋势: {_join(market.user_trends)}",
            f"- 机会窗口: {market.opportunity_window}",
        ]
        return "\n".join(lines)

    @staticmethod
    def to_market_markdown(report: ProductIntelligenceReport) -> str:
        """市场分析单模块 Markdown (CLI product_market 输出)。"""
        market = report.market_analysis
        return (
            f"# 市场分析: {report.product_name}\n\n"
            f"- 市场规模: {market.market_size}\n"
            f"- 用户趋势: {_join(market.user_trends)}\n"
            f"- 机会窗口: {market.opportunity_window}\n"
        )

    @staticmethod
    def to_persona_markdown(report: ProductIntelligenceReport) -> str:
        """用户画像单模块 Markdown (CLI product_persona 输出)。"""
        lines = [f"# 用户画像: {report.product_name}", ""]
        if report.user_personas:
            for p in report.user_personas:
                lines.append(f"## {p.name}")
                lines.append(f"- 描述: {p.description}")
                lines.append(f"- 使用场景: {_join(p.scenarios)}")
                lines.append(f"- 痛点: {_join(p.pain_points)}")
                lines.append("")
        else:
            lines.append("(暂无画像)")
        return "\n".join(lines)

    @staticmethod
    def to_mvp_markdown(report: ProductIntelligenceReport) -> str:
        """MVP 规划单模块 Markdown (CLI product_mvp 输出)。"""
        return (
            f"# MVP 规划: {report.product_name}\n\n"
            f"- MVP: {_join(report.mvp_plan.mvp)}\n"
            f"- V2: {_join(report.mvp_plan.v2)}\n"
            f"- Future: {_join(report.mvp_plan.future)}\n"
        )

    @staticmethod
    def to_value_markdown(report: ProductIntelligenceReport) -> str:
        """价值评分单模块 Markdown (CLI product_value 输出)。"""
        value = report.product_value_score
        return (
            f"# 价值评分: {report.product_name}\n\n"
            f"- 评分: **{value.score}/100**\n"
            f"- 用户价值: {value.user_value}\n"
            f"- 技术价值: {value.technical_value}\n"
            f"- 理由: {value.justification}\n"
        )


def _join(items: Any) -> str:
    """列表 → 顿号分隔文本 (None/空 → '—')。"""
    if not items:
        return "—"
    if isinstance(items, str):
        return items
    return "、".join(str(x) for x in items if str(x).strip())
