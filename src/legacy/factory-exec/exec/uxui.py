"""factory-exec/exec/uxui.py — UX/UI Designer Agent 执行 (Sprint 8 S8-002)。

设计依据 (sprint8-architecture.md §2 ② UX/UI Designer / §3 Artifact 流转 +
S8-001 report §S8-002 接入说明):
```
输入: Product Artifact (7 节; UX 消费重点: user_persona / user_journey /
      feature_list / mvp_scope / user_stories — 画像驱动界面决策、旅程 → 用户
      流程、功能 → 信息架构与线框、MVP → 线框范围、故事 → 屏幕规格验收)
输出: UX/UI Artifact (7 节): information_architecture / user_flow / wireframe
      / screen_specifications / component_definition / design_tokens / prototype
实现: roles.py UX/UI Designer executable + uxui.py (UXUIDesignerAgent)
验证: CONTRACTS ux_ui 类型 (required fields + 规则; 失败 → INVALID 响亮)
接入: Workflow stage "ux_ui" (role_ref=ui-designer) — build_uxui_executor 适配器
```

实现 (KISS, 复用 pm.py 模式):
- 生成: 仅当有 Product Artifact 才调 Provider (生产 DeepSeek v4-pro; 测试
  注入 mock); LLM 输出结构化 JSON → UXUIArtifact (宽容解析: markdown 围栏
  剥离/整体解析/子串回退; 缺核心字段 → 响亮拒绝 — 不伪造设计产物)。
- Product 解析链 (executor): context inputs 中 product artifact (metadata =
  product 契约载荷) > UXUIDesignerAgent 构造绑定 product — 与架构 §3 一致
  (stage input 可无 artifact, 但 UX 设计必须有 product, 无 → 响亮)。
- 本地校验: UXUIDesignerAgent 内做同源字段校验 (7 节非空/结构, 与 org
  CONTRACTS ux_ui 规则一致; exec 零 import factory-org — Removal Isolation,
  同 tester.py/pm.py 约束); wireframe 深度结构: screens 非空 list, 每屏
  Screen = {name/ascii/components/actions} (name/ascii 非空 str)。
- 机器可读: 产物纯 JSON 结构化文本 (ASCII 布局嵌在 wireframe.screens[].ascii),
  不生成任何图片文件, 不引入 Figma 等外部系统。

约束 (S8-002):
- 只扩展, 不重写: 不 import factory-org; 不实现 Architect/Release Agent
  (S8-003/S8-004); 零明文密钥; 不修改 Workflow/Artifact 核心。
- 诚实: 无 provider / 无 product → UXUIDesignerError 响亮; 输出不可解析/
  缺字段 → 响亮拒绝 (不假装生成成功); ROLE_OUTPUT_TYPES 默认
  (ui-designer→design) 保持向后兼容, 本模块显式声明 artifact_type="ux_ui"。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field as dc_field
from typing import Any, Callable

from .provider import ProviderRequest

#: ux_ui 契约字段 (与 org CONTRACTS ux_ui required_fields 同源; 本地
#: 校验 = exec 侧同规则, Removal Isolation 下与 org 侧保持一致)
UXUI_FIELDS: tuple[str, ...] = (
    "information_architecture",
    "user_flow",
    "wireframe",
    "screen_specifications",
    "component_definition",
    "design_tokens",
    "prototype",
)

#: wireframe 必含键 (与 org CONTRACTS ux_ui validation_rules 同源)
_WIREFRAME_KEYS: tuple[str, ...] = ("screens",)

#: 每屏 Screen 必含键 (任务清单: Screen: {name, components[], actions[]};
#: ascii 为 ASCII 布局文本 — 机器可读, 不生成图片)
_SCREEN_KEYS: tuple[str, ...] = ("name", "ascii", "components", "actions")

#: product 契约中 UX 消费的 5 节 (S8-001 report §S8-002 接入说明:
#: 画像/旅程/功能/MVP/故事 — prompt 摘要前置, 设计驱动)
_PRODUCT_UX_SECTIONS: tuple[str, ...] = (
    "user_persona",
    "user_journey",
    "feature_list",
    "mvp_scope",
    "user_stories",
)

#: prompt 内 product 摘要上限 (字符; 防超长 product 撑爆上下文, 同 pm 截断思路)
_PRODUCT_SUMMARY_LIMIT = 8000


class UXUIDesignerError(Exception):
    """UX/UI Designer Agent 业务错误 (缺 product / provider 缺失 / 输出
    不可解析 / 缺字段)。"""

    __test__ = False  # pytest 收集豁免 (Test* 前缀类名误匹配)


# ------------------------------------------------------------------ 模型


@dataclass(frozen=True)
class UXUIArtifact:
    """结构化 UX/UI Artifact (ux_ui 契约载荷; 字段 = UXUI_FIELDS)。

    information_architecture: 信息架构 dict (如 screens 层级 + navigation);
    user_flow: 用户流程 list (每步 dict: step/screen);
    wireframe: 线框 dict, 必含 screens list — 每屏 Screen = {name, ascii
      (ASCII 布局文本), components[], actions[]} (机器可读, 不生成图片);
    screen_specifications: 屏幕规格 list (每屏 dict: screen/elements/
      behaviors/acceptance);
    component_definition: 组件定义 list (每组件 dict: name/description/usage);
    design_tokens: 设计规范 dict (如 colors/typography/spacing);
    prototype: 原型说明 str (交互描述文本, 无外部工具依赖)。
    """

    information_architecture: dict[str, Any] = dc_field(default_factory=dict)
    user_flow: list[Any] = dc_field(default_factory=list)
    wireframe: dict[str, Any] = dc_field(default_factory=dict)
    screen_specifications: list[Any] = dc_field(default_factory=list)
    component_definition: list[Any] = dc_field(default_factory=list)
    design_tokens: dict[str, Any] = dc_field(default_factory=dict)
    prototype: str = ""

    def to_dict(self) -> dict[str, Any]:
        """契约载荷 (7 节全字段)。"""
        return {f: getattr(self, f) for f in UXUI_FIELDS}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "UXUIArtifact":
        """宽容解析 (LLM 输出): 缺核心字段/空节 → UXUIDesignerError 响亮
        (不伪造设计产物); 未知字段忽略; 结构经本地校验 (同 CONTRACTS 规则)。"""
        if not isinstance(raw, dict):
            raise UXUIDesignerError(
                f"ux_ui artifact must be a dict, got {type(raw).__name__}"
            )
        missing = [f for f in UXUI_FIELDS if f not in raw]
        if missing:
            raise UXUIDesignerError(
                f"ux_ui artifact missing required fields: {', '.join(missing)}"
            )
        errors = _local_validate(raw)
        if errors:
            raise UXUIDesignerError(
                f"ux_ui artifact invalid: {'; '.join(errors)}"
            )
        return cls(
            information_architecture=dict(raw["information_architecture"]),
            user_flow=list(raw["user_flow"]),
            wireframe=dict(raw["wireframe"]),
            screen_specifications=list(raw["screen_specifications"]),
            component_definition=list(raw["component_definition"]),
            design_tokens=dict(raw["design_tokens"]),
            prototype=str(raw["prototype"]).strip(),
        )


def _local_validate(payload: dict[str, Any]) -> list[str]:
    """ux_ui 契约本地校验 (exec 侧; 规则与 org CONTRACTS ux_ui 同源)。

    返回失败信息列表 (空 = 通过); 缺失字段由调用方 (from_dict) 先查,
    本函数只校验已存在字段的规则 (str 非空 / list 非空 / dict 非空 +
    wireframe 含 screens)。wireframe.screens 深度结构 (非空 list, 每屏
    Screen 四键) 为 exec 侧增强校验 — org 侧契约只保证 dict 含 screens 键。
    """
    errors: list[str] = []
    ia = payload.get("information_architecture")
    if not isinstance(ia, dict) or not ia:
        errors.append("information_architecture: expected non-empty dict")
    uf = payload.get("user_flow")
    if not isinstance(uf, list) or not uf:
        errors.append("user_flow: expected non-empty list")
    wf = payload.get("wireframe")
    if not isinstance(wf, dict) or not wf:
        errors.append("wireframe: expected non-empty dict")
    elif not all(k in wf for k in _WIREFRAME_KEYS):
        errors.append("wireframe: missing required keys 'screens'")
    else:
        errors.extend(_validate_screens(wf["screens"]))
    ss = payload.get("screen_specifications")
    if not isinstance(ss, list) or not ss:
        errors.append("screen_specifications: expected non-empty list")
    cd = payload.get("component_definition")
    if not isinstance(cd, list) or not cd:
        errors.append("component_definition: expected non-empty list")
    dt = payload.get("design_tokens")
    if not isinstance(dt, dict) or not dt:
        errors.append("design_tokens: expected non-empty dict")
    proto = payload.get("prototype")
    if not isinstance(proto, str) or not proto.strip():
        errors.append("prototype: expected non-empty str")
    return errors


def _validate_screens(screens: Any) -> list[str]:
    """wireframe.screens 深度结构: 非空 list, 每屏 dict 含 name/ascii/
    components/actions (name/ascii 非空 str, components/actions 为 list)。"""
    if not isinstance(screens, list) or not screens:
        return ["wireframe.screens: expected non-empty list"]
    errors: list[str] = []
    for i, screen in enumerate(screens):
        if not isinstance(screen, dict):
            errors.append(f"wireframe.screens[{i}]: expected dict")
            continue
        missing = [k for k in _SCREEN_KEYS if k not in screen]
        if missing:
            errors.append(
                f"wireframe.screens[{i}]: missing required keys "
                f"{', '.join(missing)}"
            )
            continue
        name = screen.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"wireframe.screens[{i}].name: expected non-empty str")
        ascii_text = screen.get("ascii")
        if not isinstance(ascii_text, str) or not ascii_text.strip():
            errors.append(
                f"wireframe.screens[{i}].ascii: expected non-empty str"
            )
        for key in ("components", "actions"):
            if not isinstance(screen.get(key), list):
                errors.append(f"wireframe.screens[{i}].{key}: expected list")
    return errors


# ------------------------------------------------------------------ prompt


#: UX/UI Designer Agent prompt (Product Artifact → 设计 7 节; 生产 provider
#: = DeepSeek v4-pro)
#: S8-005 强化: 显式声明每节必须为实质内容 (str 非空 / list 非空 /
#: wireframe 含 screens), 禁止省略/留空 — 与 PM prompt 同策略, 契约失败由
#: design 反馈重试闭环兜底 (见 _build_retry_prompt)。
_UXUI_AGENT_PROMPT = (
    "你是一名 UX/UI Designer (UX/UI 设计师)。把下面的产品分析产物 (Product "
    "Artifact) 转化为结构化 UX/UI 设计产物 (UX/UI Artifact), 覆盖 7 节: \n"
    "- information_architecture: 信息架构 (对象, 含 screens 层级与 navigation)\n"
    "- user_flow: 用户流程 (数组, 每项含 step/screen)\n"
    "- wireframe: 线框 (对象, 必含 screens 数组; 每屏 Screen = {{name, ascii, "
    "components[], actions[]}}, ascii 为 ASCII 布局文本 — 机器可读, 不生成图片)\n"
    "- screen_specifications: 屏幕规格 (数组, 每项含 screen/elements/"
    "behaviors/acceptance)\n"
    "- component_definition: 组件定义 (数组, 每项含 name/description/usage)\n"
    "- design_tokens: 设计规范 (对象, 含 colors/typography/spacing)\n"
    "- prototype: 原型说明 (字符串, 交互描述文本)\n\n"
    "产品分析产物:\n{product}\n\n"
    "输出 JSON 对象, 7 节字段必须全部存在且为实质内容: information_architecture "
    "/ wireframe / design_tokens 为非空对象 (wireframe 必含 screens 非空数组, "
    "每屏含 name/ascii/components/actions), user_flow / screen_specifications / "
    "component_definition 为非空数组, prototype 为非空字符串。每一节都必须"
    "认真填写, 禁止省略任何一节, 禁止留空或写占位文字。必须是纯 JSON 对象: "
    "禁止 markdown 代码块围栏 (```), 禁止注释, 禁止任何前后说明文字; "
    "输出必须以 {{ 开始、以 }} 结束。"
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
    raise UXUIDesignerError("UX/UI Designer output is not valid JSON")


def _parse_uxui(content: str) -> UXUIArtifact:
    """LLM 输出 → UXUIArtifact (宽容解析; 空/垃圾 → UXUIDesignerError)。"""
    data = _extract_json(content)
    if not isinstance(data, dict):
        raise UXUIDesignerError(
            "UX/UI Designer output must be a JSON object (ux_ui artifact 7 节)"
        )
    return UXUIArtifact.from_dict(data)


def _build_retry_prompt(original_prompt: str, error: UXUIDesignerError) -> str:
    """契约失败反馈 (生产自愈闭环, S8-005 PM 同模式): 原始 prompt + 校验
    错误明细 + 修正要求 → 重试轮输入。"""
    return (
        original_prompt
        + "\n\n你的上一次输出未通过 UX/UI 契约校验, 错误如下:\n"
        + str(error)
        + "\n请修正后重新输出完整 JSON: 7 节字段必须全部存在且为实质内容"
        " (str 节非空字符串、list 节非空数组、dict 节非空对象, wireframe "
        "必含 screens 非空数组且每屏含 name/ascii/components/actions), "
        "特别注意补齐所有缺失或为空的节。禁止省略任何一节。"
        " 必须输出修正后的完整 JSON (纯 JSON 对象, 以 { 开始、以 } 结束), "
        "禁止 markdown 代码块围栏 (```)、禁止注释、禁止任何说明文字。"
    )


# ------------------------------------------------------------------ UX/UI Agent


class UXUIDesignerAgent:
    """UX/UI Designer Agent: Product Artifact → 结构化 UX/UI Artifact (7 节)。

    构造:
    - provider: ProviderInterface (设计 LLM; 生产 DeepSeek v4-pro, 测试注入
      mock; None → design 时 UXUIDesignerError 响亮)。
    - product: 可选默认 Product Artifact dict (Workflow executor 场景 context
      无 product artifact 时的回退输入; 架构 §3: stage input 可无 artifact,
      但 UX 设计必须有 product, 均无 → 响亮)。

    方法:
    - design(product=None) → UXUIArtifact: LLM 生成 + 本地校验 (Product
      解析链: 方法参数 > 构造绑定 > UXUIDesignerError)。
    """

    __test__ = False  # pytest 收集豁免 (Test* 前缀类名误匹配)

    def __init__(
        self,
        provider: Any = None,
        *,
        product: dict[str, Any] | None = None,
        max_tokens: int = 8192,
        max_retries: int = 2,
    ) -> None:
        self._provider = provider
        self._product = _normalize_product(product)
        # S8-005: v4-pro reasoning 消耗大, 4096 曾截断致输出缺节 → 8192
        self._max_tokens = int(max_tokens)
        # S8-005: 契约失败 → 带错误反馈重试 ≤max_retries 次 (生产自愈)
        self._max_retries = int(max_retries)

    @property
    def provider(self) -> Any:
        return self._provider

    @property
    def product(self) -> dict[str, Any] | None:
        return self._product

    def set_product(self, product: dict[str, Any] | None) -> "UXUIDesignerAgent":
        """绑定/替换默认 Product Artifact (executor 复用同一 agent 实例)。"""
        self._product = _normalize_product(product)
        return self

    def design(self, product: dict[str, Any] | None = None) -> UXUIArtifact:
        """Product Artifact → UX/UI Artifact (LLM 结构化输出 + 本地契约校验)。

        provider 缺失 / 调用失败 / 输出不可解析 / 缺字段 → UXUIDesignerError
        响亮 (不假装生成成功); 输出再经 Workflow Runner CONTRACTS ux_ui
        校验 (org 侧), 失败 → INVALID → stage FAILED。

        S8-005 生产自愈 (与 PM develop 同模式): 契约校验失败 → 错误明细
        反馈重试 ≤max_retries 次; 耗尽仍失败 → 响亮 (错误含最后失败明细)。
        """
        payload = _normalize_product(product) or self._product
        if not payload:
            raise UXUIDesignerError(
                "product artifact required (UXUIDesignerAgent 构造绑定 或 "
                "design(product) 显式传入)"
            )
        if self._provider is None:
            raise UXUIDesignerError(
                "ux_ui design requires a provider (仅 DeepSeek v4-pro; 测试注入 mock)"
            )
        prompt = _UXUI_AGENT_PROMPT.format(product=_product_summary(payload))
        last_error: UXUIDesignerError | None = None
        for attempt in range(self._max_retries + 1):
            response = self._provider.generate(
                ProviderRequest(task_context=prompt, max_tokens=self._max_tokens)
            )
            if not response.ok or not (response.content or "").strip():
                raise UXUIDesignerError(
                    f"ux_ui design failed: {response.error or 'empty provider response'}"
                )
            try:
                return _parse_uxui(response.content)
            except UXUIDesignerError as exc:
                last_error = exc
                if attempt < self._max_retries:
                    prompt = _build_retry_prompt(prompt, exc)
        raise UXUIDesignerError(
            f"ux_ui design failed after {self._max_retries + 1} attempts: "
            f"{last_error}"
        )


def _normalize_product(product: Any) -> dict[str, Any] | None:
    """product 输入归一: 非 dict → 响亮配置错误; 空 dict → None (未绑定)。"""
    if product is None:
        return None
    if not isinstance(product, dict):
        raise UXUIDesignerError(
            f"product artifact must be a dict, got {type(product).__name__}"
        )
    return product if product else None


def _product_summary(product: dict[str, Any]) -> str:
    """Product Artifact → prompt 摘要 (UX 设计驱动 5 节前置, 其余节保留;
    截断防上下文撑爆)。"""
    ordered = [k for k in _PRODUCT_UX_SECTIONS if k in product]
    ordered += [k for k in product if k not in ordered]
    lines = "\n".join(
        f"{k}: {json.dumps(product[k], ensure_ascii=False)}" for k in ordered
    )
    return lines[: _PRODUCT_SUMMARY_LIMIT]


# ------------------------------------------------------------------ Workflow 接入


def build_uxui_executor(
    agent: UXUIDesignerAgent,
) -> Callable[[Any, dict[str, Any]], dict[str, Any]]:
    """UXUIDesignerAgent → Workflow executor 适配器 (ux_ui stage, role_ref=ui-designer)。

    返回 dict 契约 (S7-003 _register_outputs 消费):
    - artifact_type: "ux_ui" (显式声明; ROLE_OUTPUT_TYPES 默认
      ui-designer→design 保持向后兼容, 不覆盖)
    - ref: 产物引用 (file:///docs/ux_ui.json)
    - metadata: UX/UI Artifact 契约载荷 (7 节; Runner 自动注册 → CONTRACTS
      ux_ui 校验 → VALIDATED / INVALID → stage FAILED)

    Product 解析链 (架构 §3): context inputs 中 product artifact (metadata =
    product 契约载荷) > UXUIDesignerAgent 构造绑定 product; 均无 →
    UXUIDesignerError (stage FAILED — 诚实, 不臆造输入)。
    """

    def executor(stage: Any, context: dict[str, Any]) -> dict[str, Any]:
        product = _product_from_context(context) or agent.product
        if not product:
            raise UXUIDesignerError(
                "uxui executor needs a product artifact "
                "(context inputs product artifact metadata 或 "
                "UXUIDesignerAgent 绑定 product)"
            )
        artifact = agent.design(product)
        return {
            "artifact_type": "ux_ui",
            "ref": "file:///docs/ux_ui.json",
            "metadata": artifact.to_dict(),
        }

    return executor


def _product_from_context(context: dict[str, Any]) -> dict[str, Any] | None:
    """从 executor context inputs 的 product 产物 metadata 解析 Product
    Artifact (product 产物契约: type == "product", metadata = 契约载荷)。"""
    for inp in context.get("inputs", []):
        if not isinstance(inp, dict):
            continue
        if inp.get("type") == "product":
            meta = inp.get("metadata")
            if isinstance(meta, dict) and meta:
                return meta
    return None
