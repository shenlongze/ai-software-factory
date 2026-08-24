"""S10-065 批次 A — DiscoverySession 测试套件。

覆盖: start / process_user_input (单轮+多轮澄清) / detect_missing_fields /
generate_question / apply_answer / build_summary / confirm / create_product /
cancel / 增强字段 (usage_scenarios/mvp_scope/non_functional_requirements) /
持久化 save/load/resume / 失败安全。

验收: A (全状态流转+多轮澄清+增强字段+summary+confirm/cancel) / B (只有
CONFIRMED 才允许 create_product) / C (持久化 save/load/resume 进程退出不丢失)。

装配: tmp_path; 禁真实 LLM/网络; create_product 默认薄调现有 actions
(测试注入 creator 或使用真实 tmp workspace)。
"""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path

import pytest

DIS = import_module("factory-console.session.discovery")

FIELD_ORDER = ("problem", "user", "core_features", "usage_scenarios", "mvp_scope",
               "non_functional_requirements")


def _start(idea: str = "我想做一个台球计分APP", **kw):
    return DIS.DiscoverySession.start(idea, **kw)


def _full_answer(session, answers):
    """依次回答多轮追问, 返回最后结果 dict。"""
    result = None
    for text in answers:
        result = session.process_user_input(text)
    assert result is not None
    return result


FULL_ANSWERS = [
    "台球玩家记分太麻烦",
    "打台球的人",
    "计分, 排名, 记录",
    "球房和家里",
    "第一版只做计分",
    "无特殊要求",
]


# ================================================================== 1. start


class TestStart:
    def test_start_initial_state(self):
        s = _start()
        assert s.current_state == DIS.DiscoveryState.DISCOVERING

    def test_start_first_question_problem(self):
        s = _start()
        assert s.questions
        assert s.questions[-1].field == "problem"
        # S10-101 验收: 首问 question 带进度/生命周期前缀 (两路径同步)
        assert s.questions[-1].question.startswith(
            "流程: [发现]→确认→创建→PRD→工程→开发 (当前: 发现)\n产品定义 0/3:"
        )
        assert "这个产品解决什么问题?" in s.questions[-1].question
        assert s.questions[-1].required is True

    def test_start_initializes_product_intent(self):
        s = _start()
        assert s.product_intent is not None
        assert s.product_intent.raw == "我想做一个台球计分APP"

    def test_start_temp_product_name(self):
        s = _start()
        assert s.product_intent.name.startswith("未命名产品-")

    def test_start_session_id_unique(self):
        a, b = _start(), _start()
        assert a.session_id
        assert a.session_id != b.session_id

    def test_start_workspace_id(self):
        s = _start(workspace_id="ws-1")
        assert s.workspace_id == "ws-1"

    def test_start_idea_empty_ok(self):
        s = _start(idea="")
        assert s.idea == ""
        assert s.current_state == DIS.DiscoveryState.DISCOVERING

    def test_start_custom_session_id(self):
        s = _start(session_id="custom-1")
        assert s.session_id == "custom-1"

    def test_start_pending_full_order(self):
        s = _start()
        assert list(s._pending_fields) == list(FIELD_ORDER)

    def test_start_ask_enhanced_false_pending_required_only(self):
        s = _start(ask_enhanced=False)
        assert list(s._pending_fields) == ["problem", "user", "core_features"]


# ================================================================== 2. missing fields


