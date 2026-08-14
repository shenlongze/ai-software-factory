"""tests/console/test_session_renderer.py — Renderer 输出层 (S10-047 Task 006)。

设计: docs/sprint10/S10-046-renderer-design.md (§4 渲染层架构 / §5 --json / §6 边界)
覆盖:
- Renderer ABC: abstractmethod render, 不可直接实例化
- HumanRenderer: 文本 (key: value) / 简单表格 (title/header/rows 对齐) /
  错误 (❌ Failed + Reason + Solution) / 成功 (✔) / 成本 (tokens · $ · 秒)
- JsonRenderer: 机器可读 (json.dumps 结构化, json.loads 可回读)
- renderer_for(json_flag): json=True → JsonRenderer; 否则 HumanRenderer (验收 E)
- 输入契约: 非 dict → TypeError

basename 全仓库唯一 (test_session_* 前缀, tests/console 既有模式)。
"""

from __future__ import annotations

import importlib
import inspect
import json

import pytest

RENDER_MOD = importlib.import_module("factory-console.session.renderer")


# ------------------------------------------------------------------ 接口 (Renderer ABC)


def test_renderer_is_abstract():
    assert inspect.isabstract(RENDER_MOD.Renderer)
    with pytest.raises(TypeError):
        RENDER_MOD.Renderer()  # ABC 不可直接实例化


def test_renderers_are_subclasses():
    assert issubclass(RENDER_MOD.HumanRenderer, RENDER_MOD.Renderer)
    assert issubclass(RENDER_MOD.JsonRenderer, RENDER_MOD.Renderer)


def test_render_returns_str():
    assert isinstance(RENDER_MOD.HumanRenderer().render({"ok": True}), str)
    assert isinstance(RENDER_MOD.JsonRenderer().render({"ok": True}), str)


# ------------------------------------------------------------------ HumanRenderer (验收 D: 人类可读)


def test_human_generic_key_value():
    out = RENDER_MOD.HumanRenderer().render({"status": "idle", "count": 3})
    assert out == "status: idle\ncount: 3"


def test_human_generic_nested_json():
    out = RENDER_MOD.HumanRenderer().render({"agents": [{"id": "a"}, {"id": "b"}]})
    assert "agents:" in out and '"id": "a"' in out


def test_human_table_aligned():
    result = {
        "title": "项目清单 (2 个)",
        "header": ["ID", "名称"],
        "rows": [["P-001", "my-app"], ["P-002", "demo-app"]],
    }
    out = RENDER_MOD.HumanRenderer().render(result)
    assert "项目清单 (2 个)" in out
    assert "ID" in out and "名称" in out
    assert "P-001" in out and "my-app" in out
    # 列对齐: 同列起始位置一致
    lines = out.splitlines()[1:]
    assert lines[0].index("ID") == lines[1].index("P-001") == lines[2].index("P-002")


def test_human_error_shape():
    result = {
        "ok": False,
        "error": "provider error: deepseek api key missing",
        "solution": "export DEEPSEEK_API_KEY=... 后重试",
    }
    out = RENDER_MOD.HumanRenderer().render(result)
    assert "❌ Failed" in out
    assert "Reason:" in out and "deepseek api key missing" in out
    assert "Solution:" in out and "export DEEPSEEK_API_KEY" in out


def test_human_ok_message():
    assert RENDER_MOD.HumanRenderer().render({"ok": True, "message": "完成"}) == "✔ 完成"


def test_human_cost_shape():
    out = RENDER_MOD.HumanRenderer().render({"tokens": 5549, "cost": 0.0022, "seconds": 41.8})
    assert out == "本次执行: 5,549 tokens · $0.0022 · 41.8 秒"


# ------------------------------------------------------------------ JsonRenderer (验收 D/E: 机器可读)


def test_json_renderer_machine_readable():
    result = {"ok": True, "projects": [{"id": "P-001", "name": "my-app"}]}
    out = RENDER_MOD.JsonRenderer().render(result)
    assert json.loads(out) == result  # 可回读 (CI/脚本消费)
    assert "\n" in out and "  " in out  # indent=2 结构化
    assert '"ok": true' in out


def test_json_renderer_unicode_preserved():
    out = RENDER_MOD.JsonRenderer().render({"msg": "你好"})
    assert "你好" in out  # ensure_ascii=False


# ------------------------------------------------------------------ renderer_for 工厂 (验收 E)


def test_renderer_for_json_flag():
    assert isinstance(RENDER_MOD.renderer_for(json_flag=True), RENDER_MOD.JsonRenderer)
    assert isinstance(RENDER_MOD.renderer_for(json_flag=False), RENDER_MOD.HumanRenderer)
    assert isinstance(RENDER_MOD.renderer_for(), RENDER_MOD.HumanRenderer)  # 默认人类


# ------------------------------------------------------------------ 输入契约


@pytest.mark.parametrize("renderer", [RENDER_MOD.HumanRenderer(), RENDER_MOD.JsonRenderer()])
def test_render_rejects_non_dict(renderer):
    with pytest.raises(TypeError):
        renderer.render(["not", "a", "dict"])
    with pytest.raises(TypeError):
        renderer.render("nope")
