"""tests/console/test_query_engine.py — 会话意图→本地真实数据查询 (v1.1.119)。

覆盖 (factory-console/session/query_engine.py + console_sessions 标准输出接线):
- parse_intent 确定性 / parse_intent_llm (LLM JSON/非法→fallback)
- build_facts: 项目列表/单项目状态/质量分/任务/文档/模型/纯对话
- send_message reply_extra: 标准输出指令注入
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_FACTORY_CORE = _ROOT / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))

_qe = importlib.import_module("factory-console.session.query_engine")
_sessions = importlib.import_module("factory-console.console_sessions")


class _P:
    def __init__(self, id, name, stage="idea", status="active", starred=False, progress=0, tasks=None, current_stage=None, workflow_status=None, archived=False):
        self.id = id
        self.name = name
        self.lifecycle_stage = stage
        self.status = status
        self.starred = starred
        self.progress = progress
        self.tasks = tasks or {}
        self.current_stage = current_stage
        self.workflow_status = workflow_status
        self.archived = archived


PROJECTS = [
    _P("P-1", "旅行记账", stage="development", starred=True, progress=0.5, tasks={"done": 3, "todo": 2}, current_stage="开发", workflow_status="running"),
    _P("P-2", "台球计分", stage="confirmed"),
]


class TestParseIntent:
    def test_deterministic(self):
        assert _qe.parse_intent("有哪些项目")["intent"] == "list_projects"
        assert _qe.parse_intent("旅行记账现在什么状态")["intent"] == "project_status"
        assert _qe.parse_intent("这个项目质量怎么样")["intent"] == "project_quality"
        assert _qe.parse_intent("有什么任务")["intent"] == "project_tasks"
        assert _qe.parse_intent("有哪些文档")["intent"] == "project_docs"
        assert _qe.parse_intent("你用什么模型")["intent"] == "model"
        assert _qe.parse_intent("你好")["intent"] == "chat"

    def test_llm_parse_and_fallback(self):
        r = _qe.parse_intent_llm("旅行记账什么状态", lambda p: '{"intent":"project_status","project":"旅行记账"}')
        assert r == {"intent": "project_status", "project": "旅行记账", "task": None}
        r2 = _qe.parse_intent_llm("有哪些项目", lambda p: 'not json')
        assert r2["intent"] == "list_projects"  # fallback 到确定性
        assert r2.get("task") is None
        r3 = _qe.parse_intent_llm("有哪些项目", lambda p: '{"intent":"bogus"}')
        assert r3["intent"] == "list_projects"  # 非法意图 → fallback


class TestBuildFacts:
    def test_list_projects(self, tmp_path):
        facts = _qe.build_facts("有哪些项目", scope="company", project_id=None, projects=PROJECTS, root=tmp_path, model_line="模型: deepseek-chat")
        assert "旅行记账" in facts and "⭐重点项目" in facts
        assert "模型: deepseek-chat" in facts

    def test_project_status_with_hint(self, tmp_path):
        facts = _qe.build_facts("现在什么状态", scope="company", project_id=None, projects=PROJECTS, root=tmp_path, model_line="", hint_project="旅行记账")
        assert "项目: 旅行记账" in facts
        assert "development" in facts

    def test_project_quality_score(self, tmp_path):
        pdir = tmp_path / "projects" / "P-1"
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "quality.json").write_text(json.dumps({"score": 0.72}), encoding="utf-8")
        facts = _qe.build_facts("质量怎么样", scope="company", project_id=None, projects=PROJECTS, root=tmp_path, hint_project="旅行记账")
        assert "0.72" in facts

    def test_tasks_and_docs(self, tmp_path):
        facts = _qe.build_facts("有哪些任务", scope="company", project_id=None, projects=PROJECTS, root=tmp_path, hint_project="旅行记账")
        assert "done:3" in facts
        facts_docs = _qe.build_facts("有哪些文档", scope="company", project_id=None, projects=PROJECTS, root=tmp_path, hint_project="旅行记账")
        assert "文档:" in facts_docs

    def test_chat_no_project_required(self, tmp_path):
        facts = _qe.build_facts("你好", scope="company", project_id=None, projects=PROJECTS, root=tmp_path)
        assert "旅行记账" in facts  # 兜底项目列表


class TestStandardOutput:
    def test_reply_extra_injected(self, tmp_path):
        store = _sessions.SessionStore(tmp_path / "s.json")
        sess = store.create_session(scope="company")
        seen: list[str] = []
        _sessions.send_message(
            store, sess["id"], "有哪些项目",
            facts="项目列表: 旅行记账",
            reply_extra=_qe.STANDARD_OUTPUT_PROMPT,
            llm_fn=lambda p: (seen.append(p) or "【结论】..."),
        )
        assert "【结论】" in seen[0]  # 标准输出指令已注入
        assert "不要编造" in seen[0]
