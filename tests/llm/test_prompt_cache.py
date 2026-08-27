"""提示缓存意识单测 (S10-127 P2.1)。

覆盖:
- Anthropic body: system 带 cache_control ephemeral
- openai_compat: 响应 usage → out["usage"]
- anthropic: 响应 usage → out["usage"]
- session_audit: prompt_tokens/completion_tokens 落盘
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_LG = _ROOT / "factory-console" / "session" / "llm_gateway.py"
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


@pytest.fixture(scope="module")
def lg():
    spec = importlib.util.spec_from_file_location("llm_gateway", _LG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fake_urlopen(factory):
    import urllib.request

    class FakeResp:
        def __init__(self, data):
            self._d = json.dumps(data).encode("utf-8")
        def read(self):
            return self._d
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def _open(req, timeout=120):
        return FakeResp(factory(req))

    return _open


def test_anthropic_cache_control(lg, monkeypatch):
    captured = {}

    def factory(req):
        body = json.loads(req.data.decode("utf-8"))
        captured["body"] = body
        return {"content": [{"type": "text", "text": "ok"}],
                "usage": {"input_tokens": 100, "output_tokens": 20}}

    monkeypatch.setattr(lg.urllib.request, "urlopen", _fake_urlopen(factory))
    r = lg._anthropic_complete(
        [{"role": "system", "content": "静态前缀"},
         {"role": "user", "content": "hi"}],
        None, model="claude-x", base_url="", api_key="k",
        temperature=0.2, timeout=10,
    )
    sys_block = captured["body"]["system"]
    assert sys_block[0]["type"] == "text"
    assert sys_block[0]["cache_control"] == {"type": "ephemeral"}
    assert r["usage"] == {"prompt_tokens": 100, "completion_tokens": 20}


def test_openai_compat_usage(lg, monkeypatch):
    def factory(req):
        return {"choices": [{"message": {"content": "ok", "tool_calls": []}}],
                "usage": {"prompt_tokens": 55, "completion_tokens": 7}}
    monkeypatch.setattr(lg.urllib.request, "urlopen", _fake_urlopen(factory))
    r = lg._openai_compat_complete(
        [{"role": "user", "content": "hi"}], None,
        model="m", base_url="http://x/chat/completions", api_key="k",
        temperature=0.2, timeout=10,
    )
    assert r["usage"] == {"prompt_tokens": 55, "completion_tokens": 7}


def test_audit_records_tokens(tmp_path):
    from factory_console.session import session_audit as _sa

    _sa.audit(str(tmp_path), session_id="s1", question="q", intent="chat",
              emotion="", tools=[], total_calls=1, rounds=1,
              duration_ms=10, answer_len=2, converge="autonomous",
              answer="ok", prompt_tokens=123, completion_tokens=45)
    day = _sa._now_iso()[:10]
    rec = json.loads((Path(tmp_path) / "session_audit" / f"{day}.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert rec["prompt_tokens"] == 123
    assert rec["completion_tokens"] == 45
