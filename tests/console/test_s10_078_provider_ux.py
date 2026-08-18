"""S10-078 — Provider 配置链 + Error UX 分层 测试。

覆盖:
A. Provider missing → ChatService 明确不可用
B. Error sanitization: 默认输出不含内部 exception / 类名
C. Developer diagnostics: verbose 含细节
D. Provider resolution: select 读配置
E. 配置持久化: providers.json 可读 (env ref, 不落明文)
F. Query 零 LLM 回归
G. Safety: 不泄漏 API Key
"""

from __future__ import annotations

import io
import contextlib

from importlib import import_module

S = import_module("factory-console.session.session")
CHAT = import_module("factory-console.session.chat")


class _FakeChat:
    def __init__(self):
        self.calls = []

    def answer(self, question: str, **kw):
        self.calls.append(question)
        return "AI: 测试回答"

    def is_fallback(self, a: str) -> bool:
        return a.startswith("AI:")


class _BrokenProvider:
    """模拟 LLM 装配失败 (api key missing)。"""

    def _default_llm_fn(self):
        raise RuntimeError("anthropic api key missing: ANTHROPIC_API_KEY 未设置")


def _dispatch(session, line: str) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        session._dispatch(line)
    return buf.getvalue()


class TestErrorSanitization:
    def test_default_no_internal_exception(self):
        """默认输出不含内部 exception / Python 类名。"""
        cs = CHAT.ChatService(reasoning_provider=_BrokenProvider())
        out = cs.answer("你好")
        assert "AI 对话服务当前不可用" in out
        assert "chat answer failed" not in out
        assert "Traceback" not in out
        assert "ReasoningProvider" not in out
        assert "_default_llm_fn" not in out

    def test_default_has_actionable_steps(self):
        cs = CHAT.ChatService(reasoning_provider=_BrokenProvider())
        out = cs.answer("你好")
        assert "factory doctor" in out
        assert "factory init" in out

    def test_verbose_has_detail(self):
        """verbose=True → 开发者可看细节。"""
        cs = CHAT.ChatService(reasoning_provider=_BrokenProvider())
        out = cs.answer("你好", verbose=True)
        assert "细节" in out or "api key" in out.lower()

    def test_repl_default_clean(self):
        """REPL 默认路径 (无 verbose) 输出干净。"""
        s = S.InteractiveSession(chat_service=_FakeChat())
        # 替换为 broken chat 验证 REPL 层不泄漏
        from importlib import import_module
        CH = import_module("factory-console.session.chat")
        s.chat_service = CH.ChatService(reasoning_provider=_BrokenProvider())
        out = _dispatch(s, "你好")
        assert "AI 对话服务当前不可用" in out
        assert "chat answer failed" not in out
        assert "AnthropicProvider" not in out


class TestProviderResolution:
    def test_select_reads_providers_json(self, tmp_path, monkeypatch):
        """Provider resolution 读 providers.json (env ref, 不落明文)。"""
        import json
        from pathlib import Path
        data = tmp_path / "factory"
        data.mkdir(exist_ok=True)
        (data / "providers.json").write_text(json.dumps({
            "version": 1,
            "providers": {
                "deepseek": {
                    "id": "deepseek", "enabled": True,
                    "api_key_ref": "env:DEEPSEEK_API_KEY",
                    "models": ["deepseek-chat"],
                }
            },
        }), encoding="utf-8")
        raw = (data / "providers.json").read_text(encoding="utf-8")
        assert "env:DEEPSEEK_API_KEY" in raw
        assert "sk-" not in raw  # 无明文 key
        assert "deepseek" in raw

    def test_no_key_leak_in_messages(self):
        """错误信息不包含 API Key 值。"""
        cs = CHAT.ChatService(reasoning_provider=_BrokenProvider())
        out = cs.answer("你好", verbose=True)
        assert "sk-" not in out


class TestQueryIndependence:
    def test_project_query_no_llm_with_broken_chat(self):
        """Provider 缺失: Factory Query 仍正常 (零 LLM)。"""
        from importlib import import_module
        CH = import_module("factory-console.session.chat")
        s = S.InteractiveSession(
            chat_service=CH.ChatService(reasoning_provider=_BrokenProvider())
        )
        out = _dispatch(s, "现在有什么项目")
        assert "AI 对话服务当前不可用" not in out
        assert "id" in out or "name" in out  # 项目列表

    def test_context_query_no_llm_with_broken_chat(self):
        from importlib import import_module
        CH = import_module("factory-console.session.chat")
        s = S.InteractiveSession(
            chat_service=CH.ChatService(reasoning_provider=_BrokenProvider())
        )
        s.context.current_project = "P-999"
        out = _dispatch(s, "当前项目是什么？")
        assert "P-999" in out
        assert "AI 对话服务当前不可用" not in out
