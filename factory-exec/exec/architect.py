"""factory-exec/exec/architect.py — Architect Agent 执行 (Sprint 8 S8-003)。

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

import json
from dataclasses import dataclass, field as dc_field
from typing import Any, Callable

from .provider import ProviderRequest

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
_TASK_KEYS: tuple[str, ...] = ("module", "task", "api_contract", "ui_guidance")

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
    return errors


# ------------------------------------------------------------------ prompt


#: Architect Agent prompt (Product + UX/UI → 技术设计 7 节; 生产 provider
#: = DeepSeek v4-pro)
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
    "api_contract, ui_guidance}} — 模块/技术任务/API 约定/UI 实现指导, 供 "
    "Developer 直接消费)\n\n"
    "产品分析产物:\n{product}\n\n"
    "UX/UI 设计产物:\n{ux_ui}\n\n"
    "输出 JSON 对象, 7 节字段齐全, 仅输出 JSON, 不要任何多余文字。"
)


# ------------------------------------------------------------------ 解析


def _extract_json(content: str) -> Any:
    """宽容 JSON 提取: 剥 markdown 围栏 → 整体解析 → 子串回退 ({})。"""
    text = content.strip()
    lines = text.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except ValueError:
            pass
    raise ArchitectError("Architect output is not valid JSON")


def _parse_design(content: str) -> DesignArtifact:
    """LLM 输出 → DesignArtifact (宽容解析; 空/垃圾 → ArchitectError)。"""
    data = _extract_json(content)
    if not isinstance(data, dict):
        raise ArchitectError(
            "Architect output must be a JSON object (design artifact 7 节)"
        )
    return DesignArtifact.from_dict(data)


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
        max_tokens: int = 4096,
    ) -> None:
        self._provider = provider
        self._product = _require_input("product", product)
        self._ux_ui = _require_input("ux_ui", ux_ui)
        self._max_tokens = int(max_tokens)

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
        prompt = _ARCH_AGENT_PROMPT.format(
            product=_input_summary("product", product_payload),
            ux_ui=_input_summary("ux_ui", ux_ui_payload),
        )
        response = self._provider.generate(
            ProviderRequest(task_context=prompt, max_tokens=self._max_tokens)
        )
        if not response.ok or not (response.content or "").strip():
            raise ArchitectError(
                f"design generation failed: {response.error or 'empty provider response'}"
            )
        return _parse_design(response.content)


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
