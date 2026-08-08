"""tests/s8/s8_helpers.py — S8 测试构造/断言 helper (唯一名)。

- product_payload_ok: 合法 product 契约载荷 (7 节) — 与 org CONTRACTS
  product 同构 (market_analysis/user_persona/user_journey/problem_statement/
  feature_list/mvp_scope/user_stories)
- product_json: 合法 product 的 JSON 串 (mock provider 注入, 围栏/散文变体)
- uxui_payload_ok: 合法 ux_ui 契约载荷 (7 节) — 与 org CONTRACTS ux_ui
  同构 (information_architecture/user_flow/wireframe/screen_specifications/
  component_definition/design_tokens/prototype); wireframe.screens 每屏
  Screen = {name, ascii, components[], actions[]} (机器可读 ASCII 布局)
- uxui_json: 合法 ux_ui 的 JSON 串 (mock provider 注入, 围栏/散文变体)
- design_payload_ok: 合法 design 契约载荷 (7 节) — 与 org CONTRACTS design
  同构 (system_architecture/technical_stack/database_design/api_design/
  frontend_architecture/backend_architecture/task_breakdown); api_design 必含
  endpoints; task_breakdown 每项含 module/task/api_contract/ui_guidance
  (Developer 消费: 模块/API 约定/UI 实现指导)
- design_json: 合法 design 的 JSON 串 (mock provider 注入, 围栏/散文变体)
- release_payload_ok: 合法 release 契约载荷 (5 节) — 与 org CONTRACTS
  release 同构 (build_result/version/package/release_notes/deployment);
  build_result 必含 status/command; package 必含 name/type/files
- release_json: 合法 release 的 JSON 串 (mock provider 注入, 围栏/散文变体)
- code_payload_ok: 合法 code 契约载荷 (files/changes — Code Artifact)
- qa_payload_ok: 合法 test 契约载荷 (results 含 passed + bugs — Test
  Artifact, VALIDATED 语义; qa = 测试角色别名, 同 ROLE_ALIASES; 命名避开
  test_* 前缀防 pytest 误收集)
- event_sequence / payload_of: 事件库断言辅助 (org.workflow.* / org.stage.*)
- make_idea_artifact: idea 产物 dict (executor context inputs 契约)
- make_product_artifact: product 产物 dict (executor context inputs 契约:
  type == "product", metadata = product 契约载荷)
- make_uxui_artifact: ux_ui 产物 dict (executor context inputs 契约:
  type == "ux_ui", metadata = ux_ui 契约载荷)
- make_code_artifact: code 产物 dict (executor context inputs 契约:
  type == "code", metadata = code 契约载荷)
- make_test_artifact: test 产物 dict (executor context inputs 契约:
  type == "test", metadata = test 契约载荷)
"""

from __future__ import annotations

import json
from typing import Any


def product_payload_ok(*, feature_count: int = 3, story_count: int = 2) -> dict[str, Any]:
    """合法 product 契约载荷 (7 节; feature_list/mvp_scope/user_stories 结构)。"""
    return {
        "market_analysis": "目标市场: 个人记账用户; 竞争: 手工表格/同类 App",
        "user_persona": "25-40 岁上班族, 需要简单记账与月度报表",
        "user_journey": "记录一笔支出 → 查看分类统计 → 月底生成报表",
        "problem_statement": "手工记账繁琐, 现有工具功能过重",
        "feature_list": [f"功能 {i}" for i in range(1, feature_count + 1)],
        "mvp_scope": {
            "in": ["支出记录", "分类统计"],
            "out": ["多人协作", "自动导入账单"],
        },
        "user_stories": [
            {"as-a": "用户", "i-want": "快速记录支出", "so-that": "不遗漏"},
            {"as-a": "用户", "i-want": "查看月度报表", "so-that": "掌握开销"},
        ][:story_count] or ["用户故事占位"],
    }


def product_json(
    *,
    fenced: bool = False,
    prose: bool = False,
    **overrides: Any,
) -> str:
    """合法 product 的 JSON 串 (mock provider 注入; 围栏/散文变体可叠加)。"""
    payload = product_payload_ok()
    payload.update(overrides)
    body = json.dumps(payload, ensure_ascii=False)
    if fenced:
        body = f"```json\n{body}\n```"
    if prose:
        body = f"以下是产品分析结果:\n{body}\n以上为全部内容。"
    return body


