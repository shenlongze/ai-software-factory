"""src/legacy/factory-exec/exec/architect.py — Architect Agent 执行 (Sprint 8 S8-003)。

设计依据 (sprint8-architecture.md §2 ③ Architect / §3 Artifact 流转 +
S8-002 report §S8-003 接入说明):
```
输入: Product Artifact (7 节) + UX/UI Artifact (7 节) — 双输入强校验
      (Architect 消费重点: product 的 feature_list/mvp_scope/user_stories
       → 模块划分与任务拆分; ux_ui 的 information_architecture/
      screen_specifications/component_definition/design_tokens → 架构
      分层/API 数据形状/UI 层实现约束)
输出: Design Artifact (7 节): system_architecture / technical_stack /
      database_design / api_design / frontend_architecture /
      backend_architecture / task_breakdown
实现: roles.py Architect executable + architect.py (ArchitectAgent)
验证: CONTRACTS design 类型 (7 节必填 + 规则; 失败 → INVALID 响亮)
接入: Workflow stage "architecture" (role_ref=architect) —
      build_arch_executor 适配器
```

实现 (KISS, 复用 pm.py/uxui.py 模式):
- 双输入强校验: ArchitectAgent 构造时 product + ux_ui 必须同时存在 (任一
  缺失 → ArchitectError 响亮) — 禁止脱离输入独立生成 (架构师不能凭空设计)。
  set_product/set_ux_ui 同样拒绝空输入 (不变量全入口生效)。
- 生成: 仅当双输入齐备才调 Provider (生产 DeepSeek v4-pro; 测试注入 mock);
  LLM 输出结构化 JSON → DesignArtifact (宽容解析: markdown 围栏剥离/整体
  解析/子串回退; 缺核心字段/空节 → 响亮拒绝 — 不伪造技术设计)。
- 本地校验: ArchitectAgent 内做同源字段校验 (7 节非空/结构 + api_design
  必含 endpoints + task_breakdown 深度结构: 每项含 module/task/api_contract/
  ui_guidance — 与 org CONTRACTS design 规则一致; exec 零 import
  factory-org — Removal Isolation, 同 pm/uxui 约束)。
- artifact_refs (强引用): build_arch_executor 从 executor context inputs
  解析 product/ux_ui 产物 id, 输出 metadata 带 "artifact_refs":
  [product_id, ux_ui_id] — 设计产物显式引用输入产物 (审计/溯源); context
  缺任一输入产物 → ArchitectError (stage FAILED — 诚实, 不脱离输入独立
  生成, 即使 agent 构造已绑定 payload)。

约束 (S8-003):
- 只扩展, 不重写: 不 import factory-org; 不实现 Release Agent (S8-004);
  零明文密钥; 不修改 Workflow/Artifact 核心。
- 诚实: 无 provider / 缺双输入 → ArchitectError 响亮; 输出不可解析/缺字段
  → 响亮拒绝 (不假装生成成功); ROLE_OUTPUT_TYPES 默认 (architect→design)
  保持向后兼容, 本模块显式声明 artifact_type="design"。
"""

from __future__ import annotations

import sys

import json
import re
from dataclasses import dataclass, field as dc_field
from typing import Any, Callable

from ai_factory_os.infrastructure.llm.provider import ProviderRequest

#: design 契约字段 (与 org CONTRACTS design required_fields 同源; 本地
#: 校验 = exec 侧同规则, Removal Isolation 下与 org 侧保持一致)
DESIGN_FIELDS: tuple[str, ...] = (
    "system_architecture",
    "technical_stack",
    "database_design",
    "api_design",
    "frontend_architecture",
    "backend_architecture",
    "task_breakdown",
)

#: api_design 必含键 (与 org CONTRACTS design validation_rules 同源;
#: endpoints = API 约定, 供 S8-005 Developer 消费)
_API_DESIGN_KEYS: tuple[str, ...] = ("endpoints",)

#: 每个 endpoint 必含键 (API 约定深度结构: 方法/路径/契约描述)
_ENDPOINT_KEYS: tuple[str, ...] = ("method", "path", "contract")

#: task_breakdown 每项必含键 (Developer 消费准备: 模块 / 技术任务 /
#: API 约定 / UI 实现指导 — S8-005 Developer 消费点)
#: ★ 2026-09-21 加 "acceptance"（Founder 纠正: "任务拆解就不够细啊"）。
#:   背景: 原契约是「每项 = 一个 module + 一个 task」⇒ 天生 1 模块 1 任务（实测 13 模块→13 叶,
#:   每叶 3~7 件事）⇒ **"拆解"这一环其实没拆**（expand.py 自述也承认 task_breakdown 是平的）。
#:   现在: 每个 task 必须是【原子任务】（一工程师一次做完 + 可独立验收），同一 module 可多次出现,
#:   且 acceptance 必填 —— 契约层就不允许"粗叶"出生。
_TASK_KEYS: tuple[str, ...] = ("module", "task", "api_contract", "ui_guidance", "acceptance")

#: task_breakdown 每项的【可选】键 —— ★ 2026-09-19 增 depends_on（M3 并行调度）:
#:   该模块依赖的**模块名**数组（架构阶段还不知道任务树 id, 故用名字; 无依赖 → 空数组）。
#:   消费方: services/work/decomposition.parallel_groups（按名匹配 → 拓扑分层）。
#:   为什么让架构给: 依赖是架构设计的产物 —— 架构 agent 本就按模块划分,
#:   由它给是"源头给"; 靠后从关键词/路径猜都不如源头准。
_TASK_OPTIONAL_KEYS: tuple[str, ...] = ("depends_on", "required_capabilities")

