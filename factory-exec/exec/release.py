"""factory-exec/exec/release.py — Release Agent 执行 (Sprint 8 S8-004)。

设计依据 (sprint8-architecture.md §2 ⑥ Release / §3 Artifact 流转 +
S8-003 report §S8-004 接入说明):
```
输入: Code Artifact + Test Artifact — 双输入强校验
      (Test 必须 VALIDATED 强校验: test 契约载荷 — results dict 必含
       passed 键 + bugs list; 未通过测试的产物禁止发布 — 质量门禁)
输出: Release Artifact (5 节): build_result / version / package /
      release_notes / deployment
实现: roles.py DevOps executable + release.py (ReleaseAgent)
验证: CONTRACTS release 类型 (5 节必填 + 规则; 失败 → INVALID 响亮)
接入: Workflow stage "release" (role_ref=devops) —
      build_release_executor 适配器
```

实现 (KISS, 复用 pm.py/uxui.py/architect.py 模式):
- 双输入强校验: ReleaseAgent 构造时 code + test 必须同时存在 (任一缺失 →
  ReleaseError 响亮) — 禁止脱离输入独立生成 (发布不能凭空捏造)。
- Test VALIDATED 强校验 (本任务硬性要求): test 输入必须满足 test 契约
  (results dict 必含 passed + bugs list — 与 org CONTRACTS test 同源),
  缺 results/bugs/passed → ReleaseError 响亮 ("未通过测试的产物禁止发布")。
  set_code/set_test 同样拒绝空输入 (不变量全入口生效)。
- 生成: 仅当双输入齐备才调 Provider (生产 DeepSeek v4-pro; 测试注入 mock);
  LLM 输出结构化 JSON → ReleaseArtifact (宽容解析: markdown 围栏剥离/整体
  解析/子串回退; 缺核心字段/空节 → 响亮拒绝 — 不伪造发布产物)。
- 本地校验: ReleaseAgent 内做同源字段校验 (5 节非空/结构 + build_result
  必含 status/command + package 必含 name/type/files + files 非空 list —
  与 org CONTRACTS release 规则一致; exec 零 import factory-org —
  Removal Isolation, 同 pm/uxui/architect 约束)。
- artifact_refs (强引用): build_release_executor 从 executor context inputs
  解析 code/test 产物 id, 输出 metadata 带 "artifact_refs":
  [code_id, test_id] — 发布产物显式引用输入产物 (审计/溯源); context
  缺任一输入产物 → ReleaseError (stage FAILED — 诚实, 不脱离输入独立
  生成, 即使 agent 构造已绑定 payload)。

约束 (S8-004):
- 只扩展, 不重写: 不 import factory-org; 不实现 S8-005 Demo 编排;
  零明文密钥; 不修改 Workflow/Artifact 核心。
- 诚实: 无 provider / 缺双输入 → ReleaseError 响亮; 输出不可解析/缺字段
  → 响亮拒绝 (不假装生成成功); ROLE_OUTPUT_TYPES 默认 (devops→release)
  保持向后兼容, 本模块显式声明 artifact_type="release"。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field as dc_field
from typing import Any, Callable

from .provider import ProviderRequest

#: release 契约字段 (与 org CONTRACTS release required_fields 同源; 本地
#: 校验 = exec 侧同规则, Removal Isolation 下与 org 侧保持一致)
RELEASE_FIELDS: tuple[str, ...] = (
    "build_result",
    "version",
    "package",
    "release_notes",
    "deployment",
)

#: build_result 必含键 (与 org CONTRACTS release validation_rules 同源;
#: status = 构建成败, command = 构建命令)
_BUILD_RESULT_KEYS: tuple[str, ...] = ("status", "command")

#: package 必含键 (发布包清单: 名称/类型/文件清单)
_PACKAGE_KEYS: tuple[str, ...] = ("name", "type", "files")

#: code 契约中 Release 消费的 2 节 (文件清单/变更说明 → 打包范围与发布说明)
_CODE_RELEASE_SECTIONS: tuple[str, ...] = ("files", "changes")

#: test 契约中 Release 消费的 2 节 (结果/缺陷 → 质量门禁: 未通过禁止发布)
_TEST_RELEASE_SECTIONS: tuple[str, ...] = ("results", "bugs")

#: prompt 内单输入摘要上限 (字符; 防超长 code/test 撑爆上下文, 同 architect
#: 截断思路; 双输入各自截断)
_INPUT_SUMMARY_LIMIT = 8000


class ReleaseError(Exception):
    """Release Agent 业务错误 (缺双输入 / Test 未 VALIDATED / provider 缺失 /
    输出不可解析 / 缺字段 / 独立生成拒绝)。"""

    __test__ = False  # pytest 收集豁免 (Test* 前缀类名误匹配)


# ------------------------------------------------------------------ 模型


@dataclass(frozen=True)
class ReleaseArtifact:
    """结构化 Release Artifact (release 契约载荷; 字段 = RELEASE_FIELDS)。

    build_result: 构建结果 dict, 必含 {status, command} (构建成败/命令);
    version: 版本号 str (非空);
    package: 发布包 dict, 必含 {name, type, files} (名称/类型/文件清单);
    release_notes: 发布说明 str (非空);
    deployment: 部署方案 str (非空, 含部署步骤)。
    """

    build_result: dict[str, Any] = dc_field(default_factory=dict)
    version: str = ""
    package: dict[str, Any] = dc_field(default_factory=dict)
    release_notes: str = ""
    deployment: str = ""

    def to_dict(self) -> dict[str, Any]:
        """契约载荷 (5 节全字段)。"""
        return {f: getattr(self, f) for f in RELEASE_FIELDS}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ReleaseArtifact":
        """宽容解析 (LLM 输出): 缺核心字段/空节 → ReleaseError 响亮
        (不伪造发布产物); 未知字段忽略; 结构经本地校验 (同 CONTRACTS 规则)。"""
        if not isinstance(raw, dict):
            raise ReleaseError(
                f"release artifact must be a dict, got {type(raw).__name__}"
            )
        missing = [f for f in RELEASE_FIELDS if f not in raw]
        if missing:
            raise ReleaseError(
                f"release artifact missing required fields: {', '.join(missing)}"
            )
        errors = _local_validate(raw)
        if errors:
            raise ReleaseError(
                f"release artifact invalid: {'; '.join(errors)}"
            )
        return cls(
            build_result=dict(raw["build_result"]),
            version=str(raw["version"]).strip(),
            package=dict(raw["package"]),
            release_notes=str(raw["release_notes"]).strip(),
            deployment=str(raw["deployment"]).strip(),
        )


def _local_validate(payload: dict[str, Any]) -> list[str]:
    """release 契约本地校验 (exec 侧; 规则与 org CONTRACTS release 同源)。

    返回失败信息列表 (空 = 通过); 缺失字段由调用方 (from_dict) 先查,
    本函数只校验已存在字段的规则 (build_result dict 必含 status/command,
    package dict 必含 name/type/files, version/release_notes/deployment
    非空 str)。build_result.status/command 非空 str、package.name/type
    非空 str + files 非空 list 为 exec 侧增强校验 — org 侧契约只保证
    dict 含键 (双体系一致, 同 architect endpoints 策略)。
    """
    errors: list[str] = []
    for f in ("version", "release_notes", "deployment"):
        v = payload.get(f)
        if not isinstance(v, str) or not v.strip():
            errors.append(f"{f}: expected non-empty str")
    build = payload.get("build_result")
    if not isinstance(build, dict) or not build:
        errors.append("build_result: expected non-empty dict")
    elif not all(k in build for k in _BUILD_RESULT_KEYS):
        errors.append("build_result: missing required keys 'status', 'command'")
    else:
        errors.extend(_validate_build_result(build))
    pkg = payload.get("package")
    if not isinstance(pkg, dict) or not pkg:
        errors.append("package: expected non-empty dict")
    elif not all(k in pkg for k in _PACKAGE_KEYS):
        errors.append("package: missing required keys 'name', 'type', 'files'")
    else:
        errors.extend(_validate_package(pkg))
    return errors


def _validate_build_result(build: dict[str, Any]) -> list[str]:
    """build_result 深度结构: status/command 均非空 str (构建成败/命令)。"""
    errors: list[str] = []
    for key in _BUILD_RESULT_KEYS:
        val = build.get(key)
        if not isinstance(val, str) or not val.strip():
            errors.append(f"build_result.{key}: expected non-empty str")
    return errors


def _validate_package(pkg: dict[str, Any]) -> list[str]:
    """package 深度结构: name/type 非空 str + files 非空 list (发布包清单)。"""
    errors: list[str] = []
    for key in ("name", "type"):
        val = pkg.get(key)
        if not isinstance(val, str) or not val.strip():
            errors.append(f"package.{key}: expected non-empty str")
    files = pkg.get("files")
    if not isinstance(files, list) or not files:
        errors.append("package.files: expected non-empty list")
    else:
        for i, f in enumerate(files):
            if not isinstance(f, str) or not f.strip():
                errors.append(f"package.files[{i}]: expected non-empty str")
    return errors


# ------------------------------------------------------------------ prompt


#: Release Agent prompt (Code + Test → 发布产物 5 节; 生产 provider
#: = DeepSeek v4-pro)
_RELEASE_AGENT_PROMPT = (
    "你是一名 DevOps 工程师 (Release Manager)。基于下面的代码产物 (Code "
    "Artifact) 与测试产物 (Test Artifact) 产出结构化发布产物 (Release "
    "Artifact), 覆盖 5 节: \n"
    "- build_result: 构建结果 (对象, 必含 {{status, command}} — 构建成败/命令)\n"
    "- version: 版本号 (字符串, 非空, 语义化版本)\n"
    "- package: 发布包 (对象, 必含 {{name, type, files}} — 名称/类型/文件清单)\n"
    "- release_notes: 发布说明 (字符串, 非空, 面向用户的变更摘要)\n"
    "- deployment: 部署方案 (字符串, 非空, 含部署步骤)\n\n"
    "代码产物:\n{code}\n\n"
    "测试产物:\n{test}\n\n"
    "测试产物必须已通过 (results.passed 为真且 bugs 为空); 未通过测试的 "
    "代码禁止发布。\n"
    "输出 JSON 对象, 5 节字段齐全, 仅输出 JSON, 不要任何多余文字。"
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
    raise ReleaseError("Release output is not valid JSON")


def _parse_release(content: str) -> ReleaseArtifact:
    """LLM 输出 → ReleaseArtifact (宽容解析; 空/垃圾 → ReleaseError)。"""
    data = _extract_json(content)
    if not isinstance(data, dict):
        raise ReleaseError(
            "Release output must be a JSON object (release artifact 5 节)"
        )
    return ReleaseArtifact.from_dict(data)


# ------------------------------------------------------------------ Release Agent


class ReleaseAgent:
    """Release Agent: Code + Test Artifact → 结构化 Release Artifact (5 节)。

    构造 (双输入强校验 + Test VALIDATED 强校验):
    - provider: ProviderInterface (发布 LLM; 生产 DeepSeek v4-pro, 测试
      注入 mock; None → release 时 ReleaseError 响亮)。
    - code: Code Artifact dict (必填 — 构造时缺失 → ReleaseError,
      禁止脱离输入独立生成 — 发布不能凭空捏造)。
    - test: Test Artifact dict (必填 + VALIDATED 强校验: 必须满足 test
      契约 — results dict 必含 passed + bugs list; 未通过测试的产物禁止
      发布 — 质量门禁)。

    方法:
    - release(code=None, test=None) → ReleaseArtifact: LLM 生成 + 本地校验
      (双输入解析链: 方法参数 > 构造绑定; 任一为空 → ReleaseError — 强
      校验全入口生效, 不变量永不被打破)。
    - set_code / set_test: 绑定/替换 (空输入拒绝, 不变量保持)。
    """

    __test__ = False  # pytest 收集豁免 (Test* 前缀类名误匹配)

    def __init__(
        self,
        provider: Any = None,
        *,
        code: dict[str, Any] | None = None,
        test: dict[str, Any] | None = None,
        max_tokens: int = 4096,
    ) -> None:
        self._provider = provider
        self._code = _require_code_input("code", code)
        self._test = _require_test_input("test", test)
        self._max_tokens = int(max_tokens)

    @property
    def provider(self) -> Any:
        return self._provider

    @property
    def code(self) -> dict[str, Any]:
        return self._code

    @property
    def test(self) -> dict[str, Any]:
        return self._test

    def set_code(self, code: dict[str, Any]) -> "ReleaseAgent":
        """绑定/替换 Code Artifact (空输入 → ReleaseError — 强校验)。"""
        self._code = _require_code_input("code", code)
        return self

    def set_test(self, test: dict[str, Any]) -> "ReleaseAgent":
        """绑定/替换 Test Artifact (空输入/未 VALIDATED → ReleaseError)。"""
        self._test = _require_test_input("test", test)
        return self

    def release(
        self,
        code: dict[str, Any] | None = None,
        test: dict[str, Any] | None = None,
    ) -> ReleaseArtifact:
        """Code + Test → Release Artifact (LLM 结构化输出 + 本地契约校验)。

        双输入解析链: 方法参数 > 构造绑定; 任一缺失 → ReleaseError 响亮
        (禁止脱离输入独立生成); test 未 VALIDATED (缺 results.passed /
        bugs) → ReleaseError (未通过测试禁止发布); provider 缺失 / 调用
        失败 / 输出不可解析 / 缺字段 → ReleaseError 响亮 (不假装生成成功);
        输出再经 Workflow Runner CONTRACTS release 校验 (org 侧), 失败 →
        INVALID → stage FAILED。
        """
        # 双输入解析链: 方法显式参数 > 构造绑定 (先解析再校验 — 参数缺省
        # 时回退绑定值, 而非对 None 直接报错; 空 dict/非 dict 仍响亮拒绝)
        code_payload = _require_code_input(
            "code", code if code is not None else self._code
        )
        test_payload = _require_test_input(
            "test", test if test is not None else self._test
        )
        if self._provider is None:
            raise ReleaseError(
                "release generation requires a provider (仅 DeepSeek v4-pro; "
                "测试注入 mock)"
            )
        prompt = _RELEASE_AGENT_PROMPT.format(
            code=_input_summary("code", code_payload),
            test=_input_summary("test", test_payload),
        )
        response = self._provider.generate(
            ProviderRequest(task_context=prompt, max_tokens=self._max_tokens)
        )
        if not response.ok or not (response.content or "").strip():
            raise ReleaseError(
                f"release generation failed: {response.error or 'empty provider response'}"
            )
        return _parse_release(response.content)


def _require_code_input(name: str, payload: Any) -> dict[str, Any]:
    """code 输入强校验: 非 dict / 空 dict → ReleaseError 响亮 (禁止脱离
    输入独立生成 — 发布不能凭空捏造)。"""
    if payload is None:
        raise ReleaseError(
            f"{name} artifact required (ReleaseAgent 构造双输入强校验 — "
            f"禁止脱离 code + test 独立生成)"
        )
    if not isinstance(payload, dict):
        raise ReleaseError(
            f"{name} artifact must be a dict, got {type(payload).__name__}"
        )
    if not payload:
        raise ReleaseError(
            f"{name} artifact must not be empty (双输入强校验 — 禁止脱离 "
            f"输入独立生成)"
        )
    return payload


def _require_test_input(name: str, payload: Any) -> dict[str, Any]:
    """test 输入强校验: 非 dict / 空 dict → ReleaseError; 且 Test 必须
    VALIDATED (满足 test 契约: results dict 必含 passed + bugs list —
    与 org CONTRACTS test 同源) — 未通过测试的产物禁止发布 (质量门禁)。"""
    if payload is None:
        raise ReleaseError(
            f"{name} artifact required (ReleaseAgent 构造双输入强校验 — "
            f"禁止脱离 code + test 独立生成)"
        )
    if not isinstance(payload, dict):
        raise ReleaseError(
            f"{name} artifact must be a dict, got {type(payload).__name__}"
        )
    if not payload:
        raise ReleaseError(
            f"{name} artifact must not be empty (双输入强校验 — 禁止脱离 "
            f"输入独立生成)"
        )
    # Test VALIDATED 强校验: 未通过测试的产物禁止发布 (质量门禁 —
    # 契约驱动, 与 org CONTRACTS test 同源: results 必含 passed + bugs)
    results = payload.get("results")
    if not isinstance(results, dict) or "passed" not in results:
        raise ReleaseError(
            f"{name} artifact must be VALIDATED (test 契约: results dict "
            f"必含 passed — 未通过测试的产物禁止发布)"
        )
    if "bugs" not in payload:
        raise ReleaseError(
            f"{name} artifact must be VALIDATED (test 契约: bugs list 必填 "
            f"— 未通过测试的产物禁止发布)"
        )
    return payload


def _input_summary(name: str, payload: dict[str, Any]) -> str:
    """Code/Test Artifact → prompt 摘要 (Release 消费节前置, 其余节保留;
    各自截断防上下文撑爆)。"""
    sections = (
        _CODE_RELEASE_SECTIONS if name == "code" else _TEST_RELEASE_SECTIONS
    )
    ordered = [k for k in sections if k in payload]
    ordered += [k for k in payload if k not in ordered]
    lines = "\n".join(
        f"{k}: {json.dumps(payload[k], ensure_ascii=False)}" for k in ordered
    )
    return lines[: _INPUT_SUMMARY_LIMIT]


# ------------------------------------------------------------------ Workflow 接入


def build_release_executor(
    agent: ReleaseAgent,
) -> Callable[[Any, dict[str, Any]], dict[str, Any]]:
    """ReleaseAgent → Workflow executor 适配器 (release stage,
    role_ref=devops)。

    返回 dict 契约 (S7-003 _register_outputs 消费):
    - artifact_type: "release" (显式声明; ROLE_OUTPUT_TYPES 默认
      devops→release 保持向后兼容, 不覆盖)
    - ref: 产物引用 (file:///dist/release.json)
    - metadata: Release Artifact 契约载荷 (5 节 + artifact_refs 强引用;
      Runner 自动注册 → CONTRACTS release 校验 → VALIDATED / INVALID →
      stage FAILED)

    双输入解析链 (架构 §2 ⑥ + S8-004 强引用):
    - context inputs 中 code + test 产物 (type 匹配, metadata = 契约
      载荷) 必须同时存在 — 任一缺失 → ReleaseError (stage FAILED —
      诚实, 禁止脱离输入独立生成; agent 构造虽已绑定 payload, executor
      仍要求 context 输入, 因为 artifact_refs 强引用需要输入产物 id)。
    - test 产物必须 VALIDATED (metadata 满足 test 契约: results.passed +
      bugs — 未通过测试禁止发布; 由 _require_test_input 强校验)。
    - artifact_refs: [code_id, test_id] 写入 metadata — 发布产物显式
      引用输入产物 id (审计/溯源, 任务清单硬性要求)。
    """

    def executor(stage: Any, context: dict[str, Any]) -> dict[str, Any]:
        code = _artifact_from_context(context, "code")
        test = _artifact_from_context(context, "test")
        if code is None or test is None:
            raise ReleaseError(
                "release executor needs BOTH code and test artifacts "
                "(context inputs, 带 id 强引用) — 禁止脱离输入独立生成"
            )
        artifact = agent.release(code["metadata"], test["metadata"])
        metadata = artifact.to_dict()
        metadata["artifact_refs"] = [code["id"], test["id"]]
        return {
            "artifact_type": "release",
            "ref": "file:///dist/release.json",
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