def uxui_payload_ok(*, screen_count: int = 2) -> dict[str, Any]:
    """合法 ux_ui 契约载荷 (7 节; wireframe.screens 每屏含 name/ascii/
    components/actions — 机器可读 ASCII 布局, 不生成图片文件)。"""
    screens = [
        {
            "name": f"screen_{i}",
            "ascii": f"+----------+\n| 屏幕 {i} |\n+----------+",
            "components": ["header", "content"],
            "actions": ["点击进入下一屏"],
        }
        for i in range(1, screen_count + 1)
    ]
    return {
        "information_architecture": {
            "screens": [s["name"] for s in screens],
            "navigation": "底部 Tab 导航: 首页/记录/报表",
        },
        "user_flow": [
            {"step": "打开应用", "screen": "screen_1"},
            {"step": "记录一笔支出", "screen": "screen_2"},
            {"step": "查看月度报表", "screen": "screen_1"},
        ],
        "wireframe": {"screens": screens},
        "screen_specifications": [
            {
                "screen": "screen_1",
                "elements": ["余额卡片", "近期流水"],
                "behaviors": ["下拉刷新", "点击流水进入详情"],
                "acceptance": ["余额展示正确", "流水按时间倒序"],
            },
            {
                "screen": "screen_2",
                "elements": ["金额输入", "分类选择"],
                "behaviors": ["提交后返回首页", "分类必选"],
                "acceptance": ["金额校验通过才可提交"],
            },
        ],
        "component_definition": [
            {"name": "BalanceCard", "description": "余额展示卡片",
             "usage": "首页顶部"},
            {"name": "AmountInput", "description": "金额输入框",
             "usage": "记录页"},
        ],
        "design_tokens": {
            "colors": {"primary": "#1A73E8", "background": "#FFFFFF"},
            "typography": {"title": "18px/600", "body": "14px/400"},
            "spacing": {"xs": 4, "sm": 8, "md": 16},
        },
        "prototype": (
            "点击底部 Tab 在首页/记录/报表间切换; 记录页提交表单后返回首页"
            "并刷新余额; 交互纯文本描述, 无外部原型工具依赖。"
        ),
    }


def uxui_json(
    *,
    fenced: bool = False,
    prose: bool = False,
    **overrides: Any,
) -> str:
    """合法 ux_ui 的 JSON 串 (mock provider 注入; 围栏/散文变体可叠加)。"""
    payload = uxui_payload_ok()
    payload.update(overrides)
    body = json.dumps(payload, ensure_ascii=False)
    if fenced:
        body = f"```json\n{body}\n```"
    if prose:
        body = f"以下是 UX/UI 设计产物:\n{body}\n以上为全部内容。"
    return body


def design_payload_ok(*, endpoint_count: int = 2, task_count: int = 3) -> dict[str, Any]:
    """合法 design 契约载荷 (7 节; api_design 必含 endpoints, task_breakdown
    每项含 module/task/api_contract/ui_guidance — Developer 消费: 模块/API
    约定/UI 实现指导)。"""
    endpoints = [
        {
            "method": "GET" if i % 2 else "POST",
            "path": f"/api/v1/resource{i}",
            "contract": f"接口 {i} 契约: 请求/响应数据形状",
        }
        for i in range(1, endpoint_count + 1)
    ]
    tasks = [
        {
            "module": f"module_{i}",
            "task": f"实现模块 {i} 的核心逻辑",
            "api_contract": f"模块 {i} 依赖的 API 约定 (端点/数据形状)",
            "ui_guidance": f"模块 {i} 的 UI 实现指导 (依据 wireframe/spec)",
        }
        for i in range(1, task_count + 1)
    ]
    return {
        "system_architecture": (
            "三层架构: 前端静态页 + 后端 API 服务 + 本地存储; 模块边界清晰, "
            "数据流单向"
        ),
        "technical_stack": {
            "frontend": "HTML/CSS/JS (原生, 无框架)",
            "backend": "Python 标准库 HTTP 服务",
            "database": "JSON 文件存储 (MVP 无外部数据库)",
        },
        "database_design": {
            "models": [
                {"name": "transaction", "fields": ["id", "amount", "category", "date"]},
            ],
            "storage": "data/transactions.json",
        },
        "api_design": {"endpoints": endpoints},
        "frontend_architecture": (
            "页面: 首页/记录/报表; 组件: BalanceCard/AmountInput; 状态: "
            "余额与流水单向数据流"
        ),
        "backend_architecture": (
            "单服务: app.py 路由 + service 层 + storage 层; 模块: "
            "transactions/categories/reports"
        ),
        "task_breakdown": tasks,
    }