class TestMissingFields:
    def test_missing_all_required(self):
        s = _start()
        missing = s.detect_missing_fields()
        assert set(missing) == {"产品解决什么问题", "目标用户", "核心功能"}

    def test_missing_partial(self):
        s = _start()
        s.apply_answer("problem", "问题")
        missing = s.detect_missing_fields()
        assert set(missing) == {"目标用户", "核心功能"}

    def test_missing_none_when_complete(self):
        s = _start()
        for field in ("problem", "user", "core_features"):
            s.apply_answer(field, "值")
        assert s.detect_missing_fields() == []

    def test_missing_excludes_enhanced_fields(self):
        s = _start()
        s.apply_answer("problem", "p")
        s.apply_answer("user", "u")
        s.apply_answer("core_features", "f")
        s.apply_answer("usage_scenarios", "场景")
        s.apply_answer("mvp_scope", "范围")
        s.apply_answer("non_functional_requirements", "性能")
        assert s.detect_missing_fields() == []

    def test_required_filled_flag(self):
        s = _start()
        assert s.required_filled() is False
        for field in ("problem", "user", "core_features"):
            s.apply_answer(field, "值")
        assert s.required_filled() is True

    def test_missing_fields_attr_refreshed(self):
        s = _start()
        assert s.missing_fields
        s.apply_answer("problem", "p")
        s.detect_missing_fields()
        assert "产品解决什么问题" not in s.missing_fields


# ================================================================== 3. process_user_input


class TestProcessUserInput:
    def test_single_round_next_question(self):
        s = _start()
        r = s.process_user_input("台球玩家记分麻烦")
        assert r["question"].field == "user"
        assert r["state"] == DIS.DiscoveryState.CLARIFYING

    def test_result_dict_keys(self):
        s = _start()
        r = s.process_user_input("x")
        assert set(r.keys()) == {"state", "question", "summary", "missing_fields", "message"}

    def test_required_answer_applied(self):
        s = _start()
        s.process_user_input("台球玩家记分麻烦")
        assert s.product_intent.problem == "台球玩家记分麻烦"

    def test_multi_round_full_order(self):
        s = _start()
        seen = []
        for text in FULL_ANSWERS:
            r = s.process_user_input(text)
            if r["question"] is not None:
                seen.append(r["question"].field)
        assert seen == ["user", "core_features", "usage_scenarios", "mvp_scope",
                        "non_functional_requirements"]

    def test_full_flow_reaches_ready(self):
        r = _full_answer(_start(), FULL_ANSWERS)
        assert r["state"] == DIS.DiscoveryState.READY_FOR_CONFIRMATION
        assert r["question"] is None
        assert r["missing_fields"] == []

    def test_ready_message_contains_summary_and_prompt(self):
        r = _full_answer(_start(), FULL_ANSWERS)
        assert "产品:" in r["message"]
        assert "确认" in r["message"]

    def test_required_filled_still_asks_enhanced(self):
        s = _start()
        for text in FULL_ANSWERS[:3]:
            s.process_user_input(text)
        assert s.detect_missing_fields() == []
        r = s.process_user_input(FULL_ANSWERS[3])
        assert r["state"] == DIS.DiscoveryState.CLARIFYING
        assert r["question"].field == "mvp_scope"

    def test_blank_rejected(self):
        s = _start()
        r = s.process_user_input("")
        assert "不能为空" in r["message"]
        assert r["state"] == DIS.DiscoveryState.DISCOVERING
        assert r["question"].field == "problem"

    def test_whitespace_rejected(self):
        s = _start()
        r = s.process_user_input("   \t\n ")
        assert "不能为空" in r["message"]
        assert r["question"].field == "problem"

    def test_blank_does_not_advance_field(self):
        s = _start()
        s.process_user_input("")
        r = s.process_user_input("真实回答")
        assert r["question"].field == "user"
        assert s.product_intent.problem == "真实回答"

    def test_input_after_ready_prompts_confirmation(self):
        s = _start()
        _full_answer(s, FULL_ANSWERS)
        r = s.process_user_input("补充信息")
        assert r["state"] == DIS.DiscoveryState.READY_FOR_CONFIRMATION
        assert "确认" in r["message"]

    def test_input_after_confirmed_prompts_confirmation(self):
        s = _start()
        _full_answer(s, FULL_ANSWERS)
        s.confirm()
        r = s.process_user_input("y")
        assert r["state"] == DIS.DiscoveryState.CONFIRMED
        assert "确认" in r["message"]

    def test_input_after_cancelled_terminal_message(self):
        s = _start()
        s.cancel()
        r = s.process_user_input("x")
        assert r["state"] == DIS.DiscoveryState.CANCELLED

    def test_input_after_created_terminal_message(self):
        s = _confirmed_session()
        s.create_product(creator=_fake_creator)
        r = s.process_user_input("x")
        assert r["state"] == DIS.DiscoveryState.PRODUCT_CREATED

    def test_core_features_parsed_to_list(self):
        s = _start()
        s.process_user_input("问题")
        s.process_user_input("用户")
        r = s.process_user_input("计分、排名,记录")
        assert r["question"].field == "usage_scenarios"
        assert s.product_intent.core_features == ["计分", "排名", "记录"]

    def test_ask_enhanced_false_reaches_ready_after_required(self):
        s = _start(ask_enhanced=False)
        r = _full_answer(s, ["问题", "用户", "计分, 排名"])
        assert r["state"] == DIS.DiscoveryState.READY_FOR_CONFIRMATION

    def test_questions_list_grows_with_asked_questions(self):
        s = _start()
        s.process_user_input("问题")
        s.process_user_input("用户")
        fields = [q.field for q in s.questions]
        assert fields == ["problem", "user", "core_features"]

    def test_each_question_asked_once(self):
        s = _start()
        for text in FULL_ANSWERS:
            s.process_user_input(text)
        fields = [q.field for q in s.questions]
        assert fields == list(FIELD_ORDER)