#: product 契约中 Architect 消费的 3 节 (功能/MVP/故事 → 模块划分与任务拆分)
_PRODUCT_ARCH_SECTIONS: tuple[str, ...] = (
    "feature_list",
    "mvp_scope",
    "user_stories",
)

#: ux_ui 契约中 Architect 消费的 4 节 (信息架构/屏幕规格/组件定义/设计规范
#: → 架构分层/API 数据形状/UI 层实现约束 — S8-002 report §S8-003 接入说明)
_UXUI_ARCH_SECTIONS: tuple[str, ...] = (
    "information_architecture",
    "screen_specifications",
    "component_definition",
    "design_tokens",
)

#: prompt 内单输入摘要上限 (字符; 防超长 product/ux_ui 撑爆上下文, 同 uxui
#: 截断思路; 双输入各自截断)
_INPUT_SUMMARY_LIMIT = 8000


class ArchitectError(Exception):
    """Architect Agent 业务错误 (缺双输入 / provider 缺失 / 输出不可解析 /
    缺字段 / 独立生成拒绝)。"""

    __test__ = False  # pytest 收集豁免 (Test* 前缀类名误匹配)


# ------------------------------------------------------------------ 模型


@dataclass(frozen=True)
class DesignArtifact:
    """结构化 Design Artifact (design 契约载荷; 字段 = DESIGN_FIELDS)。

    system_architecture: 系统架构 str (分层/模块边界/数据流);
    technical_stack: 技术选型 dict (语言/框架/存储等);
    database_design: 数据库设计 dict (模型/表结构);
    api_design: API 设计 dict, 必含 endpoints list — 每项 endpoint =
      {method, path, contract} (API 约定, Developer 消费);
    frontend_architecture: 前端架构 str (目录/组件边界, UI 实现指导依据);
    backend_architecture: 后端架构 str (服务/模块);
    task_breakdown: 任务拆分 list — 每项 task = {module, task,
      api_contract, ui_guidance} (Developer 消费: 模块/API 约定/UI 指导)。
    """

    system_architecture: str = ""
    technical_stack: dict[str, Any] = dc_field(default_factory=dict)
    database_design: dict[str, Any] = dc_field(default_factory=dict)
    api_design: dict[str, Any] = dc_field(default_factory=dict)
    frontend_architecture: str = ""
    backend_architecture: str = ""
    task_breakdown: list[Any] = dc_field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """契约载荷 (7 节全字段)。"""
        return {f: getattr(self, f) for f in DESIGN_FIELDS}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "DesignArtifact":
        """宽容解析 (LLM 输出): 缺核心字段/空节 → ArchitectError 响亮
        (不伪造技术设计); 未知字段忽略; 结构经本地校验 (同 CONTRACTS 规则)。"""
        if not isinstance(raw, dict):
            raise ArchitectError(
                f"design artifact must be a dict, got {type(raw).__name__}"
            )
        missing = [f for f in DESIGN_FIELDS if f not in raw]
        if missing:
            raise ArchitectError(
                f"design artifact missing required fields: {', '.join(missing)}"
            )
        errors = _local_validate(raw)
        if errors:
            raise ArchitectError(
                f"design artifact invalid: {'; '.join(errors)}"
            )
        return cls(
            system_architecture=str(raw["system_architecture"]).strip(),
            technical_stack=dict(raw["technical_stack"]),
            database_design=dict(raw["database_design"]),
            api_design=dict(raw["api_design"]),
            frontend_architecture=str(raw["frontend_architecture"]).strip(),
            backend_architecture=str(raw["backend_architecture"]).strip(),
            task_breakdown=list(raw["task_breakdown"]),
        )


def _local_validate(payload: dict[str, Any]) -> list[str]:
    """design 契约本地校验 (exec 侧; 规则与 org CONTRACTS design 同源)。

    返回失败信息列表 (空 = 通过); 缺失字段由调用方 (from_dict) 先查,
    本函数只校验已存在字段的规则 (str 非空 / dict 非空 / api_design 必含
    endpoints / task_breakdown 非空 list)。api_design.endpoints 深度结构
    (非空 list, 每项 endpoint = {method/path/contract}) 与 task_breakdown
    深度结构 (每项含 module/task/api_contract/ui_guidance — Developer 消费
    准备) 为 exec 侧增强校验 — org 侧契约只保证 dict 含 endpoints 键 /
    list 非空 (双体系一致, 同 ux_ui wireframe Screen 策略)。
    """
    errors: list[str] = []
    for f in ("system_architecture", "frontend_architecture", "backend_architecture"):
        v = payload.get(f)
        if not isinstance(v, str) or not v.strip():
            errors.append(f"{f}: expected non-empty str")
    for f in ("technical_stack", "database_design"):
        v = payload.get(f)
        if not isinstance(v, dict) or not v:
            errors.append(f"{f}: expected non-empty dict")
    api = payload.get("api_design")
    if not isinstance(api, dict) or not api:
        errors.append("api_design: expected non-empty dict")
    elif not all(k in api for k in _API_DESIGN_KEYS):
        errors.append("api_design: missing required keys 'endpoints'")
    else:
        errors.extend(_validate_endpoints(api["endpoints"]))
    tb = payload.get("task_breakdown")
    if not isinstance(tb, list) or not tb:
        errors.append("task_breakdown: expected non-empty list")
    else:
        errors.extend(_validate_tasks(tb))
    return errors


