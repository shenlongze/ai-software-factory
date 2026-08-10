"""tests/console/test_console_suggest.py — S10-007 想法确认对话后端测试。

覆盖 (factory-console/api/projects.py suggest_project + web/backend/
fastapi_adapter.py POST /api/projects/suggest + POST /api/projects {name}):
- suggest_project: LLM 提议 (llm_fn 注入) / 诚实 fallback (ai_generated=false,
  questions=[]) / idea 空 → ValueError
- LLM 输出解析链 (剥围栏/整体 loads/{..} 子串回退/非法 → None)
- _suggest_via_llm 失败安全: 无 key / provider 异常 / 空输出 / 非法 JSON /
  契约缺 suggested_name → None (调用方走 fallback, 不冒充 AI)
- 可读名提炼 (_readable_name_from_idea): "一个记账 App" → "记账"
- POST /api/projects {idea, name}: 显式 name 优先落库; 无 name → 规则 slug
  兜底 (向后兼容旧调用)
- HTTP: POST /api/projects/suggest 200 形状 / 400 空 idea / fallback 标注

真实 LLM 调用不在本文件证明 (禁 mock 当证明 — 单元测试用 llm_fn 注入控制
路径; 真实 DeepSeek 调用由 headless 端到端实测验证)。basename 全仓库唯一。
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_FACTORY_CORE = _ROOT / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))
# _suggest_via_llm 真实路径 import exec.provider (ProviderRequest) — 测试注入
# fake provider 时仍会执行该 import; 挂 factory-exec 保持路径一致
_FACTORY_EXEC = _ROOT / "factory-exec"
if str(_FACTORY_EXEC) not in sys.path:
    sys.path.insert(0, str(_FACTORY_EXEC))

#: factory-console 包名含连字符 → importlib 加载 (同 tests/console 其余测试模式)
_adapter = importlib.import_module("factory-console.web.backend.fastapi_adapter")
_api = importlib.import_module("factory-console.api")
_projects_api = importlib.import_module("factory-console.api.projects")
_wf_runner = importlib.import_module("factory-console.workflow_runner")
_models = importlib.import_module("factory-console.models")


# ------------------------------------------------------------------ 测试桩


class _RecordingService:
    """记录 create_project 调用 (name 优先/兜底断言)。"""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.created = SimpleNamespace(id="P-0001", name="", goal="", lifecycle="idea")

    def create_project(self, idea, **kwargs):
        self.calls.append({"idea": idea, **kwargs})
        return self.created


class _FakeProvider:
    """generate → 固定响应 (ok/content/error 形状同 ProviderResponse)。"""

    def __init__(self, response: SimpleNamespace) -> None:
        self._response = response
        self.requests: list[Any] = []

    def generate(self, request):
        self.requests.append(request)
        return self._response


def _resp(*, ok: bool = True, content: str = "", error: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(ok=ok, content=content, error=error)


# ------------------------------------------------------------------ JSON 解析链 (纯函数)


class TestParseSuggestJson:
    def test_plain_json(self):
        """纯 JSON 对象 → dict。"""
        parsed = _projects_api._parse_suggest_json(
            '{"suggested_name": "记账小助手", "slug": "ledger-app", "summary": "x", "questions": []}'
        )
        assert parsed is not None
        assert parsed["suggested_name"] == "记账小助手"

    def test_fenced_json(self):
        """```json 围栏包裹 → 剥围栏解析。"""
        parsed = _projects_api._parse_suggest_json(
            '```json\n{"suggested_name": "记账小助手"}\n```'
        )
        assert parsed is not None
        assert parsed["suggested_name"] == "记账小助手"

    def test_braced_substring(self):
        """前后多余文字 + {..} 子串 → 回退解析。"""
        parsed = _projects_api._parse_suggest_json(
            '好的, 结果如下: {"suggested_name": "记账小助手"} 希望对你有帮助'
        )
        assert parsed is not None
        assert parsed["suggested_name"] == "记账小助手"

    def test_invalid_json_none(self):
        """非法 JSON / 非对象 → None (调用方走诚实 fallback)。"""
        assert _projects_api._parse_suggest_json("not json at all") is None
        assert _projects_api._parse_suggest_json("[1, 2, 3]") is None
        assert _projects_api._parse_suggest_json("") is None
        assert _projects_api._parse_suggest_json(None) is None


# ------------------------------------------------------------------ 诚实 fallback


class TestFallbackSuggestion:
    def test_readable_name_extraction(self):
        """"一个记账 App" → 可读名 "记账" (去量词/尾部英文后缀)。"""
        suggestion = _projects_api._fallback_suggestion("一个记账 App")
        assert suggestion.suggested_name == "记账"
        assert suggestion.slug == "ledger-app"  # 规则 slug 映射

    def test_fallback_shape(self):
        """fallback 形状: ai_generated=false + questions=[] + 规则名。"""
        suggestion = _projects_api._fallback_suggestion("我想开发一个待办清单")
        assert suggestion.ai_generated is False
        assert suggestion.questions == []  # 诚实: 规则无法提问
        assert suggestion.suggested_name == "待办清单"
        assert "规则" in suggestion.summary  # 明确标注非 AI 理解

    def test_fallback_empty_idea(self):
        """空想法 → 空名 (调用方 400 先行拦截; 纯函数不崩溃)。"""
        suggestion = _projects_api._fallback_suggestion("   ")
        assert suggestion.suggested_name == ""
        assert suggestion.ai_generated is False

    def test_readable_name_verb_prefix(self):
        """动词前缀去除: 开发一个博客网站 → 博客。"""
        assert _projects_api._readable_name_from_idea("开发一个博客网站") == "博客"


# ------------------------------------------------------------------ suggest_project 路由函数


class TestSuggestProject:
    def test_llm_suggestion_passthrough(self):
        """llm_fn 返回建议 → 原样透传 (ai_generated=true 字段完整)。"""
        suggestion = _projects_api.suggest_project(
            object(),
            "一个记账 App",
            llm_fn=lambda idea: _models.IdeaSuggestion(
                idea=idea,
                suggested_name="记账小助手",
                slug="ledger-app",
                summary="一个简单的个人记账工具",
                questions=["是否需要多币种?", "需要报表吗?"],
                ai_generated=True,
            ),
        )
        assert suggestion.ai_generated is True
        assert suggestion.suggested_name == "记账小助手"
        assert suggestion.questions == ["是否需要多币种?", "需要报表吗?"]

    def test_llm_unavailable_falls_back(self):
        """llm_fn → None (LLM 不可用) → 诚实 fallback (不 5xx, 不冒充 AI)。"""
        suggestion = _projects_api.suggest_project(
            object(), "一个记账 App", llm_fn=lambda idea: None
        )
        assert suggestion.ai_generated is False
        assert suggestion.questions == []
        assert suggestion.suggested_name == "记账"

    def test_empty_idea_raises_value_error(self):
        """idea 空 → ValueError (HTTP 层映射 400 — 空想法不分析)。"""
        with pytest.raises(ValueError):
            _projects_api.suggest_project(object(), "   ", llm_fn=lambda idea: None)


# ------------------------------------------------------------------ _suggest_via_llm 失败安全


class TestSuggestViaLlm:
    def test_no_key_returns_none(self, monkeypatch):
        """无 LLM key → None (诚实 fallback 信号, 不发起真实调用)。"""
        monkeypatch.setattr(_wf_runner, "has_llm_key", lambda: False)
        assert _projects_api._suggest_via_llm("一个记账 App") is None

    def test_provider_error_returns_none(self, monkeypatch):
        """Provider 异常 (超时/网络) → None (失败安全 → fallback)。"""
        monkeypatch.setattr(_wf_runner, "has_llm_key", lambda: True)

        def boom(idea):
            raise RuntimeError("provider timeout")

        monkeypatch.setattr(_projects_api, "_build_suggest_provider", boom)
        assert _projects_api._suggest_via_llm("一个记账 App") is None

    def test_empty_response_returns_none(self, monkeypatch):
        """空输出 (reasoning 耗尽/空响应) → None (不冒充 AI 理解)。"""
        monkeypatch.setattr(_wf_runner, "has_llm_key", lambda: True)
        monkeypatch.setattr(
            _projects_api,
            "_build_suggest_provider",
            lambda: _FakeProvider(_resp(content="")),
        )
        assert _projects_api._suggest_via_llm("一个记账 App") is None

    def test_invalid_json_returns_none(self, monkeypatch):
        """非法 JSON 输出 → None (解析失败 → 诚实 fallback)。"""
        monkeypatch.setattr(_wf_runner, "has_llm_key", lambda: True)
        monkeypatch.setattr(
            _projects_api,
            "_build_suggest_provider",
            lambda: _FakeProvider(_resp(content="抱歉, 我没法理解")),
        )
        assert _projects_api._suggest_via_llm("一个记账 App") is None

    def test_missing_name_contract_returns_none(self, monkeypatch):
        """契约缺 suggested_name → None (名称必填, 缺 → 不冒充)。"""
        monkeypatch.setattr(_wf_runner, "has_llm_key", lambda: True)
        monkeypatch.setattr(
            _projects_api,
            "_build_suggest_provider",
            lambda: _FakeProvider(_resp(content='{"summary": "x", "questions": []}')),
        )
        assert _projects_api._suggest_via_llm("一个记账 App") is None

    def test_valid_llm_output(self, monkeypatch):
        """合法 LLM 输出 → IdeaSuggestion (ai_generated=true; questions 收窄 ≤3)。"""
        monkeypatch.setattr(_wf_runner, "has_llm_key", lambda: True)
        provider = _FakeProvider(
            _resp(
                content=(
                    '{"suggested_name": "记账小助手", "slug": "ledger-app", '
                    '"summary": "一个简单的个人记账工具", "questions": ["q1", "q2", "q3", "q4"]}'
                )
            )
        )
        monkeypatch.setattr(_projects_api, "_build_suggest_provider", lambda: provider)
        suggestion = _projects_api._suggest_via_llm("一个记账 App")
        assert suggestion is not None
        assert suggestion.ai_generated is True
        assert suggestion.suggested_name == "记账小助手"
        assert suggestion.slug == "ledger-app"
        assert len(suggestion.questions) == 3  # 上限 3 个澄清问题
        assert provider.requests[0].max_tokens == 2048  # 小调用预算


# ------------------------------------------------------------------ POST /api/projects {idea, name}


class TestCreateProjectExplicitName:
    def test_explicit_name_preferred(self):
        """显式 name (用户确认) 优先 → service.create_project(name=用户确认名)。"""
        service = _RecordingService()
        summary = _projects_api.create_project(service, "一个记账 App", name="记账小助手")
        assert summary is not None
        call = service.calls[0]
        assert call["name"] == "记账小助手"  # 非规则 slug (ledger-app)

    def test_no_name_rule_fallback(self):
        """无 name → 规则 slug 兜底 (旧 {idea} 调用向后兼容)。"""
        service = _RecordingService()
        summary = _projects_api.create_project(service, "一个记账 App")
        assert summary is not None
        assert service.calls[0]["name"] == "ledger-app"

    def test_blank_name_rule_fallback(self):
        """name 空白串 → 视同未提供 (规则兜底, 不落空白名)。"""
        service = _RecordingService()
        _projects_api.create_project(service, "一个记账 App", name="   ")
        assert service.calls[0]["name"] == "ledger-app"

    def test_created_summary_reflects_explicit_name(self):
        """创建摘要 name = 显式名 (org 回显优先, 无 → 显式名兜底)。"""
        service = _RecordingService()
        summary = _projects_api.create_project(service, "一个记账 App", name="记账小助手")
        assert summary is not None
        assert summary.name == "记账小助手"
        assert summary.idea == "一个记账 App"


# ------------------------------------------------------------------ HTTP (fastapi + httpx)


try:
    from fastapi.testclient import TestClient  # noqa: E402

    _HAS_FASTAPI = True
except Exception:
    TestClient = None  # type: ignore[assignment,misc]
    _HAS_FASTAPI = False

requires_fastapi = pytest.mark.skipif(
    not _HAS_FASTAPI, reason="fastapi/httpx 未安装 (console 侧 venv 需安装)"
)


@requires_fastapi
class TestSuggestHttp:
    @pytest.fixture
    def client(self, factory_root: Path, event_logger):
        """真实装配 (build_console_service → org ProjectStore 落盘 factory_root/org)。"""
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        app = _adapter.build_app(service, event_logger=event_logger)
        with TestClient(app) as c:
            yield c

    def test_suggest_200_shape(self, client, monkeypatch):
        """POST /api/projects/suggest → 200 {idea, suggested_name, slug, summary,
        questions, ai_generated} (LLM 路径经 monkeypatch 注入 — 形状断言)。"""
        monkeypatch.setattr(
            _projects_api,
            "_suggest_via_llm",
            lambda idea: _models.IdeaSuggestion(
                idea=idea,
                suggested_name="记账小助手",
                slug="ledger-app",
                summary="一个简单的个人记账工具",
                questions=["是否需要多币种?"],
                ai_generated=True,
            ),
        )
        resp = client.post("/api/projects/suggest", json={"idea": "一个记账 App"})
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) == {
            "idea",
            "suggested_name",
            "slug",
            "summary",
            "questions",
            "ai_generated",
        }
        assert body["suggested_name"] == "记账小助手"
        assert body["ai_generated"] is True

    def test_suggest_empty_idea_400(self, client):
        """idea 空 → 400 (空想法不分析, 不发起 LLM 调用)。"""
        resp = client.post("/api/projects/suggest", json={"idea": "   "})
        assert resp.status_code == 400
        assert "idea is required" in resp.json()["detail"]

    def test_suggest_fallback_200_with_flag(self, client, monkeypatch):
        """LLM 不可用 → 200 fallback (ai_generated=false + questions=[] — 前端
        据此标注"快速模式"; 不 5xx, 用户仍可确认创建)。"""
        monkeypatch.setattr(_projects_api, "_suggest_via_llm", lambda idea: None)
        resp = client.post("/api/projects/suggest", json={"idea": "一个记账 App"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["ai_generated"] is False
        assert body["questions"] == []
        assert body["suggested_name"] == "记账"

    def test_create_with_explicit_name_201(self, client):
        """POST /api/projects {idea, name} → 201, 名称 = 用户确认名 (非规则 slug)。"""
        resp = client.post(
            "/api/projects", json={"idea": "一个记账 App", "name": "记账小助手"}
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "记账小助手"
        assert body["idea"] == "一个记账 App"