def _fake_creator(workspace, product_intent, **kw):
    return "score-pocket"


def _confirmed_session(**kw):
    s = _start(**kw)
    _full_answer(s, FULL_ANSWERS)
    s.confirm()
    return s


# ================================================================== 4. apply_answer


class TestApplyAnswer:
    def test_apply_problem(self):
        s = _start()
        s.apply_answer("problem", "手动记账麻烦")
        assert s.product_intent.problem == "手动记账麻烦"

    def test_apply_user(self):
        s = _start()
        s.apply_answer("user", "台球爱好者")
        assert s.product_intent.user == "台球爱好者"

    def test_apply_core_features_list(self):
        s = _start()
        s.apply_answer("core_features", "计分, 排名")
        assert s.product_intent.core_features == ["计分", "排名"]

    def test_apply_platform(self):
        s = _start()
        s.apply_answer("platform", "mobile")
        assert s.product_intent.platform == "mobile"

    def test_apply_name(self):
        s = _start()
        s.apply_answer("name", "ScorePocket")
        assert s.product_intent.name == "ScorePocket"

    def test_apply_usage_scenarios(self):
        s = _start()
        s.apply_answer("usage_scenarios", "球房比赛")
        assert s.answers["usage_scenarios"] == "球房比赛"

    def test_apply_mvp_scope(self):
        s = _start()
        s.apply_answer("mvp_scope", "只做计分")
        assert s.answers["mvp_scope"] == "只做计分"

    def test_apply_non_functional(self):
        s = _start()
        s.apply_answer("non_functional_requirements", "响应 < 1s")
        assert s.answers["non_functional_requirements"] == "响应 < 1s"

    def test_apply_records_answers(self):
        s = _start()
        s.apply_answer("problem", "p")
        assert s.answers["problem"] == "p"

    def test_repeated_answer_overwrites(self):
        s = _start()
        s.apply_answer("problem", "第一版")
        s.apply_answer("problem", "第二版")
        assert s.product_intent.problem == "第二版"
        assert s.answers["problem"] == "第二版"

    def test_repeated_enhanced_overwrites(self):
        s = _start()
        s.apply_answer("usage_scenarios", "场景A")
        s.apply_answer("usage_scenarios", "场景B")
        assert s.answers["usage_scenarios"] == "场景B"

    def test_unknown_field_ignored(self):
        s = _start()
        before = s.product_intent.problem
        s.apply_answer("nonexistent_field", "x")  # 不崩溃
        assert s.product_intent.problem == before
        assert "nonexistent_field" not in s.answers

    def test_apply_none_value(self):
        s = _start()
        s.apply_answer("problem", None)
        assert s.product_intent.problem == ""

    def test_apply_whitespace_stripped(self):
        s = _start()
        s.apply_answer("problem", "  问题  ")
        assert s.product_intent.problem == "问题"