def _validate_endpoints(endpoints: Any) -> list[str]:
    """api_design.endpoints 深度结构: 非空 list, 每项 dict 含 method/path/
    contract (method/path 非空 str — API 约定, Developer 消费)。"""
    if not isinstance(endpoints, list) or not endpoints:
        return ["api_design.endpoints: expected non-empty list"]
    errors: list[str] = []
    for i, ep in enumerate(endpoints):
        if not isinstance(ep, dict):
            errors.append(f"api_design.endpoints[{i}]: expected dict")
            continue
        missing = [k for k in _ENDPOINT_KEYS if k not in ep]
        if missing:
            errors.append(
                f"api_design.endpoints[{i}]: missing required keys "
                f"{', '.join(missing)}"
            )
            continue
        for key in ("method", "path"):
            val = ep.get(key)
            if not isinstance(val, str) or not val.strip():
                errors.append(
                    f"api_design.endpoints[{i}].{key}: expected non-empty str"
                )
    return errors


def _validate_tasks(tasks: Any) -> list[str]:
    """task_breakdown 深度结构: 非空 list, 每项 dict 含 module/task/
    api_contract/ui_guidance (全非空 str — Developer 消费: 模块/技术任务/
    API 约定/UI 实现指导)。"""
    if not isinstance(tasks, list) or not tasks:
        return ["task_breakdown: expected non-empty list"]
    errors: list[str] = []
    for i, task in enumerate(tasks):
        if not isinstance(task, dict):
            errors.append(f"task_breakdown[{i}]: expected dict")
            continue
        missing = [k for k in _TASK_KEYS if k not in task]
        if missing:
            errors.append(
                f"task_breakdown[{i}]: missing required keys "
                f"{', '.join(missing)}"
            )
            continue
        for key in _TASK_KEYS:
            val = task.get(key)
            if not isinstance(val, str) or not val.strip():
                errors.append(
                    f"task_breakdown[{i}].{key}: expected non-empty str"
                )
        # 注（2026-09-21 Founder 纠正）: 这里**不拦"粗"** —— 架构给的是**模块级种子**,
        #   把种子拆到"最小实现单位"是【拆解环的递归职责】(expand_to_minimal), 不是架构的。
        #   我第一版在这里加了粒度拦截 ⇒ 架构直接产不出（模块级种子被判"没拆到位"）✗ 已撤。
        # ★ 可选键 depends_on: 给了就必须是 str 列表（模块名; 不给 = 无依赖）
        if "depends_on" in task:
            dep = task.get("depends_on")
            if not isinstance(dep, list) or any(
                not isinstance(x, str) or not x.strip() for x in dep
            ):
                errors.append(
                    f"task_breakdown[{i}].depends_on: expected list[str] (模块名)"
                )
        # ★ 可选键 required_capabilities: 给了就必须是 str 列表（角色名; 不给 = 不声明）
        if "required_capabilities" in task:
            caps = task.get("required_capabilities")
            if not isinstance(caps, list) or any(
                not isinstance(x, str) or not x.strip() for x in caps
            ):
                errors.append(
                    f"task_breakdown[{i}].required_capabilities: expected list[str] (角色名)"
                )
    return errors


# ------------------------------------------------------------------ prompt


