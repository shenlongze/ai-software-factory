"""K5: Conversation Experience & Control Tower Production Usability。

覆盖:
- Conversation Quality (8 项: 清晰/一致/不跑题/不遗忘/不幻觉/不越权/不过度行动/结果解释)
- Golden Suite (G1-G20)
- Conversation → Work 真闭环 (quality 挂钩)
- CLI / API
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest  # noqa: E402

from factory_console.conversation_os import (  # noqa: E402
    create_conversation, send_message, get_conversation,
)
from factory_console.conversation_quality import (  # noqa: E402
    quality_report, INTERNAL_TERMS,
)
from factory_console.golden_suite import run_suite  # noqa: E402


def _good_factory(node_id):
    def fn(input_data):
        return {"ok": True, "output": {"code": "x"},
                "patch_text": ("diff --git a/a.py b/a.py\n--- /dev/null\n+++ b/a.py\n"
                               "@@ -0,0 +1 @@\nx = 1\n"),
                "artifact_type": "code_change", "verification": {"result": "PASS"}}
    return fn


# --- 用户语言质量: 清晰 (不暴露内部术语) ---

def test_clarity(tmp_path):
    conv = create_conversation(str(tmp_path), title="t")
    send_message(str(tmp_path), conv["id"], "我想做一个产品")
    send_message(str(tmp_path), conv["id"], "目标用户是个人用户")
    q = quality_report(str(tmp_path), conv["id"])
    assert q["quality_score"] >= 50
    assert "scores" in q and "clarity" in q["scores"]
    # 回复不应含内部术语
    c = get_conversation(str(tmp_path), conv["id"])
    for m in c["messages"]:
        if m.get("intent") == "REPLY":
            for t in INTERNAL_TERMS:
                assert t not in m["content"], f"回复暴露内部术语: {t}"


# --- 用户语言质量: 不跑题/不遗忘 (长对话) ---

def test_no_forget_no_drift(tmp_path):
    conv = create_conversation(str(tmp_path), title="t")
    for m in ["我想做一个产品", "目标用户是个人用户, MVP 做记账", "确认",
              "帮我做记账", "今天天气怎么样", "继续做记账"]:
        send_message(str(tmp_path), conv["id"], m)
    q = quality_report(str(tmp_path), conv["id"])
    assert q["scores"]["no_forget"] >= 0.5
    assert q["scores"]["on_topic"] >= 0.2  # 记账 goal 保持
    c = get_conversation(str(tmp_path), conv["id"])
    decisions = " ".join(c["state"]["confirmed_decisions"])
    assert "记账" in decisions  # 不遗忘


# --- 用户语言质量: 不幻觉 (未执行不说执行) ---

def test_no_hallucination(tmp_path):
    conv = create_conversation(str(tmp_path), title="t")
    send_message(str(tmp_path), conv["id"], "我想做一个产品")
    send_message(str(tmp_path), conv["id"], "目标用户是个人")
    q = quality_report(str(tmp_path), conv["id"])
    # 无 work_items, 回复不应说"已完成"
    assert q["scores"]["no_hallucination"] >= 0.5


# --- 用户语言质量: 不过度行动 (讨论不执行) ---

def test_no_overaction(tmp_path):
    conv = create_conversation(str(tmp_path), title="t")
    send_message(str(tmp_path), conv["id"], "我想做一个产品")
    send_message(str(tmp_path), conv["id"], "目标用户是个人")
    q = quality_report(str(tmp_path), conv["id"])
    assert q["scores"]["no_overaction"] >= 0.5  # 无 EXECUTE 意图无 work


# --- Golden Suite 全场景 ---

def test_golden_suite_all(tmp_path):
    r = run_suite(str(tmp_path))
    assert r["passed"] == 20, f"Golden Suite {r['passed']}/20"
    assert r["total"] == 20
    # 每场景有 evidence
    for s in r["scenarios"]:
        assert s["evidence"], f"{s['scenario']} 缺 evidence"


# --- Golden Suite 带真实执行 ---

def test_golden_suite_with_executor(tmp_path):
    r = run_suite(str(tmp_path), executor_factory=_good_factory)
    assert r["passed"] == 20


# --- CLI ---

def test_cli_quality(tmp_path):
    conv = create_conversation(str(tmp_path), title="t")
    send_message(str(tmp_path), conv["id"], "我想做一个产品")
    from factory_console.cli_factory import main as _cli_main
    assert _cli_main(["quality", "report", conv["id"], "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["quality", "suite", "--data-dir", str(tmp_path)]) == 0


# --- API ---

def test_api_quality(tmp_path):
    conv = create_conversation(str(tmp_path), title="t")
    send_message(str(tmp_path), conv["id"], "我想做一个产品")
    from fastapi.testclient import TestClient
    from factory_console.web.backend.fastapi_adapter import build_app
    client = TestClient(build_app(None, factory_root=str(tmp_path)))
    resp = client.get(f"/api/quality/{conv['id']}")
    assert resp.status_code == 200
    assert "quality_score" in resp.json()
    resp = client.post("/api/quality/suite")
    assert resp.status_code == 200
    assert resp.json()["total"] == 20