# ================================================================== 5. generate_question


class TestGenerateQuestion:
    def test_problem_template(self):
        assert DIS.DiscoverySession.generate_question("problem") == "这个产品解决什么问题?"

    def test_user_template(self):
        assert DIS.DiscoverySession.generate_question("user") == "主要给谁使用?"

    def test_core_features_template(self):
        assert DIS.DiscoverySession.generate_question("core_features") == "核心功能有哪些? (用逗号或顿号分隔)"

    def test_usage_scenarios_template(self):
        assert DIS.DiscoverySession.generate_question("usage_scenarios") == "主要在哪些场景使用?"

    def test_mvp_scope_template(self):
        assert DIS.DiscoverySession.generate_question("mvp_scope") == "第一版范围是什么? (可不填, 默认全量)"

    def test_non_functional_template(self):
        assert DIS.DiscoverySession.generate_question("non_functional_requirements") == "有什么性能/安全/兼容性要求? (可不填)"

    def test_unknown_field_fallback(self):
        assert "请补充" in DIS.DiscoverySession.generate_question("unknown")


# ================================================================== 6. build_summary


class TestBuildSummary:
    def test_summary_full_fields(self):
        s = _start()
        for field, value in zip(FIELD_ORDER, FULL_ANSWERS):
            s.apply_answer(field, value)
        s.apply_answer("platform", "mobile")
        summary = s.build_summary()
        assert isinstance(summary, DIS.DiscoverySummary)
        assert summary.name == s.product_intent.name
        assert summary.problem == "台球玩家记分太麻烦"
        assert summary.user == "打台球的人"
        assert summary.platform == "mobile"
        assert summary.core_features == ["计分", "排名", "记录"]
        assert summary.usage_scenarios == "球房和家里"
        assert summary.mvp_scope == "第一版只做计分"
        assert summary.non_functional_requirements == "无特殊要求"

    def test_summary_defaults_when_missing(self):
        s = _start()
        summary = s.build_summary()
        assert summary.problem == ""
        assert summary.user == ""
        assert summary.core_features == []
        assert summary.usage_scenarios == ""

    def test_summary_stored_on_session(self):
        s = _start()
        s.build_summary()
        assert s.summary is not None

    def test_summary_to_dict_keys(self):
        s = _start()
        d = s.build_summary().to_dict()
        assert set(d.keys()) == {
            "name", "problem", "user", "platform", "core_features",
            "usage_scenarios", "mvp_scope", "non_functional_requirements",
        }

    def test_summary_to_text_lines(self):
        s = _start()
        for field, value in zip(FIELD_ORDER, FULL_ANSWERS):
            s.apply_answer(field, value)
        text = s.build_summary().to_text()
        assert "产品:" in text
        assert "问题:" in text
        assert "目标用户:" in text
        assert "核心功能:" in text
        assert "使用场景:" in text
        assert "MVP 范围:" in text
        assert "非功能要求:" in text

    def test_ready_response_builds_summary(self):
        r = _full_answer(_start(), FULL_ANSWERS)
        assert r["summary"] is not None
        assert r["summary"].usage_scenarios == "球房和家里"


# ================================================================== 7. confirm / cancel


