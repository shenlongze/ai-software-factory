"""tests/console/test_t5_task_continuity_e2e.py — T-5 端到端实测 (T 系列验收)。

Founder 2026-08-27 (T-5): 会话A建任务 → 会话B继续 → 完成 → 会话C审计,
全程上下文连贯 (验收 T-1 锚定 / T-2 上下文注入 / T-3 跨会话恢复)。

真实链路 (HTTP + 真实 service/store, tmp 数据目录):
1. 会话A: "给 测试项目 完善导出功能" → create_task 意图 → 任务真实创建
2. 会话B: "继续做 完善导出功能" → task_continue 意图 → 锚定 task_id +
   跨会话恢复 (找到 A 的上次会话/上次说到); 锚定后发消息 → prompt 注入
   【当前任务】 (T-2 证据)
3. 会话B: "标记完成 完善导出功能" → task_action → 状态机逐步 done (每步审计)
4. 会话C: "继续做 完善导出功能" → 看到 done 状态 + 历史 (审计/溯源);
   GET 任务详情: status=done + history 含创建→完成 + 多个会话 task_id 关联

LLM 用 stub (monkeypatch console_sessions.llm_raw): 确定性意图锁定 +
参数补齐; 回答 prompt 记录以便断言 T-2 上下文注入。
"""

from __future__ import annotations

import importlib
import json
import re
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_FACTORY_CORE = _ROOT / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))

_sessions = importlib.import_module("factory-console.console_sessions")
_adapter = importlib.import_module("factory-console.web.backend.fastapi_adapter")

try:
    from fastapi.testclient import TestClient

    _HAS_FASTAPI = True
except Exception:  # noqa: BLE001
    TestClient = None  # type: ignore[assignment,misc]
    _HAS_FASTAPI = False

requires_fastapi = pytest.mark.skipif(
    not _HAS_FASTAPI, reason="fastapi/httpx 未安装 (console 侧 venv 需安装)"
)

PROJECT_NAME = "测试项目"
TASK_TEXT = "完善导出功能"


def _intent_json(question: str) -> str:
    """确定性参数补齐 (意图由关键词锁定, 这里只补 project/task 参数)。"""
    if "继续做" in question:
        return json.dumps(
            {"intent": "task_continue", "project": PROJECT_NAME, "task": TASK_TEXT}
        )
    if "标记完成" in question:
        return json.dumps(
            {"intent": "task_action", "project": PROJECT_NAME, "task": TASK_TEXT}
        )
    if "完善" in question:
        return json.dumps(
            {"intent": "create_task", "project": PROJECT_NAME, "task": TASK_TEXT}
        )
    return json.dumps({"intent": "chat", "project": None, "task": None})


def _make_app(tmp_path):
    event_logger = None
    service = _adapter.build_console_service(tmp_path, event_logger=event_logger)
    app = _adapter.build_app(service, event_logger=event_logger, factory_root=tmp_path)
    return app


