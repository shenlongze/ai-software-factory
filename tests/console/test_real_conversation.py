"""tests/console/test_real_conversation.py — 真实会话回归 (v1.1.215).

Founder 2026-08-27: 会话问题不能靠一个个加关键词修 — 语义优先 + 把踩过的坑固化成回归测试,
防止"修一个漏一个"。

覆盖 (全部是 Founder 实测 WebUI 会话踩过的坑):
1. "扫描代码" → code_scan (不被关键词"扫描"劫持成 project_scan)
2. "了解项目真实结构" → project_structure (不是 project_status 进度状态)
3. "是真正影响项目的么" → deep_analyze 验证 (不是 chat 泛答)
4. "调整任务" → 不落 chat (task_action / 至少非闲聊)
5. 防退化: 明确操作 + LLM 误判 chat → 锁操作意图
6. LLM 不可用 → 关键词兜底仍可用
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from factory_console.session import query_engine as _qe


def _llm(prompt: str) -> str:
    """模拟语义正确的 LLM 意图判定 (从 prompt 提取用户消息)。"""
    q = str(prompt or "").split("用户: ")[-1].strip()
    mapping = {
        "扫描代码": "code_scan",
        "扫代码": "code_scan",
        "了解项目真实结构": "project_structure",
        "项目结构": "project_structure",
        "是真正影响项目的么": "deep_analyze",
        "这些任务确实是关键的吗": "deep_analyze",
        "项目进度怎么样": "project_status",
        "调整任务": "task_action",
        "把登录做完": "create_task",
    }
    intent = mapping.get(q, "chat")
    task = q if intent in ("create_task", "task_action", "task_continue") else None
    return json.dumps({"intent": intent, "project": None, "task": task})


def _chat_llm(_question: str) -> str:
    """模拟 LLM 退化: 什么都判 chat。"""
    return json.dumps({"intent": "chat", "project": None, "task": None})


class TestRealConversationRegression:
    """Founder 实测踩坑固化 — 语义优先, 不靠加关键词。"""

    def test_scan_code_not_hijacked_by_scan_keyword(self):
        # 关键词"扫描"命中 project_scan, 但 LLM 语义正确 → 采信 code_scan
        assert _qe.parse_intent_llm("扫描代码", _llm)["intent"] == "code_scan"
        assert _qe.parse_intent_llm("扫代码", _llm)["intent"] == "code_scan"
        # 无 LLM 兜底同样正确 (code_scan 规则在 project_scan 前)
        assert _qe.parse_intent("扫描代码")["intent"] == "code_scan"

    def test_project_structure_not_status(self):
        assert _qe.parse_intent_llm("了解项目真实结构", _llm)["intent"] == "project_structure"
        assert _qe.parse_intent_llm("项目结构", _llm)["intent"] == "project_structure"
        assert _qe.parse_intent("了解项目真实结构")["intent"] == "project_structure"

    def test_skeptical_question_not_chat(self):
        # "是真正影响项目的么" → 验证语义 (deep_analyze 多工具+证据), 不是泛答
        assert _qe.parse_intent_llm("是真正影响项目的么", _llm)["intent"] == "deep_analyze"
        assert _qe.parse_intent_llm("这些任务确实是关键的吗", _llm)["intent"] == "deep_analyze"

    def test_adjust_task_not_chat(self):
        # "调整任务" 是操作语义, 不落 chat
        assert _qe.parse_intent_llm("调整任务", _llm)["intent"] == "task_action"

    def test_op_locked_against_llm_degradation(self):
        # 防退化: 明确操作 + LLM 误判 chat → 锁操作 (不能"聊没")
        assert _qe.parse_intent_llm("标记完成 完善导出功能", _chat_llm)["intent"] == "task_action"
        assert _qe.parse_intent_llm("推送到 github", _chat_llm)["intent"] == "git_push"
        assert _qe.parse_intent_llm("把项目改名为 X", _chat_llm)["intent"] == "project_action"

    def test_keyword_fallback_when_llm_down(self):
        # LLM 不可用 → 关键词兜底仍正确 (降级保护, 不是主路径)
        assert _qe.parse_intent_llm("扫描项目", None)["intent"] == "project_scan"
        assert _qe.parse_intent_llm("有哪些项目", None)["intent"] == "list_projects"
        assert _qe.parse_intent_llm("项目进度怎么样", None)["intent"] == "project_status"

    def test_normal_queries_not_broken(self):
        # 不误伤: 常规查询语义不变
        assert _qe.parse_intent_llm("项目进度怎么样", _llm)["intent"] == "project_status"
        assert _qe.parse_intent_llm("把登录做完", _llm)["intent"] == "create_task"


class TestSkepticalSignal:
    """Founder 实测: "是真正影响项目的么" 无 LLM 时被判 chat → 确定性走验证。"""

    def test_skeptical_deep_analyze_without_llm(self):
        # 不依赖 LLM 的确定性质疑信号 → deep_analyze (多工具+证据), 不是 chat
        assert _qe.parse_intent_llm("是真正影响项目的么", None)["intent"] == "deep_analyze"
        assert _qe.parse_intent_llm("你说的这些真的会影响项目吗", None)["intent"] == "deep_analyze"
        assert _qe.parse_intent_llm("能确定吗", None)["intent"] == "deep_analyze"
        assert _qe.parse_intent_llm("靠谱吗", None)["intent"] == "deep_analyze"

    def test_not_hijacking_normal_queries(self):
        assert _qe.parse_intent_llm("项目进度怎么样", None)["intent"] == "project_status"
        assert _qe.parse_intent_llm("扫描代码", None)["intent"] == "code_scan"
        assert _qe.parse_intent_llm("项目结构", None)["intent"] == "project_structure"