class TestConfirm:
    def test_confirm_from_ready(self):
        s = _confirmed_session()
        assert s.current_state == DIS.DiscoveryState.CONFIRMED

    def test_confirm_idempotent(self):
        s = _confirmed_session()
        s.confirm()
        assert s.current_state == DIS.DiscoveryState.CONFIRMED

    def test_confirm_from_discovering_raises(self):
        s = _start()
        with pytest.raises(DIS.DiscoveryStateError):
            s.confirm()

    def test_confirm_from_clarifying_raises(self):
        s = _start()
        s.process_user_input("问题")
        with pytest.raises(DIS.DiscoveryStateError):
            s.confirm()

    def test_confirm_from_cancelled_raises(self):
        s = _start()
        s.cancel()
        with pytest.raises(DIS.DiscoveryStateError):
            s.confirm()

    def test_confirm_from_created_raises(self):
        s = _confirmed_session()
        s.create_product(creator=_fake_creator)
        with pytest.raises(DIS.DiscoveryStateError):
            s.confirm()


class TestCancel:
    def test_cancel_from_discovering(self):
        s = _start()
        s.cancel()
        assert s.current_state == DIS.DiscoveryState.CANCELLED

    def test_cancel_from_clarifying(self):
        s = _start()
        s.process_user_input("问题")
        s.cancel()
        assert s.current_state == DIS.DiscoveryState.CANCELLED

    def test_cancel_from_ready(self):
        s = _start()
        _full_answer(s, FULL_ANSWERS)
        s.cancel()
        assert s.current_state == DIS.DiscoveryState.CANCELLED

    def test_cancel_from_confirmed(self):
        s = _confirmed_session()
        s.cancel()
        assert s.current_state == DIS.DiscoveryState.CANCELLED

    def test_cancel_idempotent(self):
        s = _start()
        s.cancel()
        s.cancel()
        assert s.current_state == DIS.DiscoveryState.CANCELLED

    def test_cancel_after_created_raises(self):
        s = _confirmed_session()
        s.create_product(creator=_fake_creator)
        with pytest.raises(DIS.DiscoveryStateError):
            s.cancel()


# ================================================================== 8. create_product