@requires_fastapi
class TestT5TaskContinuityE2E:
    def test_session_a_create_b_continue_c_audit(self, tmp_path, monkeypatch):
        prompts: list[str] = []

        def fake_llm(prompt: str) -> str | None:
            prompts.append(prompt)
            if "把用户的提问转成标准查询意图" in prompt:
                q = prompt.rsplit("用户: ", 1)[-1].strip()
                return _intent_json(q)
            return "（stub 回答: 已按事实卡处理）"

        monkeypatch.setattr(_sessions, "llm_raw", fake_llm)

        with TestClient(_make_app(tmp_path)) as c:
            # ---- 0. 建项目 ----
            r = c.post("/api/projects", json={"idea": "测试产品", "name": PROJECT_NAME})
            assert r.status_code == 201, r.text
            pid = r.json()["project_id"]

            def new_session(title: str) -> str:
                r = c.post(
                    "/api/sessions",
                    json={"scope": "project", "project_id": pid, "title": title},
                )
                assert r.status_code == 200, r.text
                return r.json()["id"]

            # ---- 1. 会话A: 建任务 ----
            sid_a = new_session("会话A")
            r = c.post(
                f"/api/sessions/{sid_a}/messages",
                json={"message": f"给 {PROJECT_NAME} {TASK_TEXT}"},
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["meta"]["intent"] == "create_task", body
            assert body["meta"]["action"] == "created", body
            # 任务 id 从真实 backlog 查 (不靠回复文案 — 真实数据断言)
            r = c.get(f"/api/projects/{pid}/backlog")
            created_tasks = [
                t for t in r.json()["tasks"] if t.get("title") == TASK_TEXT
            ]
            assert len(created_tasks) == 1, created_tasks
            task_id = created_tasks[0]["id"]
            assert created_tasks[0]["status"] == "todo"

            # 会话A 继续做 → 锚定 (成为 T-3「上次会话」证据源)
            r = c.post(
                f"/api/sessions/{sid_a}/messages",
                json={"message": f"继续做 {TASK_TEXT}"},
            )
            assert r.status_code == 200, r.text
            r = c.get("/api/sessions")
            sess_a = next(s for s in r.json()["items"] if s["id"] == sid_a)
            assert sess_a["task_id"] == task_id
            # 再讨论一句 → T-3「上次说到」内容来源
            r = c.post(
                f"/api/sessions/{sid_a}/messages",
                json={"message": "导出要支持 CSV 和 Excel 两种格式"},
            )
            assert r.status_code == 200, r.text

            # ---- 2. 会话B: 继续做 → 锚定 + 跨会话恢复 ----
            sid_b = new_session("会话B")
            prompts.clear()
            r = c.post(
                f"/api/sessions/{sid_b}/messages",
                json={"message": f"继续做 {TASK_TEXT}"},
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["meta"]["intent"] == "task_continue", body
            # 真实 facts 在传给 LLM 的 prompt 里 (回复是 stub) — 断言系统真实产出
            prompt_b = prompts[-1] if prompts else ""
            assert "已锚定任务" in prompt_b and TASK_TEXT in prompt_b, prompt_b
            assert "上次会话" in prompt_b and "会话A" in prompt_b, prompt_b  # T-3 跨会话
            assert "CSV" in prompt_b or "Excel" in prompt_b, prompt_b  # 上次说到接上
            # 会话B 已锚定 task_id
            r = c.get("/api/sessions")
            sess_b = next(s for s in r.json()["items"] if s["id"] == sid_b)
            assert sess_b["task_id"] == task_id

            # ---- T-2: B 锚定后发消息 → prompt 注入【当前任务】 ----
            prompts.clear()
            r = c.post(
                f"/api/sessions/{sid_b}/messages",
                json={"message": "下一步做什么"},
            )
            assert r.status_code == 200, r.text
            task_prompt = prompts[-1] if prompts else ""  # 意图 prompt 在前, 回答 prompt 在后 (含事实卡)
            assert "【当前任务】" in task_prompt, task_prompt
            assert TASK_TEXT in task_prompt and task_id in task_prompt, task_prompt
            assert "下一步:" in task_prompt, task_prompt  # T-2 事实卡含下一步

            # ---- 3. 会话B: 标记完成 (状态机逐步 done, 每步审计) ----
            r = c.post(
                f"/api/sessions/{sid_b}/messages",
                json={"message": f"标记完成 {TASK_TEXT}"},
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["meta"]["intent"] == "task_action", body
            r = c.get(f"/api/projects/{pid}/backlog/task/{task_id}")
            detail = r.json()
            assert detail["status"] == "done", detail
            hist = detail.get("history") or []
            assert len(hist) >= 2, hist  # 创建 + 至少一次推进

            # ---- 4. 会话C: 审计/溯源 ----
            sid_c = new_session("会话C")
            prompts.clear()
            r = c.post(
                f"/api/sessions/{sid_c}/messages",
                json={"message": f"继续做 {TASK_TEXT}"},
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["meta"]["intent"] == "task_continue", body
            prompt_c = prompts[-1] if prompts else ""
            assert "已锚定任务" in prompt_c, prompt_c
            assert "状态: done" in prompt_c or "已完成" in prompt_c, prompt_c  # 审计看到终态
            # 会话C 也锚定
            r = c.get("/api/sessions")
            sess_c = next(s for s in r.json()["items"] if s["id"] == sid_c)
            assert sess_c["task_id"] == task_id
            # 任务 ↔ 会话 关联: 至少 B + C (A 讨论未锚定, 诚实)
            linked = [s for s in r.json()["items"] if s.get("task_id") == task_id]
            assert len(linked) >= 2, linked
            # 全程审计链: 任务详情 history 含创建→完成各步
            r = c.get(f"/api/projects/{pid}/backlog/task/{task_id}")
            detail = r.json()
            assert detail["status"] == "done"
            assert len(detail.get("history") or []) >= 4  # todo→ready→in_progress→review→done