def design_json(
    *,
    fenced: bool = False,
    prose: bool = False,
    **overrides: Any,
) -> str:
    """合法 design 的 JSON 串 (mock provider 注入; 围栏/散文变体可叠加)。"""
    payload = design_payload_ok()
    payload.update(overrides)
    body = json.dumps(payload, ensure_ascii=False)
    if fenced:
        body = f"```json\n{body}\n```"
    if prose:
        body = f"以下是技术设计产物:\n{body}\n以上为全部内容。"
    return body


def release_payload_ok(
    *, file_count: int = 2, build_status: str = "success"
) -> dict[str, Any]:
    """合法 release 契约载荷 (5 节; build_result 必含 status/command,
    package 必含 name/type/files — 构建结果/版本/发布包清单/说明/部署)。"""
    return {
        "build_result": {
            "status": build_status,
            "command": "python -m build",
        },
        "version": "1.0.0",
        "package": {
            "name": "demo-app",
            "type": "tar.gz",
            "files": [f"dist/demo-1.0.0.{i}.tar.gz" for i in range(file_count)],
        },
        "release_notes": "首个正式版本: 核心功能完整, 测试全部通过",
        "deployment": "解压发布包 → 安装依赖 → 启动服务 → 健康检查",
    }


def release_json(
    *,
    fenced: bool = False,
    prose: bool = False,
    **overrides: Any,
) -> str:
    """合法 release 的 JSON 串 (mock provider 注入; 围栏/散文变体可叠加)。"""
    payload = release_payload_ok()
    payload.update(overrides)
    body = json.dumps(payload, ensure_ascii=False)
    if fenced:
        body = f"```json\n{body}\n```"
    if prose:
        body = f"以下是发布产物:\n{body}\n以上为全部内容。"
    return body


def code_payload_ok(*, file_count: int = 2) -> dict[str, Any]:
    """合法 code 契约载荷 (files/changes — Code Artifact, Release 输入)。"""
    return {
        "files": [f"src/module_{i}.py" for i in range(1, file_count + 1)],
        "changes": "实现核心功能模块 (S8-005 全链 Demo 代码产物)",
    }


def qa_payload_ok(*, passed: Any = True, bug_count: int = 0) -> dict[str, Any]:
    """合法 test 契约载荷 (results 含 passed + bugs — Test Artifact,
    VALIDATED 语义: 通过 = passed 为真 + bugs 空)。"""

    return {
        "results": {"passed": passed, "total": 3, "failed": 0},
        "bugs": [{"location": f"b{i}"} for i in range(bug_count)],
    }


def event_sequence(store: Any) -> list[str]:
    return [e.type.value for e in store.query()]


def payload_of(store: Any, event_type: str) -> dict[str, Any]:
    for e in store.query():
        if e.type.value == event_type:
            return dict(e.payload)
    raise AssertionError(f"no event of type {event_type!r} found")


def make_idea_artifact(*, idea: str = "开发一个记账 Web App") -> dict[str, Any]:
    """idea 产物 dict (executor context inputs 契约: type + metadata.idea)。"""
    return {"type": "idea", "ref": "file:///idea.txt", "metadata": {"idea": idea}}


def make_product_artifact(
    *, payload: dict[str, Any] | None = None, ref: str = "file:///docs/product.json"
) -> dict[str, Any]:
    """product 产物 dict (executor context inputs 契约: type == "product",
    metadata = product 契约载荷)。"""
    return {"type": "product", "ref": ref, "metadata": payload or product_payload_ok()}


def make_uxui_artifact(
    *, payload: dict[str, Any] | None = None, ref: str = "file:///docs/ux_ui.json"
) -> dict[str, Any]:
    """ux_ui 产物 dict (executor context inputs 契约: type == "ux_ui",
    metadata = ux_ui 契约载荷)。"""
    return {"type": "ux_ui", "ref": ref, "metadata": payload or uxui_payload_ok()}


def make_code_artifact(
    *, payload: dict[str, Any] | None = None, ref: str = "file:///src"
) -> dict[str, Any]:
    """code 产物 dict (executor context inputs 契约: type == "code",
    metadata = code 契约载荷)。"""
    return {"type": "code", "ref": ref, "metadata": payload or code_payload_ok()}


def make_test_artifact(
    *, payload: dict[str, Any] | None = None, ref: str = "file:///test_result.json"
) -> dict[str, Any]:
    """test 产物 dict (executor context inputs 契约: type == "test",
    metadata = test 契约载荷 — VALIDATED 语义: results.passed + bugs)。"""
    return {"type": "test", "ref": ref, "metadata": payload or test_payload_ok()}
