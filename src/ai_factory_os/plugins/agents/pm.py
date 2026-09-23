"""src/ai_factory_os/plugins/agents/pm.py — PM Agent 执行 (Sprint 8 S8-001)。

设计依据 (sprint8-architecture.md §2 ① PM Agent / §4 Workflow 接入):
```
输入: Idea (自然语言; stage input 可无 artifact 或 idea artifact)
输出: Product Artifact (7 节): market_analysis / user_persona / user_journey /
      problem_statement / feature_list / mvp_scope / user_stories
实现: roles.py PM executable + pm.py (PMAgent: 结构化 prompt → Product Artifact)
验证: CONTRACTS product 类型 (required fields + 规则; 失败 → INVALID 响亮)
接入: Workflow stage "product" (role_ref=pm) — build_pm_executor 适配器
```

实现 (KISS, 复用优先):
- 生成: 仅当有 Idea 才调 Provider (生产 DeepSeek v4-pro; 测试注入 mock);
  LLM 输出结构化 JSON → ProductArtifact (宽容解析: markdown 围栏剥离/整体
  解析/子串回退; 缺核心字段 → 响亮拒绝 — 不伪造产品分析)。
- Idea 解析链 (executor): context inputs 中 idea artifact (metadata.idea)
  > PMAgent 构造绑定 idea — 与架构 §2 一致 (stage input 可无 artifact)。
- 本地校验: PMAgent 内做同源字段校验 (7 节非空/结构, 与 org CONTRACTS
  product 规则一致; exec 零 import factory-org — Removal Isolation, 同
  tester.py 约束); Workflow 侧经 Runner 自动注册再走 CONTRACTS product
  校验 (契约失败 → INVALID → stage FAILED → workflow FAILED)。

约束 (S8-001):
- 只扩展, 不重写: 不 import factory-org; 不实现 UX/UI/Architect/Release
  Agent; 零明文密钥。
- 诚实: 无 provider → ProductManagerError 响亮; 输出不可解析/缺字段 →
  响亮拒绝 (不假装生成成功); ROLE_OUTPUT_TYPES 默认 (product-manager→prd)
  保持向后兼容 S7-005 demo, 本模块显式声明 artifact_type="product"。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field as dc_field
from typing import Any, Callable

from ai_factory_os.contracts.llm.provider import ProviderRequest

#: product 契约字段 (与 org CONTRACTS product required_fields 同源; 本地
#: 校验 = exec 侧同规则, Removal Isolation 下与 org 侧保持一致)
PRODUCT_FIELDS: tuple[str, ...] = (
    "market_analysis",
    "user_persona",
    "user_journey",
    "problem_statement",
    "feature_list",
    "mvp_scope",
    "user_stories",
)

#: mvp_scope 必含键 (与 org CONTRACTS product validation_rules 同源)
_MVP_SCOPE_KEYS: tuple[str, ...] = ("in", "out")


class ProductManagerError(Exception):
    """PM Agent 业务错误 (缺 idea / provider 缺失 / 输出不可解析 / 缺字段)。"""

    __test__ = False  # pytest 收集豁免 (Test* 前缀类名误匹配)


# ------------------------------------------------------------------ 模型


@dataclass(frozen=True)
class ProductArtifact:
    """结构化 Product Artifact (product 契约载荷; 字段 = PRODUCT_FIELDS)。

    feature_list: 功能清单 (非空 list); mvp_scope: MVP 范围 dict (必含
    in/out 边界); user_stories: 用户故事 (list, 每项 str 或 as-a/i-want/
    so-that dict — 宽容, 契约只要求非空 list)。
    """

    market_analysis: str
    user_persona: str
    user_journey: str
    problem_statement: str
    feature_list: list[Any] = dc_field(default_factory=list)
    mvp_scope: dict[str, Any] = dc_field(default_factory=dict)
    user_stories: list[Any] = dc_field(default_factory=list)
    # ★ 2026-09-21（需求→PRD 的门, 硬契约）: 出处表 —— 每条条目 → 需求里的逐字片段。
    #   注意: 必须是**正式字段**, 否则 to_dict() 会把它丢掉（实测踩过 ✗）
    traces: dict[str, Any] = dc_field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """契约载荷 (7 节全字段 + 出处表)。"""
        d = {f: getattr(self, f) for f in PRODUCT_FIELDS}
        d["traces"] = dict(self.traces or {})
        return d

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ProductArtifact":
        """宽容解析 (LLM 输出): 缺核心字段/空节 → ProductManagerError 响亮
        (不伪造产品分析); 未知字段忽略; 结构经本地校验 (同 CONTRACTS 规则)。"""
        if not isinstance(raw, dict):
            raise ProductManagerError(
                f"product artifact must be a dict, got {type(raw).__name__}"
            )
        missing = [f for f in PRODUCT_FIELDS if f not in raw]
        if missing:
            raise ProductManagerError(
                f"product artifact missing required fields: {', '.join(missing)}"
            )
        errors = _local_validate(raw)
        if errors:
            raise ProductManagerError(
                f"product artifact invalid: {'; '.join(errors)}"
            )
        return cls(
            market_analysis=str(raw["market_analysis"]).strip(),
            user_persona=str(raw["user_persona"]).strip(),
            user_journey=str(raw["user_journey"]).strip(),
            problem_statement=str(raw["problem_statement"]).strip(),
            feature_list=list(raw["feature_list"]),
            mvp_scope=dict(raw["mvp_scope"]),
            user_stories=list(raw["user_stories"]),
        )


def _local_validate(payload: dict[str, Any]) -> list[str]:
    """product 契约本地校验 (exec 侧; 规则与 org CONTRACTS product 同源)。

    返回失败信息列表 (空 = 通过); 缺失字段由调用方 (from_dict) 先查,
    本函数只校验已存在字段的规则 (str 非空 / list 非空 / mvp_scope dict
    含 in/out)。
    """
    errors: list[str] = []
    for f in ("market_analysis", "user_persona", "user_journey", "problem_statement"):
        v = payload.get(f)
        if not isinstance(v, str) or not v.strip():
            errors.append(f"{f}: expected non-empty str")
    fl = payload.get("feature_list")
    if not isinstance(fl, list) or not fl:
        errors.append("feature_list: expected non-empty list")
    scope = payload.get("mvp_scope")
    if not isinstance(scope, dict) or not scope:
        errors.append("mvp_scope: expected non-empty dict")
    elif not all(k in scope for k in _MVP_SCOPE_KEYS):
        errors.append("mvp_scope: missing required keys 'in'/'out'")
    us = payload.get("user_stories")
    if not isinstance(us, list) or not us:
        errors.append("user_stories: expected non-empty list")
    # ★ 2026-09-21 硬契约（Founder 选 A'）: 出处表必填 —— 缺了就走 develop 的反馈重试闭环,
    #   逼模型给出"每条条目 ↔ 用户想法里的逐字片段"; 否则 PRD 里会混进用户没要过的功能。
    traces = payload.get("traces") or payload.get("feature_traces")
    if not isinstance(traces, dict) or not traces:
        errors.append("traces: expected non-empty dict (每个 feature_list / user_stories / "
                      "mvp_scope.in 条目 → 用户想法里的**逐字片段**, 至少 6 个字)")
    return errors


def _items_of(payload: dict[str, Any]) -> list[tuple[str, int, Any]]:
    """PRD 里"会自造"的三处清单: (节名, 下标, 条目)。"""
    out: list[tuple[str, int, Any]] = []
    for i, x in enumerate(payload.get("feature_list") or []):
        out.append(("feature_list", i, x))
    for i, x in enumerate(payload.get("user_stories") or []):
        out.append(("user_stories", i, x))
    scope = payload.get("mvp_scope") if isinstance(payload.get("mvp_scope"), dict) else {}
    for i, x in enumerate(scope.get("in") or []):
        out.append(("mvp_scope.in", i, x))
    return out


def enforce_requirement_traces(payload: dict[str, Any], requirement: str) -> dict[str, Any]:
    """★ 需求 → PRD 的门（Founder 选 B, 后按 A 做硬: 覆盖每一节 + 硬契约）。

    实测病: PRD 制品里就已经有用户没要过的东西（登录/通知/补课/爽约 ✗）—— 污染从这一环开始,
      下游放大到 42/199 个任务。
    判据（**可核对, 不靠模型自觉**）: 三处清单（feature_list / user_stories / mvp_scope.in）每一项都要在
      `traces`（或 feature_traces）里有一条**逐字片段**（≥6 字）, 该片段必须原样出现在用户需求原话里。
      键做**宽松匹配**（键是条目文本的子串或反之, 归一化后比）—— 避免因抄写差异误杀。
      · 有 traces 表: 给不出/编的 ⇒ 该项**移出**, 进 out_of_scope_suggestions（给人看, 不做）
      · 没有 traces 表（模型不配合/老载荷）⇒ **不移出**, 只用"与需求原话最长公共子串 <3"**标记**可疑的
    返回 {"checked","kept","moved","flagged","skipped"}
    """
    from difflib import SequenceMatcher as _SM

    from ai_factory_os.services.work.decomposition import _norm

    out: dict[str, Any] = {"checked": 0, "kept": 0, "moved": [], "flagged": [], "skipped": False}
    items = _items_of(payload)
    if not items:
        return out
    req = _norm(requirement)
    # ★ 2026-09-21 修（Founder 实测的重大误杀 ✗✗）: 需求是**在命令行里说的**
    #   （`factory chain "社区图书借还小程序: …"`）⇒ 会话里没有这句原话 ⇒ 门拿不到参照却照样过滤
    #   ⇒ 把真需求（扫码借还/查馆藏/逾期提醒…）当"凭空发明"移出 21 条 ✗
    #   ⇒ 拿不到需求原文（太短/为空）就**不过滤**（宁可放过, 不误杀）, 并如实说明。
    if len(req) < 12:
        out["skipped"] = True
        out["why"] = "拿不到需求原文（会话里没有这句需求）⇒ 本次不过滤（宁可放过, 不误杀）"
        return out
    raw = payload.get("traces") or payload.get("feature_traces")
    traces = {_norm(k): str(v).strip() for k, v in (raw or {}).items()} if isinstance(raw, dict) else {}

    def _text(x: Any) -> str:
        return str(x) if isinstance(x, str) else json.dumps(x, ensure_ascii=False)

    def _cite_for(text: str) -> str:
        tn = _norm(text)
        for k, v in traces.items():
            if not k:
                continue
            if k in tn or tn in k:
                return v
        return ""

    # ★ 2026-09-21（Founder 选 A'，最终版）: **自己从需求原话里给每条找出处** —— 不靠模型自觉。
    #   实测: 让模型填 traces ⇒ 它交回 {}（空表 ✗）; 靠"标记"又太软。正解 = 变**可核对**:
    #     条目与需求原话的最长公共子串 ≥2 字 ⇒ 记为它的出处（该片段**必然**是需求原话, 天然可核对 ✓）
    #     连 2 个字都对不上 ⇒ 需求里找不到依据 ⇒ 该条移出（真正的"凭空发明"就长这样）
    #   ★ 诚实边界: 这是文本判据 —— 拦得住"与需求毫无文字交集的凭空发明"; 对"换了说法的自造"仍会放过 ✗
    dropped: dict[str, set[int]] = {}
    for section, idx, item in items:
        out["checked"] += 1
        text = _text(item)
        tn = _norm(text)
        cite = _cite_for(text)
        if not cite and req and tn:
            m = _SM(None, tn, req).find_longest_match(0, len(tn), 0, len(req))
            if m.size >= 2:
                cite = "[自动] " + req[m.b : m.b + m.size]
        cn = _norm(cite.replace("[自动]", ""))
        if len(cn) >= 2 and cn in req:
            out["kept"] += 1
            continue
        out["moved"].append({"section": section, "item": text[:120],
                             "why": ("需求原话里找不到依据（连 2 个字都对不上 ⇒ 凭空发明）"
                                     if not cite else f"出处「{cite[:40]}」查不到")})
        dropped.setdefault(section, set()).add(idx)

    if dropped:
        payload["feature_list"] = [x for i, x in enumerate(payload.get("feature_list") or [])
                                   if i not in dropped.get("feature_list", set())]
        payload["user_stories"] = [x for i, x in enumerate(payload.get("user_stories") or [])
                                   if i not in dropped.get("user_stories", set())]
        scope = payload.get("mvp_scope") if isinstance(payload.get("mvp_scope"), dict) else {}
        if scope:
            scope["in"] = [x for i, x in enumerate(scope.get("in") or [])
                           if i not in dropped.get("mvp_scope.in", set())]
            payload["mvp_scope"] = scope
        payload["out_of_scope_suggestions"] = list(payload.get("out_of_scope_suggestions") or []) + out["moved"]
    if out["flagged"]:
        payload["_suspected_self_added"] = out["flagged"]
    out["skipped"] = not bool(traces)
    return out


# ------------------------------------------------------------------ prompt


#: PM Agent prompt (想法 → 产品分析 7 节; 生产 provider = DeepSeek v4-pro)
#: S8-005 强化: 显式声明每节必须为实质内容 (str 非空 / list 非空 /
#: mvp_scope 含 in/out), 禁止省略/留空 — 真实 v4-pro 曾输出缺 3 节
#: (user_persona/user_journey/problem_statement 为空), 契约失败由
#: develop 反馈重试闭环兜底 (见 _build_retry_prompt)。
_PM_AGENT_PROMPT = (
    "你是一名 Product Manager (产品经理)。把下面的用户想法 (Idea) 转化为结构化"
    "产品分析产物 (Product Artifact), 覆盖 7 节: \n"
    "- market_analysis: 市场分析 (目标市场/竞争/机会)\n"
    "- user_persona: 用户画像 (目标用户/特征/痛点)\n"
    "- user_journey: 用户旅程 (关键场景/步骤/触点)\n"
    "- problem_statement: 问题定义 (核心问题/影响)\n"
    "- feature_list: 功能清单 (数组, 每项一个功能 —— ★ 每项**必须**能在用户想法里找到原话依据)\n"
    "- traces: **必填** 出处表 (对象: {{你写的条目原文 → 用户想法里的**逐字片段**(至少 6 个字, 照抄)}};"
    " 必须覆盖 feature_list 的**每一条**、user_stories 的**每一条**、mvp_scope.in 的**每一条**)\n"
    "  ★ 凡是在用户想法里**找不到原话依据**的东西, 一律**不要**写进 feature_list / user_stories /"
    " mvp_scope.in（放到 out_of_scope_suggestions 里另列）—— 范围由用户定, 不许自己加。\n"
    "- out_of_scope_suggestions: 建议但**用户没提**的东西 (数组; 可空)\n"
    "- mvp_scope: MVP 范围 (对象, 必含 in/out 两个数组: 范围内/范围外)\n"
    "- user_stories: 用户故事 (数组, 每项含 as-a/i-want/so-that)\n\n"
    "用户想法:\n{idea}\n\n"
    "输出 JSON 对象, 7 节字段必须全部存在且为实质内容: "
    "market_analysis / user_persona / user_journey / problem_statement "
    "为非空字符串, feature_list / user_stories 为非空数组, mvp_scope 为"
    "含 in/out 两个数组的对象。每一节都必须认真填写, 禁止省略任何一节, "
    "禁止留空或写占位文字。必须是纯 JSON 对象: 禁止 markdown 代码块围栏 "
    "(```), 禁止注释, 禁止任何前后说明文字; 输出必须以 {{ 开始、以 }} 结束。"
)


# ------------------------------------------------------------------ 解析


def _strip_fences(content: str) -> str:
    """剥 markdown 代码块围栏 (``` / ```json 等; 前导/尾部多行均剥)。"""
    lines = content.strip().lstrip("\ufeff").splitlines()
    while lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    while lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _balanced_json_candidates(text: str) -> list[str]:
    """扫描所有顶层平衡 {...} 子串 (字符串字面量内的大括号不计数)。

    返回按出现顺序的候选列表 — 覆盖前后夹带说明文字 / 围栏残留 (如
    "}```" 同行) / 尾部散文含花括号等模型真实输出形态 (S8-005 demo7
    实测: 输出 12579/9953 chars 但整体解析与首尾子串回退全失败)。
    """
    candidates: list[str] = []
    i, n = 0, len(text)
    while i < n:
        if text[i] != "{":
            i += 1
            continue
        depth = 0
        in_str = False
        esc = False
        j = i
        while j < n:
            ch = text[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(text[i : j + 1])
                    i = j + 1
                    break
            j += 1
        else:
            i += 1  # 该起点无闭合 → 放弃, 找下一个 {
    return candidates


def _try_parse_json(candidate: str) -> Any:
    """单候选解析: strict=False 容忍字符串内控制字符; 失败 → 去尾逗号再试。"""
    try:
        return json.loads(candidate, strict=False)
    except ValueError:
        pass
    # JSON5 式尾逗号 (v4-pro 偶发): ",}" / ",]" → 去掉再试 (对合法 JSON 无副作用)
    cleaned = re.sub(r",\s*([}\]])", r"\1", candidate)
    if cleaned != candidate:
        try:
            return json.loads(cleaned, strict=False)
        except ValueError:
            pass
    return None


def _extract_json(content: str) -> Any:
    """宽容 JSON 提取 (S8-005 强化): 剥围栏 → 整体解析 → 多候选回退。"""
    text = _strip_fences(content)
    # 1) 整体解析 (最常见路径, 省扫描)
    parsed = _try_parse_json(text)
    if parsed is not None:
        return parsed
    # 2) 多候选回退: 依次尝试每个平衡 {...} 子串
    for candidate in _balanced_json_candidates(text):
        parsed = _try_parse_json(candidate)
        if parsed is not None:
            return parsed
    raise ProductManagerError("PM output is not valid JSON")


def _parse_product(content: str) -> ProductArtifact:
    """LLM 输出 → ProductArtifact (宽容解析; 空/垃圾 → ProductManagerError)。"""
    data = _extract_json(content)
    if not isinstance(data, dict):
        raise ProductManagerError(
            "PM output must be a JSON object (product artifact 7 节)"
        )
    return ProductArtifact.from_dict(data)


def _build_retry_prompt(original_prompt: str, error: ProductManagerError) -> str:
    """契约失败反馈 (生产自愈闭环, DevTestLoop 失败反馈模式移植): 原始
    prompt + 校验错误明细 + 修正要求 → 重试轮输入。

    真实 v4-pro 曾输出 7 节缺 3 节 (字段存在但为空 str) — 模型不知道契约
    校验规则, 反馈具体缺失/空字段比重复原始 prompt 更有效 (S8-005 修复)。
    """
    return (
        original_prompt
        + "\n\n你的上一次输出未通过产品契约校验, 错误如下:\n"
        + str(error)
        + "\n请修正后重新输出完整 JSON: 7 节字段必须全部存在且为实质内容"
        " (str 节非空字符串、list 节非空数组、mvp_scope 含 in/out 数组), "
        "特别注意补齐所有缺失或为空的节。禁止省略任何一节。"
        " 必须输出修正后的完整 JSON (纯 JSON 对象, 以 { 开始、以 } 结束), "
        "禁止 markdown 代码块围栏 (```)、禁止注释、禁止任何说明文字。"
    )


# ------------------------------------------------------------------ PM Agent


class PMAgent:
    """PM Agent: Idea (自然语言) → 结构化 Product Artifact (7 节)。

    构造:
    - provider: ProviderInterface (产品分析 LLM; 生产 DeepSeek v4-pro,
      测试注入 mock; None → develop 时 ProductManagerError 响亮)。
    - idea: 可选默认想法 (Workflow executor 场景 context 无 idea artifact
      时的回退输入; 架构 §2: stage input 可无 artifact)。

    方法:
    - develop(idea=None) → ProductArtifact: LLM 生成 + 本地校验
      (Idea 解析链: 方法参数 > 构造绑定 > ProductManagerError)。
    """

    __test__ = False  # pytest 收集豁免 (Test* 前缀类名误匹配)

    def __init__(
        self,
        provider: Any = None,
        *,
        idea: str = "",
        max_tokens: int = 8192,
        max_retries: int = 1,
    ) -> None:
        self._provider = provider
        self._idea = (idea or "").strip()
        # S8-005: v4-pro reasoning 消耗大, 4096 曾截断致输出缺节 → 8192
        self._max_tokens = int(max_tokens)
        # S8-005: 契约失败 → 带错误反馈重试 ≤max_retries 次 (生产自愈)
        self._max_retries = int(max_retries)

    @property
    def provider(self) -> Any:
        return self._provider

    @property
    def idea(self) -> str:
        return self._idea

    def set_idea(self, idea: str) -> "PMAgent":
        """绑定/替换默认想法 (executor 复用同一 agent 实例多轮)。"""
        self._idea = (idea or "").strip()
        return self

    def develop(self, idea: str | None = None) -> ProductArtifact:
        """Idea → Product Artifact (LLM 结构化输出 + 本地契约校验)。

        provider 缺失 / 调用失败 / 输出不可解析 / 缺字段 → ProductManagerError
        响亮 (不假装生成成功); 输出再经 Workflow Runner CONTRACTS product
        校验 (org 侧), 失败 → INVALID → stage FAILED。

        S8-005 生产自愈 (产品级闭环, 非一次性 hack): 契约校验失败 →
        将错误明细反馈给 LLM (prompt 追加缺失/空字段) 重试 ≤max_retries 次
        (DevTestLoop 失败反馈模式移植); 重试耗尽仍失败 → 响亮 (错误含
        最后一次解析失败明细, 诚实记录)。
        """
        idea_text = (idea or "").strip() or self._idea
        if not idea_text:
            raise ProductManagerError(
                "idea required (PMAgent 构造绑定 或 develop(idea) 显式传入)"
            )
        if self._provider is None:
            raise ProductManagerError(
                "product analysis requires a provider (仅 DeepSeek v4-pro; 测试注入 mock)"
            )
        prompt = _PM_AGENT_PROMPT.format(idea=idea_text[:4000])
        last_error: ProductManagerError | None = None
        for attempt in range(self._max_retries + 1):
            response = self._provider.generate(
                ProviderRequest(task_context=prompt, max_tokens=self._max_tokens)
            )
            if not response.ok or not (response.content or "").strip():
                raise ProductManagerError(
                    f"product analysis failed: {response.error or 'empty provider response'}"
                )
            try:
                return _parse_product(response.content)
            except ProductManagerError as exc:
                last_error = exc
                if attempt < self._max_retries:
                    # 契约失败 → 带错误明细反馈重试 (生产自愈闭环)
                    prompt = _build_retry_prompt(prompt, exc)
        raise ProductManagerError(
            f"product analysis failed after {self._max_retries + 1} attempts: "
            f"{last_error}"
        )


# ------------------------------------------------------------------ Workflow 接入


def build_pm_executor(
    pm: PMAgent,
) -> Callable[[Any, dict[str, Any]], dict[str, Any]]:
    """PMAgent → Workflow executor 适配器 (product stage, role_ref=pm)。

    返回 dict 契约 (S7-003 _register_outputs 消费):
    - artifact_type: "product" (显式声明; ROLE_OUTPUT_TYPES 默认 prd 保持
      向后兼容, 不覆盖)
    - ref: 产物引用 (file:///docs/product.json)
    - metadata: Product Artifact 契约载荷 (7 节; Runner 自动注册 →
      CONTRACTS product 校验 → VALIDATED / INVALID → stage FAILED)

    Idea 解析链 (架构 §2): context inputs 中 idea artifact (metadata.idea)
    > PMAgent 构造绑定 idea; 均无 → ProductManagerError (stage FAILED —
    诚实, 不臆造输入)。
    """

    def executor(stage: Any, context: dict[str, Any]) -> dict[str, Any]:
        idea = _idea_from_context(context) or pm.idea
        if not idea:
            raise ProductManagerError(
                "pm executor needs an idea "
                "(context idea artifact metadata.idea 或 PMAgent 绑定 idea)"
            )
        artifact = pm.develop(idea)
        return {
            "artifact_type": "product",
            "ref": "file:///docs/product.json",
            "metadata": artifact.to_dict(),
        }

    return executor


def _idea_from_context(context: dict[str, Any]) -> str | None:
    """从 executor context 的 idea 产物 metadata 解析想法 (idea artifact 契约)。

    兼容宽口径: type 为 "idea" 的产物, metadata.idea (或 content) 为首选;
    任何产物 metadata.idea 也可 (未显式 idea 类型的宽松路径 — KISS)。
    """
    for inp in context.get("inputs", []):
        if not isinstance(inp, dict):
            continue
        meta = inp.get("metadata") or {}
        if not isinstance(meta, dict):
            continue
        if inp.get("type") == "idea":
            idea = meta.get("idea") or meta.get("content")
            if idea:
                return str(idea)
    for inp in context.get("inputs", []):
        if not isinstance(inp, dict):
            continue
        meta = inp.get("metadata") or {}
        if isinstance(meta, dict) and meta.get("idea"):
            return str(meta["idea"])
    return None