class TestCreateProduct:
    def test_create_requires_confirmed(self):
        s = _start()
        with pytest.raises(DIS.DiscoveryStateError):
            s.create_product("ws", creator=_fake_creator)

    def test_create_requires_confirmed_from_clarifying(self):
        s = _start()
        s.process_user_input("问题")
        with pytest.raises(DIS.DiscoveryStateError):
            s.create_product("ws", creator=_fake_creator)

    def test_create_requires_confirmed_from_ready(self):
        s = _start()
        _full_answer(s, FULL_ANSWERS)
        with pytest.raises(DIS.DiscoveryStateError):
            s.create_product("ws", creator=_fake_creator)

    def test_create_requires_confirmed_from_cancelled(self):
        s = _start()
        s.cancel()
        with pytest.raises(DIS.DiscoveryStateError):
            s.create_product("ws", creator=_fake_creator)

    def test_create_success_state_and_id(self):
        s = _confirmed_session()
        pid = s.create_product("ws", creator=_fake_creator)
        assert pid == "score-pocket"
        assert s.current_state == DIS.DiscoveryState.PRODUCT_CREATED
        assert s.created_product_id == "score-pocket"

    def test_create_creator_receives_intent(self):
        captured = {}

        def creator(workspace, product_intent, **kw):
            captured["ws"] = workspace
            captured["pi"] = product_intent
            return "id-1"

        s = _confirmed_session()
        s.create_product("my-workspace", creator=creator)
        assert captured["ws"] == "my-workspace"
        assert captured["pi"] is s.product_intent

    def test_create_default_creator_writes_product_json(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir(parents=True, exist_ok=True)
        s = _confirmed_session()
        pid = s.create_product(ws)
        assert pid
        product_file = ws / "projects" / pid / "product.json"
        assert product_file.is_file()
        data = json.loads(product_file.read_text(encoding="utf-8"))
        assert data["problem"] == "台球玩家记分太麻烦"
        assert data["core_features"] == ["计分", "排名", "记录"]

    def test_create_default_creator_failure_raises(self, tmp_path):
        s = _confirmed_session()
        s.apply_answer("name", "")  # 名字不影响
        with pytest.raises(DIS.DiscoveryStateError):
            s.create_product(tmp_path / "nonexistent-dir" / "x" / "y")  # 目录不可写

    def test_create_result_returned_id(self):
        s = _confirmed_session()
        assert s.create_product(creator=_fake_creator) == "score-pocket"


# ================================================================== 9. 持久化


class TestPersistence:
    def test_save_creates_file(self, tmp_path):
        s = _confirmed_session()
        path = s.save(tmp_path)
        assert path is not None
        assert path.is_file()
        assert path.name == DIS.SESSIONS_FILE_NAME

    def test_load_roundtrip(self, tmp_path):
        s = _confirmed_session()
        s.create_product(creator=_fake_creator)
        s.save(tmp_path)
        loaded = DIS.DiscoverySession.load(tmp_path, s.session_id)
        assert loaded is not None
        assert loaded.session_id == s.session_id
        assert loaded.current_state == DIS.DiscoveryState.PRODUCT_CREATED
        assert loaded.created_product_id == "score-pocket"
        assert loaded.product_intent.problem == s.product_intent.problem
        assert loaded.product_intent.core_features == s.product_intent.core_features
        assert loaded.answers == s.answers

    def test_load_missing_session_none(self, tmp_path):
        assert DIS.DiscoverySession.load(tmp_path, "nope") is None

    def test_load_missing_file_none(self, tmp_path):
        assert DIS.DiscoverySession.load(tmp_path / "empty", "sid") is None

    def test_load_corrupt_file_none(self, tmp_path):
        (tmp_path / DIS.SESSIONS_FILE_NAME).write_text("{broken", encoding="utf-8")
        assert DIS.DiscoverySession.load(tmp_path, "sid") is None

    def test_save_updates_existing_entry(self, tmp_path):
        s = _confirmed_session()
        s.save(tmp_path)
        s.cancel()
        s.save(tmp_path)
        sessions = DIS.DiscoverySession.load_all(tmp_path)
        assert len(sessions) == 1
        assert sessions[0]["current_state"] == DIS.DiscoveryState.CANCELLED

    def test_multiple_sessions_saved(self, tmp_path):
        a = _confirmed_session()
        b = _start(idea="另一个想法")
        a.save(tmp_path)
        b.save(tmp_path)
        assert len(DIS.DiscoverySession.load_all(tmp_path)) == 2

    def test_list_sessions(self, tmp_path):
        s = _start(idea="做一个记录APP")
        s.save(tmp_path)
        items = DIS.DiscoverySession.list_sessions(tmp_path)
        assert len(items) == 1
        assert items[0]["idea"] == "做一个记录APP"
        assert items[0]["state"] == DIS.DiscoveryState.DISCOVERING

    def test_list_sessions_empty(self, tmp_path):
        assert DIS.DiscoverySession.list_sessions(tmp_path) == []

    def test_list_sessions_corrupt_empty(self, tmp_path):
        (tmp_path / DIS.SESSIONS_FILE_NAME).write_text("[]x", encoding="utf-8")
        assert DIS.DiscoverySession.list_sessions(tmp_path) == []

    def test_save_custom_file(self, tmp_path):
        s = _start()
        target = tmp_path / "sub" / "custom.json"
        path = s.save(tmp_path, file=target)
        assert path == target
        assert target.is_file()

    def test_save_failure_safe_returns_none(self, tmp_path):
        blocker = tmp_path / "blocker"
        blocker.write_text("file", encoding="utf-8")
        s = _start()
        assert s.save(blocker) is None  # 目录不可写 → 不抛

    def test_resume_restores_session(self, tmp_path):
        s = _confirmed_session()
        s.save(tmp_path)
        resumed = DIS.DiscoverySession.resume(tmp_path, s.session_id)
        assert resumed is not None
        assert resumed.current_state == DIS.DiscoveryState.CONFIRMED

    def test_resume_missing_raises(self, tmp_path):
        with pytest.raises(DIS.SessionNotFoundError):
            DIS.DiscoverySession.resume(tmp_path, "ghost")

    def test_resume_continues_clarification(self, tmp_path):
        s = _start()
        s.process_user_input("台球玩家记分麻烦")
        s.save(tmp_path)
        resumed = DIS.DiscoverySession.resume(tmp_path, s.session_id)
        r = resumed.process_user_input("打台球的人")
        assert r["question"].field == "core_features"
        assert resumed.product_intent.user == "打台球的人"

    def test_resume_after_cancel(self, tmp_path):
        s = _start()
        s.cancel()
        s.save(tmp_path)
        resumed = DIS.DiscoverySession.resume(tmp_path, s.session_id)
        assert resumed.current_state == DIS.DiscoveryState.CANCELLED

    def test_resume_after_create(self, tmp_path):
        s = _confirmed_session()
        s.create_product(creator=_fake_creator)
        s.save(tmp_path)
        resumed = DIS.DiscoverySession.resume(tmp_path, s.session_id)
        assert resumed.current_state == DIS.DiscoveryState.PRODUCT_CREATED
        assert resumed.created_product_id == "score-pocket"

    def test_resume_full_flow_roundtrip(self, tmp_path):
        s = _start()
        _full_answer(s, FULL_ANSWERS)
        s.save(tmp_path)
        resumed = DIS.DiscoverySession.resume(tmp_path, s.session_id)
        assert resumed.summary is not None
        assert resumed.summary.usage_scenarios == "球房和家里"
        assert resumed.summary.mvp_scope == "第一版只做计分"

    def test_to_dict_from_dict_roundtrip(self, tmp_path):
        s = _confirmed_session()
        s.create_product(creator=_fake_creator)
        s.save(tmp_path)
        raw = DIS.DiscoverySession.load_all(tmp_path)[0]
        restored = DIS.DiscoverySession.from_dict(raw)
        assert restored.session_id == s.session_id
        assert restored.current_state == s.current_state
        assert restored.created_product_id == s.created_product_id

    def test_from_dict_garbage_none(self):
        assert DIS.DiscoverySession.from_dict(None) is None
        assert DIS.DiscoverySession.from_dict({}) is None
        assert DIS.DiscoverySession.from_dict("x") is None


# ================================================================== 10. 状态常量


class TestStateConstants:
    def test_all_states(self):
        assert DIS.DiscoveryState.STATUSES == (
            "discovering", "clarifying", "ready_for_confirmation", "confirmed",
            "product_created", "cancelled",
        )

    def test_state_values(self):
        assert DIS.DiscoveryState.DISCOVERING == "discovering"
        assert DIS.DiscoveryState.CLARIFYING == "clarifying"
        assert DIS.DiscoveryState.READY_FOR_CONFIRMATION == "ready_for_confirmation"
        assert DIS.DiscoveryState.CONFIRMED == "confirmed"
        assert DIS.DiscoveryState.PRODUCT_CREATED == "product_created"
        assert DIS.DiscoveryState.CANCELLED == "cancelled"

    def test_field_order(self):
        assert DIS.FIELD_ORDER == FIELD_ORDER

    def test_required_fields(self):
        assert DIS.REQUIRED_FIELDS == ("problem", "user", "core_features")

    def test_enhanced_fields(self):
        assert DIS.ENHANCED_FIELDS == (
            "usage_scenarios", "mvp_scope", "non_functional_requirements",
        )

    def test_question_dataclass(self):
        q = DIS.DiscoveryQuestion(field="problem", question="?", required=True, hint="h")
        assert q.field == "problem"
        assert q.required is True
        assert q.hint == "h"
