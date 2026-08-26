"""factory-console/external_executor/schema.py — 外部执行器适配器 Schema (M1)。

设计依据: docs/sprint10/外部执行器通用适配层-设计.md §4 (适配器 Schema)。
一个外部 AI CLI = 一个声明式适配器 (yaml), 通用引擎只依赖本 Schema, 不依赖产品名。

字段语义见设计文档 §4.1-4.5; 校验失败 → Pydantic ValidationError → 引擎报
「适配器校验失败」, 不猜测不降级。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

PROJECT_DIR_MODES = ("cwd", "none")


class InvocationSpec(BaseModel):
    """调用模板 (§4.2)。占位符 {prompt}/{project_dir}/{agent}/{skills} 渲染时替换。"""

    model_config = ConfigDict(extra="forbid")

    non_interactive: list[str]
    project_dir: str = "cwd"          # cwd | none | flag:<参数名>
    agent_flag: list[str] | None = None   # 借壳: 指定宿主内部 agent
    skills_flag: list[str] | None = None  # 借壳: 指定宿主 skills
    extra: list[str] = []
    timeout: int = 600

    @field_validator("project_dir")
    @classmethod
    def _project_dir_valid(cls, v: str) -> str:
        v = str(v or "cwd").strip()
        if v in PROJECT_DIR_MODES or v.startswith("flag:"):
            return v
        raise ValueError(
            f"project_dir 必须为 cwd|none|flag:<参数名> (got {v!r})"
        )

    @field_validator("non_interactive")
    @classmethod
    def _must_contain_prompt(cls, v: list[str]) -> list[str]:
        if not isinstance(v, list) or not v:
            raise ValueError("non_interactive 不能为空")
        if not any("{prompt}" in str(x) for x in v):
            raise ValueError("non_interactive 必须含 {prompt} 占位符 (无输入调用禁止)")
        return v


class AssetSpec(BaseModel):
    """宿主内部资产发现规则 (§4.3)。"""

    model_config = ConfigDict(extra="forbid")

    dir: str
    glob: str = "*"
    format: str                 # toml | md-frontmatter | yaml | keyvalue | skill-md | dirs
    fields: dict[str, str] = {}  # 原字段名 → 标准字段 (name/description/prompt/...)


class HostAssetsSpec(BaseModel):
    """宿主内部可导入资产 (agents/skills/plugins/persona)。"""

    model_config = ConfigDict(extra="forbid")

    agents: AssetSpec | None = None
    skills: AssetSpec | None = None
    plugins: AssetSpec | None = None
    persona: dict[str, str] | None = None   # {path: "~/.hermes/SOUL.md"}


class CapabilitiesSpec(BaseModel):
    """能力声明 (§4.4) → 路由输入。"""

    model_config = ConfigDict(extra="forbid")

    roles: list[str] = []
    agents: bool = False
    skills: bool = False
    cost_tier: str = "medium"     # low | medium | high


class ExternalExecutorAdapter(BaseModel):
    """一个外部 AI CLI 的完整适配器 (yaml 文件 ↔ 本模型)。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    binary: str
    discovery: list[str] = ["PATH"]
    version_probe: list[str] = ["--version"]
    probe_help: list[str] | None = None
    invocation: InvocationSpec
    host_assets: HostAssetsSpec | None = None
    capabilities: CapabilitiesSpec = CapabilitiesSpec()
    extensions: dict[str, Any] = {}
    allow_dangerous: bool = False

    @field_validator("id")
    @classmethod
    def _id_sane(cls, v: str) -> str:
        v = str(v or "").strip()
        if not v or "/" in v or "\\" in v or " " in v:
            raise ValueError(f"非法适配器 id: {v!r}")
        return v

    @field_validator("binary")
    @classmethod
    def _binary_sane(cls, v: str) -> str:
        v = str(v or "").strip()
        if not v:
            raise ValueError("binary 不能为空")
        return v

    def to_yaml(self) -> str:
        """序列化为 yaml 文本 (写 <data_dir>/external-ais/<id>.yaml)。"""
        import yaml  # type: ignore

        return yaml.safe_dump(self.model_dump(mode="json"), sort_keys=False, allow_unicode=True)


def adapter_from_yaml(text: str) -> ExternalExecutorAdapter:
    """yaml 文本 → 适配器 (校验失败 → ValidationError)。"""
    import yaml  # type: ignore

    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise ValueError("适配器 yaml 必须是 map")
    return ExternalExecutorAdapter(**data)