#: Architect Agent prompt (Product + UX/UI → 技术设计 7 节; 生产 provider
#: = DeepSeek v4-pro)
#: S8-005 强化: 显式声明每节必须为实质内容, 禁止省略/留空 — 与 PM prompt
#: 同策略, 契约失败由 design 反馈重试闭环兜底 (见 _build_retry_prompt)。
_ARCH_AGENT_PROMPT = (
    "你是一名 Architect (架构师)。基于下面的产品分析产物 (Product Artifact) "
    "与 UX/UI 设计产物 (UX/UI Artifact) 产出结构化技术设计产物 (Design "
    "Artifact), 覆盖 7 节: \n"
    "- system_architecture: 系统架构 (字符串, 分层/模块边界/数据流)\n"
    "- technical_stack: 技术选型 (对象, 语言/框架/存储等)\n"
    "- database_design: 数据库设计 (对象, 模型/表结构)\n"
    "- api_design: API 设计 (对象, 必含 endpoints 数组; 每项 endpoint = "
    "{{method, path, contract}} — API 约定, 供 Developer 实现)\n"
    "- frontend_architecture: 前端架构 (字符串, 目录/组件边界, 依据 UX/UI "
    "产物给出 UI 实现指导)\n"
    "- backend_architecture: 后端架构 (字符串, 服务/模块)\n"
    "- task_breakdown: 任务拆分 (数组, 每项 task = {{module, task, "
    "api_contract, ui_guidance, acceptance, traces_to, depends_on, required_capabilities}} — 模块/技术任务/"
    "API 约定/UI 实现指导/一句话验收/先决模块/必需能力, "
    "供 Developer 直接消费)\n"
    "  ★★ 拆解 = 【递归】（Founder 口径; 老区 ee84bc18 实现过, 绞杀老区时随 10 万行丢失）: "
    "任务**递归嵌套** —— 每项可带 `children`（结构与本项相同, 可再嵌）, "
    "**层数不限, 按需求实际复杂度决定**; **没有 children 的项即叶子任务**。\n"
    "  ★ 拆到【最小单位 / 最小实现】才停: 叶子必须是一个工程师**一次能做完**、"
    "别人能**独立验收**的最小实现单元（能一句话写出验收）。"
    "一个叶里塞 3 件事（顿号枚举, 如\"设计并创建 A、B、C 三张表\"）就是还没拆到位 ⇒ "
    "继续拆成 children, 或拆成并列多项。宁可多几条, 不要一条包多件事。\n"
    "  ★ 每一层（含 children 内的每一项）都必须带全 module/task/api_contract/ui_guidance/acceptance;"
    "不适用写 \"-\", 不能省略。\n"
    "  ★★ traces_to = 该任务的**出处**: 对应需求/PRD 里的**哪一句原话**（照抄那句, 或写用户故事编号）。"
    "**填不出出处的, 不要放进 task_breakdown** —— 那说明它不在需求里, 是架构自己加的;"
    "这类东西不许出现在任务清单里（实测踩过: 需求只写约课/消课/课时/统计, 架构却加了微信登录/"
    "订阅消息/评价 ⇒ 42/199 个任务是没要过的）。\n"
    "  ★ acceptance = 该任务的**一句话验收标准**（怎么算做完, 可被别人独立核对; 必填; "
    "禁止\"等/…/无\"这类兜底写法）\n"
    "  ★ required_capabilities = 该任务**需要什么能力**（角色名数组, 从下面清单里选; "
    "可多选）。★ 标**实际要谁做**: 纯后端接口/数据表/脚本/迁移**不要**标 ui-designer,"
    " 只有页面/界面/组件类才标（真树实测过 52/83 叶误标 ui-designer ⇒ 派活会去找 UI 设计师,"
    " 人找错 = 白等一轮）。清单: {roles}。不确定 → 空数组 []（不猜）。\n"
    "  ★ depends_on = 该模块依赖的**模块名数组**（无依赖 → 空数组 []）。"
    "请按真实先决关系给: 脚手架/初始化/配置类模块→被其它模块依赖; "
    "底层(领域模型/存储)→被上层(命令/接口)依赖; 端到端测试→依赖被测的模块。"
    "**不要**把『列表顺序』当成依赖——顺序不代表先决。\n\n"
    "产品分析产物:\n{product}\n\n"
    "UX/UI 设计产物:\n{ux_ui}\n\n"
    "输出 JSON 对象, 7 节字段必须全部存在且为实质内容: system_architecture / "
    "frontend_architecture / backend_architecture 为非空字符串, technical_stack "
    "/ database_design / api_design 为非空对象 (api_design 必含 endpoints 非空"
    "数组, 每项含 method/path/contract), task_breakdown 为非空数组 (每项含 "
    "module/task/api_contract/ui_guidance)。每一节都必须认真填写, 禁止省略"
    "任何一节, 禁止留空或写占位文字。必须是纯 JSON 对象: 禁止 markdown "
    "代码块围栏 (```), 禁止注释, 禁止任何前后说明文字; 输出必须以 {{ 开始、以 }} 结束。"
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
    raise ArchitectError("Architect output is not valid JSON")


def _gen_task_breakdown_sliced(*, prompt: str, provider: Any, max_tokens: int) -> list[Any] | None:
    """★ task_breakdown 分片生成（2026-09-21: 递归嵌套让它变大 ⇒ 撞单次输出上限）。

    实测: 改成"递归嵌套 + 拆到最小实现"后, 真跑报
      `ProviderError: openai response truncated: finish_reason=length (content 已收到 25085 字符)`
      ⇒ 单次生成装不下（deepseek 单次输出上限 8192 tokens, 提不上去）。
    做法（与 api_design 同一套路, 不另造）:
      ① 先要【模块清单】(name + 一句 scope, 体量小)
      ② **逐模块**要它自己的原子任务（递归嵌套, 每项带 acceptance）—— 每次输出都小
      ③ 程序合并成完整 task_breakdown
    任一环节失败 ⇒ 返回 None（调用方回落"一次生成" —— 增强失败不阻塞主流程, 不静默丢）。
    """
    head = prompt[:2500]
    list_ask = (
        "你在为下面这个项目做架构设计。**只输出【模块清单】**(3-12 个模块; 每个模块给 name 与一句 scope)。\n"
        "★ 只输出 JSON: {\"modules\": [{\"module\": \"名称\", \"scope\": \"一句范围\"}]}\n"
        "不要 markdown, 不要解释。\n\n"
        f"项目背景（节选）:\n{head}\n"
    )
    try:
        r1 = provider.generate(ProviderRequest(task_context=list_ask, max_tokens=2048))
        if not getattr(r1, "ok", False) or not (r1.content or "").strip():
            return None
        d1 = _extract_json(r1.content)
        mods = (d1 or {}).get("modules") if isinstance(d1, dict) else None
        if not isinstance(mods, list) or not mods:
            return None
    except Exception:  # noqa: BLE001 — 分片是"增强", 失败回落
        return None

    out: list[Any] = []
    for m in mods[:12]:
        if isinstance(m, str):
            name, scope = m, ""
        elif isinstance(m, dict):
            name, scope = str(m.get("module") or m.get("name") or ""), str(m.get("scope") or "")
        else:
            continue
        if not name.strip():
            continue
        ask = (
            f"你在为项目做架构设计。**只输出模块「{name}」的任务拆分**（范围: {scope}）。\n"
            "★★ 递归拆到【最小单位 / 最小实现】: 叶子必须是一个工程师一次能做完、别人能独立验收的"
            "最小实现单元（能一句话写出验收）。可带 `children` 继续嵌套（层数不限）, 也可并列多项。\n"
            "★ 每项字段: {module, task, api_contract, ui_guidance, acceptance, traces_to, required_capabilities?}"
            "（traces_to=该任务对应需求/PRD 里的哪一句原话; 填不出出处就别放进 tasks）"
            " —— **含 children 里的每一项都要带全**（递归的每一层都一样）; 不适用就写 \"-\""
            "（**不能省略字段**, 缺字段会被判无效）。\n"
            "★ 只输出 JSON: {\"tasks\": [ ... ]}（module 一律填 \"" + name + "\"）\n"
            "不要 markdown, 不要解释。\n\n"
            f"项目背景（节选）:\n{head}\n"
        )
        try:
            r2 = provider.generate(ProviderRequest(task_context=ask, max_tokens=max_tokens))
            if not getattr(r2, "ok", False) or not (r2.content or "").strip():
                return None
            d2 = _extract_json(r2.content)
            tasks = (d2 or {}).get("tasks") if isinstance(d2, dict) else None
            if not isinstance(tasks, list) or not tasks:
                return None
            for tk in tasks:
                if isinstance(tk, dict):
                    tk.setdefault("module", name)
                    out.append(tk)
        except Exception:  # noqa: BLE001 — 单模块失败 ⇒ 回落（不产半成品）
            return None
    return out or None


def _gen_api_design_sliced(*, prompt: str, provider: Any, max_tokens: int) -> dict[str, Any] | None:
    """★ 分片生成 api_design（先清单 → 分批详情 → 合并）。

    为什么（Founder: "22886 字符 不能分批么？"）:
      api_design 是 7 节里最大的一节 —— 它 90% 的体积是 `endpoints` 数组。
      "把 7 节切成几组"不够（单这一组就 22886 字符 ≈ 7302 tokens, 快撞 8192 上限）;
      ⇒ 必须切到**节内部**: 先只要端点清单（几十个 METHOD/path, 很小）,
        再每批 ≤8 个端点要详情, 最后程序合并。
      ⇒ 每次调用的输出都远小于上限；且**不损质量**（每个端点仍写得细, 只是分多轮）。

    ★ 失败一律返回 None ⇒ 调用方**回落到"一次生成"**（不阻塞主流程, 不静默丢）。
    """

    base = (
        "你在为下面这个项目做架构设计。现在只处理【API 设计】这一节。\n"
        "输出必须是纯 JSON, 不要 markdown, 不要解释。\n"
    )
    # ① 端点清单（很小）
    list_prompt = (
        base
        + "第一步: 只列出【端点清单】—— 每个端点给 method / path / 一句话用途。\n"
        "不要写详细契约（下一步再写）。最多 40 个。格式:\n"
        '{"endpoints":[{"method":"POST","path":"/auth/login","purpose":"登录"}]}\n\n'
        + prompt[:4000]
    )
    try:
        r1 = provider.generate(ProviderRequest(task_context=list_prompt, max_tokens=2048))
        if not getattr(r1, "ok", False) or not (r1.content or "").strip():
            return None
        data = _extract_json(r1.content)
        eps = list((data or {}).get("endpoints") or [])
        if not eps:
            return None
    except Exception:  # noqa: BLE001 — 分片是"增强", 失败就回落
        return None

    # ② 分批详情（每批 ≤8 个）
    detailed: list[dict[str, Any]] = []
    batch = 8
    for i in range(0, len(eps), batch):
        chunk = eps[i:i + batch]
        lines = "\n".join(
            f"{j+1}. {e.get('method')} {e.get('path')} — {e.get('purpose') or ''}"
            for j, e in enumerate(chunk)
        )
        d_prompt = (
            base
            + f"第二步: 为下面这 {len(chunk)} 个端点写【contract】—— 一句话说清这个接口\n"
            "的输入与输出约定（含关键请求/响应字段与错误码）, 供 Developer 照着实现。\n"
            f"★ 只输出这 {len(chunk)} 个, 不要多写, **必须带 contract 且非空**。格式:\n"
            '{"endpoints":[{"method":"POST","path":"/x","contract":"入参 a,b; 出参 c; 401 未登录"}]}\n\n'
            f"端点:\n{lines}\n"
        )
        try:
            r2 = provider.generate(ProviderRequest(task_context=d_prompt, max_tokens=max_tokens))
            if not getattr(r2, "ok", False) or not (r2.content or "").strip():
                return None
            d2 = _extract_json(r2.content)
            got = list((d2 or {}).get("endpoints") or [])
            if not got:
                return None
            detailed.extend(got)
        except Exception:  # noqa: BLE001
            return None

    if not detailed:
        return None
    # ③ 合并（程序做, 不经 LLM）
    return {"endpoints": detailed, "generated_by": "sliced",
            "batches": (len(eps) + batch - 1) // batch}


#: 设计产物的 7 节（顺序即生成顺序; 靠后的节依赖前面的结论）
SECTION_KEYS: tuple[str, ...] = (
    "system_architecture", "technical_stack", "database_design", "api_design",
    "frontend_architecture", "backend_architecture", "task_breakdown",
)

#: 每节的简短说明（写进 prompt, 让模型知道这一节该产出什么）
_SECTION_DESC: dict[str, str] = {
    "system_architecture": "系统架构: 分层/组件/部署形态/关键取舍",
    "technical_stack": "技术栈选型: 语言/框架/中间件/版本, 各带一句理由",
    "database_design": "数据库设计: 表/字段/索引/关系（可分批, 表多时按表分批）",
    "api_design": "API 设计: 端点清单与契约（★ 本节最大, 走分片生成）",
    "frontend_architecture": "前端架构: 页面/组件/状态管理/路由",
    "backend_architecture": "后端架构: 模块划分/服务边界/事务与并发要点",
    # ★ 2026-09-21（Founder: 缺的是任务出处这一栏）: 每条任务必须能指回需求/PRD 的原句
    "traces_to 规则": "★ task_breakdown 每项**必须**带 traces_to = 需求/PRD 里的**原句**（或用户故事编号）;"
                      "**填不出出处的, 不要放进 task_breakdown** —— 那说明是架构自己加的（应另列, 不进任务清单）",
    "task_breakdown": ("任务拆分: 模块 → 任务。★ 每项**必须**含 4 个非空键: "
                       "module（模块名）/ task（技术任务）/ api_contract（该任务涉及的 API 约定）/ "
                       "ui_guidance（UI 实现指导）"),
}


def _gen_sections_individually(*, prompt: str, provider: Any, max_tokens: int) -> dict[str, Any] | None:
    """★ 逐节生成（**每节一次调用**）—— 避免 7 节合并输出超限被截断。

    Founder: "组[数据与接口] 22886 字符 不能分批么？" ⇒ 能, 而且切法要更细:
      实测某产物 7 节合计 14447 字符（api_design 5457 / task_breakdown 3638 /
      database_design 2603 / 其余 4 节 2749）;
      ⇒ **每节各自一次调用** ⇒ 每次输出都是单节体量, 远小于 8192 tokens 上限 ✓
      ⇒ api_design 在大项目能到 22886 字符 ⇒ 它再走 **分片生成**
        （先端点清单 → 每批 ≤8 个写详情 → 程序合并）。
    ★ 之前"分节 4 组"失败的根因: 把 database + api **合并在同一组** ——
      api 的 22886 把那组拖爆 ⇒ 必须**每节单独**, 不合并。
    ★ 任一节失败 ⇒ 返回 None ⇒ 调用方回落到"一次生成"（不阻塞主流程, 不静默丢）。
    """
    merged: dict[str, Any] = {}
    head = prompt[:3000]          # 节取输入摘要（不要整段 prompt, 否则输入本身很占位）
    for key in SECTION_KEYS:
        if key == "api_design":
            sec = _gen_api_design_sliced(prompt=prompt, provider=provider, max_tokens=max_tokens)
        elif key == "task_breakdown":
            # ★ 递归嵌套让它变大 ⇒ 单次装不下（实测 25085 字符被截断）⇒ 分片（先模块清单→逐模块）
            sec = _gen_task_breakdown_sliced(prompt=prompt, provider=provider, max_tokens=max_tokens)
        else:
            ask = (
                f"你在为下面这个项目做架构设计。**只输出 `{key}` 这一节**的 JSON。\n"
                f"这一节的内容与**硬性字段要求**: {_SECTION_DESC.get(key, '')}\n"
                "★ 只输出这一节, 不要输出其它节; 不要 markdown, 不要解释。\n"
                f'输出格式: {{"{key}": <这一节的内容>}}\n\n'
                f"项目背景（节选）:\n{head}\n"
            )
            # ★ 2026-09-21: 单节失败**先重试一轮**再决定; 且失败要**说清是哪一节、为什么**
            #   （实测: 分节中途静默返回 None ⇒ 回落到"一次生成"那条必爆的路 ⇒ 报截断,
            #    但真因在别处 —— 静默降级把人引向了错误的方向 ✗）
            sec = None
            for _try in range(2):
                try:
                    _ask = ask if _try == 0 else (
                        f"{ask}\n★ 上一次输出不是合法 JSON。请**只输出** {{\"{key}\": ...}} 这一节的 JSON,"
                        f" 不要任何解释、不要 markdown 围栏。\n")
                    resp = provider.generate(ProviderRequest(task_context=_ask, max_tokens=max_tokens))
                    if not getattr(resp, "ok", False) or not (resp.content or "").strip():
                        _why = str(getattr(resp, "error", "") or "空响应")[:80]
                        print(f"⚠ 架构分节 {key}: 第 {_try + 1} 次调用失败 —— {_why}", file=sys.stderr)
                        continue
                    data = _extract_json(resp.content)
                    if not isinstance(data, dict) or key not in data:
                        print(f"⚠ 架构分节 {key}: 第 {_try + 1} 次输出不是含 {key} 的 JSON"
                              f"（前 80 字: {(resp.content or '')[:80]!r}）", file=sys.stderr)
                        continue
                    sec = data[key]
                    break
                except Exception as exc:  # noqa: BLE001 — 单节失败: 说清 + 重试
                    print(f"⚠ 架构分节 {key}: 第 {_try + 1} 次异常 {type(exc).__name__}: {str(exc)[:70]}",
                          file=sys.stderr)
            if sec is None:
                print(f"⚠ 架构分节 {key}: 两轮均失败 ⇒ 放弃分节（将回落到一次生成）", file=sys.stderr)
                return None
        if sec in (None, "", [], {}):
            return None
        merged[key] = sec
    return merged or None


def _parse_design(content: str) -> DesignArtifact:
    """LLM 输出 → DesignArtifact (宽容解析; 空/垃圾 → ArchitectError)。"""
    data = _extract_json(content)
    if not isinstance(data, dict):
        raise ArchitectError(
            "Architect output must be a JSON object (design artifact 7 节)"
        )
    return DesignArtifact.from_dict(data)


def _build_retry_prompt(original_prompt: str, error: ArchitectError) -> str:
    """契约失败反馈 (生产自愈闭环, S8-005 PM 同模式): 原始 prompt + 校验
    错误明细 + 修正要求 → 重试轮输入。"""
    return (
        original_prompt
        + "\n\n你的上一次输出未通过设计契约校验, 错误如下:\n"
        + str(error)
        + "\n请修正后重新输出完整 JSON: 7 节字段必须全部存在且为实质内容"
        " (str 节非空字符串、dict 节非空对象、task_breakdown 非空数组且每项"
        "含 module/task/api_contract/ui_guidance, api_design 必含 endpoints "
        "非空数组且每项含 method/path/contract), 特别注意补齐所有缺失或为空的"
        "节。禁止省略任何一节。必须输出修正后的完整 JSON (纯 JSON 对象, "
        "以 { 开始、以 } 结束), 禁止 markdown 代码块围栏 (```)、禁止注释、"
        "禁止任何说明文字。"
    )


# ------------------------------------------------------------------ Architect Agent


class ArchitectAgent:
    """Architect Agent: Product + UX/UI Artifact → 结构化 Design Artifact (7 节)。

    构造 (双输入强校验):
    - provider: ProviderInterface (技术设计 LLM; 生产 DeepSeek v4-pro, 测试
      注入 mock; None → design 时 ArchitectError 响亮)。
    - product: Product Artifact dict (必填 — 构造时缺失 → ArchitectError,
      禁止脱离输入独立生成)。
    - ux_ui: UX/UI Artifact dict (必填 — 构造时缺失 → ArchitectError)。

    方法:
    - design(product=None, ux_ui=None) → DesignArtifact: LLM 生成 + 本地校验
      (双输入解析链: 方法参数 > 构造绑定; 任一为空 → ArchitectError — 强
      校验全入口生效, 不变量永不被打破)。
    - set_product / set_ux_ui: 绑定/替换 (空输入拒绝, 不变量保持)。
    """

    __test__ = False  # pytest 收集豁免 (Test* 前缀类名误匹配)

    def __init__(
        self,
        provider: Any = None,
        *,
        product: dict[str, Any] | None = None,
        ux_ui: dict[str, Any] | None = None,
        max_tokens: int = 8192,
        max_retries: int = 1,
    ) -> None:
        self._provider = provider
        self._product = _require_input("product", product)
        self._ux_ui = _require_input("ux_ui", ux_ui)
        # S8-005: v4-pro reasoning 消耗大, 4096 曾截断致输出缺节 → 8192
        self._max_tokens = int(max_tokens)
        # S8-005: 契约失败 → 带错误反馈重试 ≤max_retries 次 (生产自愈)
        self._max_retries = int(max_retries)

    @property
    def provider(self) -> Any:
        return self._provider

    @property
    def product(self) -> dict[str, Any]:
        return self._product

    @property
    def ux_ui(self) -> dict[str, Any]:
        return self._ux_ui

    def set_product(self, product: dict[str, Any]) -> "ArchitectAgent":
        """绑定/替换 Product Artifact (空输入 → ArchitectError — 强校验)。"""
        self._product = _require_input("product", product)
        return self

    def set_ux_ui(self, ux_ui: dict[str, Any]) -> "ArchitectAgent":
        """绑定/替换 UX/UI Artifact (空输入 → ArchitectError — 强校验)。"""
        self._ux_ui = _require_input("ux_ui", ux_ui)
        return self

    def design(
        self,
        product: dict[str, Any] | None = None,
        ux_ui: dict[str, Any] | None = None,
    ) -> DesignArtifact:
        """Product + UX/UI → Design Artifact (LLM 结构化输出 + 本地契约校验)。

        双输入解析链: 方法参数 > 构造绑定; 任一缺失 → ArchitectError 响亮
        (禁止脱离输入独立生成); provider 缺失 / 调用失败 / 输出不可解析 /
        缺字段 → ArchitectError 响亮 (不假装生成成功); 输出再经 Workflow
        Runner CONTRACTS design 校验 (org 侧), 失败 → INVALID → stage FAILED。

        S8-005 生产自愈 (与 PM develop 同模式): 契约校验失败 → 错误明细
        反馈重试 ≤max_retries 次; 耗尽仍失败 → 响亮 (错误含最后失败明细)。
        """
        # 双输入解析链: 方法显式参数 > 构造绑定 (先解析再校验 — 参数缺省
        # 时回退绑定值, 而非对 None 直接报错; 空 dict/非 dict 仍响亮拒绝)
        product_payload = _require_input(
            "product", product if product is not None else self._product
        )
        ux_ui_payload = _require_input(
            "ux_ui", ux_ui if ux_ui is not None else self._ux_ui
        )
        if self._provider is None:
            raise ArchitectError(
                "design generation requires a provider (仅 DeepSeek v4-pro; "
                "测试注入 mock)"
            )
        # ★ roles 传真实角色清单（单一事实源: plugins/agents/roles.py 的 ROLE_IDS）
        from ai_factory_os.plugins.agents.roles import ROLE_IDS as _ROLE_IDS
        from ai_factory_os.plugins.agents.roles import discipline_block as _disc

        prompt = _ARCH_AGENT_PROMPT.format(
            product=_input_summary("product", product_payload),
            ux_ui=_input_summary("ux_ui", ux_ui_payload),
            roles=", ".join(_ROLE_IDS),
        )
        # ★ 注入工作纪律（吸收自 Codex 的 agent 定义写法）—— 让模型自己看见硬边界,
        #   而不是靠事后拦截（LLM 天然"越查越多" ⇒ 成本失控 + 上下文被挤出）。
        _disc_block = _disc("architect")
        if _disc_block:
            prompt = f"{prompt}\n\n{_disc_block}"
        last_error: ArchitectError | None = None

        # ★ 2026-09-19（Founder: "组[数据与接口] 22886 字符 不能分批么？"）:
        #   **逐节生成** —— 实测: 一次把 7 节全吐出来必超 deepseek 单次输出上限
        #   （8192 tokens; 实测 23550 字符 ⇒ finish_reason=length 被硬截断）。
        #   关键数据（真产物）: 7 节合计 14447 字符, 其中
        #     api_design 5457（38%）· task_breakdown 3638 · database_design 2603 · 其余 4 节 2749
        #   ⇒ **每节各自一次调用** ⇒ 每次输出都是单节体量, 远小于上限 ✓
        #   ⇒ 而 api_design 在大项目里能到 22886 字符（endpoints 很多）
        #     ⇒ 它**额外再分片**（先清单 → 分批详情 → 合并, 见 _gen_api_design_sliced）
        #   ★ 为什么之前"分节 4 组"失败: 把 database + api **合并在同一组**,
        #     api 的 22886 拖爆了那组 ⇒ 必须**每节单独**, 不合并。
        sectioned = _gen_sections_individually(
            prompt=prompt, provider=self._provider, max_tokens=self._max_tokens,
        )
        if sectioned is not None:
            return _parse_design(json.dumps(sectioned, ensure_ascii=False))

        for attempt in range(self._max_retries + 1):
            response = self._provider.generate(
                ProviderRequest(task_context=prompt, max_tokens=self._max_tokens)
            )
            if not response.ok or not (response.content or "").strip():
                raise ArchitectError(
                    f"design generation failed: {response.error or 'empty provider response'}"
                )
            try:
                return _parse_design(response.content)
            except ArchitectError as exc:
                last_error = exc
                if attempt < self._max_retries:
                    prompt = _build_retry_prompt(prompt, exc)
        raise ArchitectError(
            f"design generation failed after {self._max_retries + 1} attempts: "
            f"{last_error}"
        )


def _require_input(name: str, payload: Any) -> dict[str, Any]:
    """双输入强校验: 非 dict / 空 dict → ArchitectError 响亮 (禁止脱离
    输入独立生成 — 架构师不能凭空设计)。"""
    if payload is None:
        raise ArchitectError(
            f"{name} artifact required (ArchitectAgent 构造双输入强校验 — "
            f"禁止脱离 product + ux_ui 独立生成)"
        )
    if not isinstance(payload, dict):
        raise ArchitectError(
            f"{name} artifact must be a dict, got {type(payload).__name__}"
        )
    if not payload:
        raise ArchitectError(
            f"{name} artifact must not be empty (双输入强校验 — 禁止脱离 "
            f"输入独立生成)"
        )
    return payload


def _input_summary(name: str, payload: dict[str, Any]) -> str:
    """Product/UX-UI Artifact → prompt 摘要 (Architect 消费节前置, 其余节
    保留; 各自截断防上下文撑爆)。"""
    sections = (
        _PRODUCT_ARCH_SECTIONS if name == "product" else _UXUI_ARCH_SECTIONS
    )
    ordered = [k for k in sections if k in payload]
    ordered += [k for k in payload if k not in ordered]
    lines = "\n".join(
        f"{k}: {json.dumps(payload[k], ensure_ascii=False)}" for k in ordered
    )
    return lines[: _INPUT_SUMMARY_LIMIT]


# ------------------------------------------------------------------ Workflow 接入


def build_arch_executor(
    agent: ArchitectAgent,
) -> Callable[[Any, dict[str, Any]], dict[str, Any]]:
    """ArchitectAgent → Workflow executor 适配器 (architecture stage,
    role_ref=architect)。

    返回 dict 契约 (S7-003 _register_outputs 消费):
    - artifact_type: "design" (显式声明; ROLE_OUTPUT_TYPES 默认
      architect→design 保持向后兼容, 不覆盖)
    - ref: 产物引用 (file:///docs/design.json)
    - metadata: Design Artifact 契约载荷 (7 节 + artifact_refs 强引用;
      Runner 自动注册 → CONTRACTS design 校验 → VALIDATED / INVALID →
      stage FAILED)

    双输入解析链 (架构 §3 + S8-003 强引用):
    - context inputs 中 product + ux_ui 产物 (type 匹配, metadata = 契约
      载荷) 必须同时存在 — 任一缺失 → ArchitectError (stage FAILED —
      诚实, 禁止脱离输入独立生成; agent 构造虽已绑定 payload, executor
      仍要求 context 输入, 因为 artifact_refs 强引用需要输入产物 id)。
    - artifact_refs: [product_id, ux_ui_id] 写入 metadata — 设计产物显式
      引用输入产物 id (审计/溯源, 任务清单硬性要求)。
    """

    def executor(stage: Any, context: dict[str, Any]) -> dict[str, Any]:
        product = _artifact_from_context(context, "product")
        ux_ui = _artifact_from_context(context, "ux_ui")
        if product is None or ux_ui is None:
            raise ArchitectError(
                "architect executor needs BOTH product and ux_ui artifacts "
                "(context inputs, 带 id 强引用) — 禁止脱离输入独立生成"
            )
        artifact = agent.design(product["metadata"], ux_ui["metadata"])
        metadata = artifact.to_dict()
        metadata["artifact_refs"] = [product["id"], ux_ui["id"]]
        return {
            "artifact_type": "design",
            "ref": "file:///docs/design.json",
            "metadata": metadata,
        }

    return executor


def _artifact_from_context(
    context: dict[str, Any], type_name: str
) -> dict[str, Any] | None:
    """从 executor context inputs 解析指定类型产物 (契约: type + id +
    metadata = 契约载荷; 返回 {id, metadata}, 供 artifact_refs 强引用)。"""
    for inp in context.get("inputs", []):
        if not isinstance(inp, dict):
            continue
        if inp.get("type") == type_name:
            meta = inp.get("metadata")
            if isinstance(meta, dict) and meta:
                return {"id": inp.get("id", ""), "metadata": meta}
    return None
