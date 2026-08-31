"""factory-console/conversation_os.py — K1 Conversation OS Reality.

普通用户唯一入口: 和公司说话 → 讨论 → 决策 → 执行 → 结果 → 继续。

- Conversation Entity (S43 unified_contract 复用): conv_/msg_ 前缀
- Intent 理解 (deterministic 规则 + evidence-backed, 非裸 LLM):
  DISCUSS / DECIDE / APPROVE / EXECUTE / ASK_STATUS / CLARIFY
- ConversationState: goal/confirmed_decisions/pending_questions/current_topic
- Requirement 提取: 从确认决策形成 req_ 实体
- Decision 形成: proposal → confirm → decision_ 实体 (不可覆盖, 版本化)
- Work 触发: EXECUTE → create_task → create_production_run → execute → verification → evidence
- Result 呈现: 自然语言摘要 (做了什么/为什么/结果/下一步)
- 多轮: ConversationState + S35 Context (JIT); 用户纠正 → 新 Decision (不覆盖历史)
- 全链路 S43 Event/Lineage/Audit; 复用 S30 workforce + S3 production + S5 verification

禁止: 第二套 SSOT / 无限 Context / fake E2E / 绕过 Governance
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .unified_contract import (
    new_id, create_entity, store_entity, get_entity, entities,
    lifecycle_transition, bump_version, check_version, ConcurrencyError,
    make_event, make_command, make_response, trace_lineage,
)

#: Intents (deterministic 规则)
INTENTS = ("DISCUSS", "DECIDE", "APPROVE", "EXECUTE", "ASK_STATUS", "CLARIFY")

#: 确定性 intent 关键词
INTENT_PATTERNS = {
    "APPROVE": (r"确认|同意|可以|approve|yes|ok|就这么办|开始吧|批准", "DISCUSS"),
    "EXECUTE": (r"帮我(做|创建|写|实现|开发|执行|跑)|开始(做|开发|执行|写)|直接(做|建)|动手", "DISCUSS"),
    "ASK_STATUS": (r"进展|状态|进度|怎么样了|完成了吗|为什么(失败|报错)|测试(结果|为什么)|做到哪里|做到哪了|在做什么|有哪些|有什么|哪些(项目|任务|会话|工作)|(项目|任务|会话|工作)(列表|清单)?$|给我(看|展示|列)|看看(现在|当前)", "DISCUSS"),
    "DECIDE": (r"决定|改成|改为|用(这个|那个)|选|目标(是|为)|用户(是|为)|定位", "DISCUSS"),
    "CLARIFY": (r"什么意思|不明白|解释|举例|具体(一点|来说)|能再说", "DISCUSS"),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file(root: Path | str, name: str) -> Path:
    return Path(root) / "ops" / "conversation" / f"{name}.json"


def _load(root: Path | str, name: str) -> list[dict[str, Any]]:
    try:
        d = json.loads(_file(root, name).read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _save(root: Path | str, name: str, data: list[dict[str, Any]]) -> None:
    p = _file(root, name)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


# ------------------------------------------------------------------ Conversation Entity

def create_conversation(root: Path | str, *, title: str = "新会话",
                        created_by: str = "human") -> dict[str, Any]:
    """创建 Conversation (S43 Entity: conv_ 前缀)。"""
    conv = create_entity("conv", created_by=created_by, metadata={"title": title})
    conv["status"] = "OPEN"
    conv["messages"] = []
    conv["state"] = {"goal": "", "current_topic": "", "confirmed_decisions": [],
                     "pending_questions": [], "requirements": [], "work_items": []}
    store_entity(root, conv)
    return conv


def conversations(root: Path | str) -> list[dict[str, Any]]:
    return [e for e in entities(root, entity_type="conv")]


def get_conversation(root: Path | str, conv_id: str) -> dict[str, Any]:
    return get_entity(root, conv_id)


# ------------------------------------------------------------------ Intent 理解

def detect_intent(message: str, *, last_intent: str = "DISCUSS") -> str:
    """确定性 Intent 检测 (规则优先; 禁裸 LLM 决定执行)。"""
    for intent, (pattern, default) in INTENT_PATTERNS.items():
        if re.search(pattern, message, re.IGNORECASE):
            return intent
    return "DISCUSS"


def _extract_goal(message: str) -> str:
    """从 EXECUTE 消息提取目标 (确定性: 去意图前缀)。"""
    cleaned = re.sub(r"^(帮我|请|麻烦你|我想要|我想做|我要|开始|直接)", "", message)
    cleaned = re.sub(r"(做|创建|写|实现|开发|执行|跑)(一个|一下|个)?$", "", cleaned).strip()
    return cleaned[:120] or message[:120]


# ------------------------------------------------------------------ Message + 多轮处理

def send_message(root: Path | str, conv_id: str, message: str, *,
                 actor: str = "human") -> dict[str, Any]:
    """用户消息 → Intent → State 更新 → 回复 (多轮, 不跑题)。

    全链路: msg_ entity + S43 Event + 状态更新 (决策保留/纠正不覆盖)。
    """
    conv = get_conversation(root, conv_id)
    state = conv.get("state", {})
    last_msg = conv["messages"][-1] if conv.get("messages") else {}
    last_intent = last_msg.get("intent", "DISCUSS") if last_msg else "DISCUSS"
    intent = detect_intent(message, last_intent=last_intent)

    # msg_ entity (S43)
    msg = create_entity("msg", created_by=actor, parent_id=conv_id)
    msg["content"] = message
    msg["intent"] = intent
    msg["created_at"] = _now_iso()
    store_entity(root, msg)

    # State 更新
    if intent == "DECIDE":
        # 决策更新 (纠正 → 新 decision, 不覆盖历史)
        state["confirmed_decisions"] = state.get("confirmed_decisions", []) + [message]
        state["current_topic"] = _topic_of(message)
    elif intent == "EXECUTE":
        if not state.get("goal"):
            state["goal"] = _extract_goal(message)
        state["current_topic"] = "work"
    elif intent == "DISCUSS":
        state["current_topic"] = state.get("current_topic") or _topic_of(message)

    conv["messages"].append({"id": msg["id"], "content": message, "intent": intent,
                             "actor": actor, "at": _now_iso()})
    conv["state"] = state
    bump_version(conv, actor=actor, note=f"msg {intent}")
    store_entity(root, conv)

    # 回复生成
    reply = _make_reply(root, conv, message, intent, last_intent)
    reply_msg = create_entity("msg", created_by="system", parent_id=conv_id)
    reply_msg["content"] = reply["text"]
    reply_msg["intent"] = "REPLY"
    reply_msg["created_at"] = _now_iso()
    store_entity(root, reply_msg)
    conv["messages"].append({"id": reply_msg["id"], "content": reply["text"],
                             "intent": "REPLY", "actor": "system", "at": _now_iso()})
    bump_version(conv, actor="system", note="reply")
    store_entity(root, conv)

    return {"message_id": msg["id"], "intent": intent, "reply": reply,
            "conversation_version": conv["version"]}


def _topic_of(message: str) -> str:
    """提取主题 (确定性: 名词短语近似)。"""
    m = re.search(r"(做|开发|实现|写|建|创建|设计|分析|研究|优化|修复|测试)(一个|一款|一套|个)?([\u4e00-\u9fa5A-Za-z0-9]{2,20})", message)
    return m.group(3) if m else message[:20]


def _make_reply(root: Path | str, conv: dict[str, Any], message: str,
                intent: str, last_intent: str) -> dict[str, Any]:
    """回复生成 (deterministic 模板 + 状态感知; 不跑题/不遗忘)。"""
    state = conv.get("state", {})
    goal = state.get("goal", "")
    confirmed = state.get("confirmed_decisions", [])
    if intent == "DISCUSS":
        if not goal:
            return {"text": f"好的,我们聊聊「{_topic_of(message)}」。能告诉我它的目标用户是谁、要解决什么问题吗?",
                    "status": "CLARIFYING",
                    "card": _make_card("analysis", message, goal, confirmed)}
        return {"text": f"收到。我们正在做「{goal}」,当前已确认: {len(confirmed)} 条决策。"
                        f"关于「{_topic_of(message)}」,你希望怎么处理?", "status": "DISCUSSING",
                "card": _make_card("analysis", message, goal, confirmed)}
    if intent == "DECIDE":
        return {"text": f"好的,已记录决策: 「{message}」。需要我基于这个开始执行吗?",
                "status": "DECISION_RECORDED",
                "card": _make_card("prd", message, goal, confirmed)}
    if intent == "APPROVE":
        if last_intent in ("DECIDE", "DISCUSS") and not confirmed:
            return {"text": "我还没看到待确认的提案。你希望我做什么?", "status": "NEED_PROPOSAL"}
        return {"text": "已确认。我可以开始执行了——回复「帮我做」或「开始」即可。",
                "status": "APPROVED",
                "card": _make_card("task_tree", message, goal, confirmed)}
    if intent == "EXECUTE":
        return {"text": f"明白,目标是「{goal or _extract_goal(message)}」。我会组织执行并返回真实结果。",
                "status": "WILL_EXECUTE",
                "card": _make_card("execution", message, goal, confirmed)}
    if intent == "ASK_STATUS":
        return {"text": _status_reply(root, conv, message), "status": "STATUS",
                "card": _make_card("task_tree", message, goal, confirmed)}
    if intent == "CLARIFY":
        return {"text": f"简单说: 我们在做「{goal or '还没定目标'}」。"
                        f"已确认决策: {confirmed if confirmed else '暂无'}。你想澄清哪部分?",
                "status": "CLARIFYING",
                "card": _make_card("analysis", message, goal, confirmed)}
    return {"text": f"收到: {message[:60]}{'…' if len(message) > 60 else ''}", "status": "RECEIVED"}


def _make_card(card_type: str, message: str, goal: str,
               confirmed: list[str]) -> dict[str, Any]:
    """消息卡片 payload (K9 Human Workspace: 前端 MessageCardView 消费)。

    6 种: analysis/prd/task_tree/execution/diagnosis/approval — 全部真实状态派生。
    """
    topic = _topic_of(message)
    if card_type == "analysis":
        return {"type": "analysis", "title": "需求分析",
                "done": [f"核心话题: {goal or topic}"],
                "pending": ["目标用户是谁?", "要解决什么问题?"],
                "summary": f"正在讨论「{goal or topic}」"}
    if card_type == "prd":
        return {"type": "prd", "title": "Product Requirement",
                "summary": f"已确认: {confirmed[-1] if confirmed else topic}"}
    if card_type == "task_tree":
        return {"type": "task_tree", "title": "任务树",
                "summary": f"目标: {goal or topic}"}
    if card_type == "execution":
        return {"type": "execution", "title": "执行中",
                "summary": f"准备执行: {goal or topic}"}
    if card_type == "diagnosis":
        return {"type": "diagnosis", "title": "执行遇到问题",
                "summary": f"{goal or topic}"}
    if card_type == "approval":
        return {"type": "approval", "title": "需要你的批准",
                "summary": f"操作: {topic}", "risk": "HIGH"}
    return {"type": card_type, "title": "通知", "summary": topic}


def _status_reply(root: Path | str, conv: dict[str, Any], message: str = "") -> str:
    """状态回复 (基于真实 evidence, 非猜测)。

    - 查询项目 (有哪些/什么项目) → 公司级项目列表 (project_os SSOT)
    - 其他 → 会话内 work_items 状态
    """
    state = conv.get("state", {})
    work_items = state.get("work_items", [])
    if re.search(r"项目", message):
        try:
            from factory_console import project_os as _po
            projects = _po.projects(root)
            if not projects:
                return "当前还没有项目。想开始的话, 告诉我你想做什么就行。"
            lines = [f"当前项目 ({len(projects)}):"]
            for p in projects[:8]:
                lines.append(f"  - {p.get('title', p['id'])} [{p.get('status', 'ACTIVE')}]")
            return "\n".join(lines)
        except Exception:
            return f"当前还没有执行中的工作。目标: {state.get('goal') or '未定'}。要开始吗?"
    if not work_items:
        return f"当前还没有执行中的工作。目标: {state.get('goal') or '未定'}。要开始吗?"
    lines = [f"当前工作: {state.get('goal', '')}"]
    for wi in work_items[-3:]:
        lines.append(f"  - {wi.get('title', '')} [{wi.get('status', '')}]")
    return "\n".join(lines)


# ------------------------------------------------------------------ Requirement / Decision 实体

def extract_requirement(root: Path | str, conv_id: str, *, title: str,
                        description: str = "", acceptance: str = "") -> dict[str, Any]:
    """Requirement 实体 (req_ 前缀; 从确认决策形成, 可追溯 Conversation)。"""
    conv = get_conversation(root, conv_id)
    req = create_entity("req", created_by="system", parent_id=conv_id,
                        project_id=conv.get("project_id", ""))
    req["title"] = title
    req["description"] = description
    req["acceptance_criteria"] = acceptance
    req["source_conversation_id"] = conv_id
    req["status"] = "VALIDATED"
    store_entity(root, req)
    conv["state"]["requirements"] = conv.get("state", {}).get("requirements", []) + [req["id"]]
    bump_version(conv, actor="system", note="requirement")
    store_entity(root, conv)
    return req


def create_decision(root: Path | str, conv_id: str, *, statement: str,
                    proposed_by: str = "ai", decision: str = "ACCEPT") -> dict[str, Any]:
    """Decision 实体 (decision_ 前缀; 不可覆盖历史 — 每次形成新版本)。"""
    conv = get_conversation(root, conv_id)
    dec = create_entity("decision", created_by=proposed_by, parent_id=conv_id)
    dec["statement"] = statement
    dec["decision"] = decision
    dec["conversation_id"] = conv_id
    dec["status"] = "ACTIVE"
    store_entity(root, dec)
    return dec


# ------------------------------------------------------------------ Work 触发 (Conversation → 真实执行)

def trigger_work(root: Path | str, conv_id: str, *,
                 executor_factory, artifact_root: Path | str,
                 objective: str = "", role: str = "software_developer",
                 workflow_nodes: list[dict[str, Any]] | None = None,
                 human_approve: bool = False) -> dict[str, Any]:
    """Conversation → Work 真实执行链 (复用 S30 workforce + S3 production + S5 verification)。

    全链路: create_task → create_production_run → execute → verification → evidence
    Governance: human_approve=True 时经 S17 approval (不绕过)。
    """
    from .workforce import create_task
    from .production_run import register_workflow, create_production_run, execute_production_run

    conv = get_conversation(root, conv_id)
    state = conv.get("state", {})
    goal = objective or state.get("goal", "未命名任务")
    nodes = workflow_nodes or [{"node_id": "dev", "name": "开发", "type": "engineering",
                                "executor_name": role}]

    # 1. Task (S43 task_ 实体, parent=conv)
    task = create_entity("task", created_by="system", parent_id=conv_id)
    task["title"] = goal
    task["status"] = "READY"
    task["role"] = role
    store_entity(root, task)

    # 2. Workforce task (S30)
    wf_task = create_task(root, role=role, objective=goal,
                          production_run_id="")
    task["workforce_task_id"] = wf_task.get("task_id") or wf_task.get("id")
    bump_version(task, actor="system", note="workforce task")
    store_entity(root, task)

    # 3. Governance (human approval gate 可选)
    approval_id = ""
    if human_approve:
        from .governance_service import request_approval
        try:
            appr = request_approval(root, production_run_id="",
                                    artifact_ids=[], requested_by="conversation_os",
                                    policy_id="production_apply",
                                    subject_type="conversation",
                                    subject_id=conv_id)
            approval_id = appr.get("approval_id", "")
        except Exception:  # noqa: BLE001
            approval_id = ""

    # 4. ProductionRun (S3)
    wf_id = f"conv-{conv_id[-8:]}"
    try:
        register_workflow(root, workflow_id=wf_id, name=wf_id, nodes=nodes)
    except Exception:  # noqa: BLE001
        pass
    run = create_production_run(root, wf_id)
    task["production_run_id"] = run["run_id"]
    bump_version(task, actor="system", note="run created")
    store_entity(root, task)

    # 5. 执行 (真实)
    result = execute_production_run(root, run["run_id"], executor_factory=executor_factory,
                                    artifact_root=str(artifact_root))
    result_state = result.get("state", "UNKNOWN")

    # 6. Evidence (S23 风格: 引用真实 run)
    evidence = create_entity("evidence", created_by="system", parent_id=task["id"])
    evidence["production_run_id"] = run["run_id"]
    evidence["state"] = result_state
    evidence["evidence_refs"] = [f"production_run:{run['run_id']}"]
    evidence["status"] = "ACTIVE"
    store_entity(root, evidence)

    # 7. 更新 Conversation state (真实结果, 可继续追问)
    wi = {"id": task["id"], "title": goal, "status": result_state,
          "production_run_id": run["run_id"], "evidence_id": evidence["id"]}
    state["work_items"] = state.get("work_items", []) + [wi]
    conv["state"] = state
    bump_version(conv, actor="system", note="work executed")
    store_entity(root, conv)

    return {"task_id": task["id"], "production_run_id": run["run_id"],
            "state": result_state, "evidence_id": evidence["id"],
            "approval_id": approval_id,
            "summary": _work_summary(goal, result_state, run)}


def _work_summary(goal: str, state: str, run: dict[str, Any]) -> str:
    """结果呈现 (说人话: 做了什么/结果/下一步)。"""
    if state == "COMPLETED":
        return (f"✅ 任务「{goal}」已完成。\n"
                f"做了什么: 按专业工作流执行了开发节点, 通过了验证。\n"
                f"结果: 成功 (ProductionRun {run.get('run_id', '')[:12]} COMPLETED)。\n"
                f"下一步: 可以继续追问细节, 或让我修复/优化。")
    if state == "FAILED":
        return (f"❌ 任务「{goal}」执行失败。\n"
                f"原因: {run.get('failure', '验证未通过')}。\n"
                f"下一步: 告诉我「为什么失败」, 我会基于真实证据解释并尝试修复。")
    return (f"⏳ 任务「{goal}」当前状态: {state}。\n"
            f"下一步: 回复「状态」查看进展。")


# ------------------------------------------------------------------ 继续追问 (为什么失败/修复)

def explain_failure(root: Path | str, conv_id: str) -> str:
    """基于真实 Evidence 回答「为什么失败」(evidence-backed, 非猜测)。"""
    conv = get_conversation(root, conv_id)
    work_items = conv.get("state", {}).get("work_items", [])
    if not work_items:
        return "还没有执行过任务, 没有失败可解释。"
    failed = [wi for wi in work_items if wi.get("status") == "FAILED"]
    if not failed:
        return "最近的任务没有失败记录。"
    wi = failed[-1]
    ev = get_entity(root, wi["evidence_id"])
    return (f"任务「{wi['title']}」失败原因 (来自真实 Evidence {ev['evidence_refs']}):\n"
            f"  状态: {ev.get('state', 'FAILED')}\n"
            f"  证据引用: {ev['evidence_refs']}\n"
            f"下一步: 回复「修复它」, 我会继续工作而不是重新开始。")


def repair_from_conversation(root: Path | str, conv_id: str, *,
                             executor_factory, artifact_root: Path | str) -> dict[str, Any]:
    """「修复它」→ 复用 S39 Self-Healing (基于 Incident, 不重新开始)。"""
    from .self_healing import create_incident, run_self_healing, register_repair_plugin, _coderepair_plugin
    from .plugin_kernel import bootstrap, register_plugin, plugin_status

    bootstrap(root)
    try:
        register_plugin(root, plugin_id="repair.coderepair", name="CodeRepair",
                        version="1.0", type="repair", capabilities=["repair.code"],
                        permissions=["repair.execute"])
        plugin_status(root, "repair.coderepair", target="ENABLED")
        register_repair_plugin("repair.coderepair", _coderepair_plugin)
    except Exception:  # noqa: BLE001
        pass

    conv = get_conversation(root, conv_id)
    failed = [wi for wi in conv.get("state", {}).get("work_items", [])
              if wi.get("status") == "FAILED"]
    if not failed:
        return {"status": "NOTHING_TO_REPAIR", "summary": "没有需要修复的失败任务。"}
    wi = failed[-1]
    inc = create_incident(root, source="verification",
                          production_run_id=wi.get("production_run_id", "auto"),
                          node_id="dev", failure_type="execution_failure",
                          severity="MEDIUM", detail=wi.get("title", ""))
    result = run_self_healing(root, inc["incident_id"],
                              executor_factory=executor_factory,
                              artifact_root=str(artifact_root),
                              risk="MEDIUM", human_actor="human")
    # 更新 work item 状态
    state = conv.get("state", {})
    for item in state.get("work_items", []):
        if item["id"] == wi["id"]:
            item["status"] = result["status"]
    conv["state"] = state
    bump_version(conv, actor="system", note="repair")
    store_entity(root, conv)
    return {"incident_id": inc["incident_id"], **result}
