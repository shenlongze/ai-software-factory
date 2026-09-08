"""S1 第 2 刀 — 执行语义验收: NO_OP 完成态 + BLOCKED 依赖。

验收 D: NO_OP 叶按证据标记 COMPLETED (非假失败); 真实失败仍 FAILED。
验收 B: execute 走 production_run 图 (依赖/BLOCKED 语义生效)。
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "factory-core")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


from factory_console import golden_path as gp  # noqa: E402
from factory_console import task_decomposition as td  # noqa: E402


def _mk_approved(root: str, cid: str, *, feats: list[str]) -> dict:
    """直接构造 Understanding → PRD(带 functional_requirements)→ approve → Plan。"""
    from factory_console import conversation_app as ca
    from factory_console import product_understanding as pu
    svc = ca.ProductUnderstandingService(root)
    svc.process_user_message(cid, "我想做一个飞机大战小游戏。")
    # 直接 upsert REQUIREMENT facts (绕过理解器 — 测试 PRD→树→执行语义, 非 NL 解析)
    for f in feats:
        pu.upsert_fact(root, cid, fact_type="REQUIREMENT",
                       content=f"实现功能: {f}", source_message_id="",
                       confidence=1.0, provenance="test", status="CONFIRMED")
    prd = gp.generate_prd(root, cid)
    gp.approve_prd(root, cid, prd["id"])
    plan = gp.generate_plan(root, cid, decompose=True, decomposer=None)
    gp.approve_plan(root, plan["id"])
    return plan


class TestNoopCompletion:
    def test_expected_files_present_completed(self, tmp_path: Path) -> None:
        """NO_OP: executor 报"未产生新文件"但 expected_files 已存在 → COMPLETED。"""
        from factory_console import conversation_app as ca
        root = str(tmp_path / "factory")
        cid = ca.ConversationApplicationService(root).create(title="t")["id"]
        plan = _mk_approved(root, cid, feats=["移动", "射击"])
        tree = td.load_task_tree(root, plan["id"])
        # 给第一个功能叶 expected_files 并在 workspace 预置文件 (改树本体再落盘)
        for n in tree["nodes"]:
            if n.get("kind") == "task" and "验证" not in n["title"]:
                n["expected_files"] = ["already.txt"]
                break
        td.save_task_tree(root, plan["id"], tree)
        ws = Path(root) / "golden_path_workspace" / cid
        ws.mkdir(parents=True, exist_ok=True)
        (ws / "already.txt").write_text("pre-existing", encoding="utf-8")

        def fake_cap(inp: dict) -> dict:
            return {"ok": False, "error": "未产生新文件 (no change)",
                    "output": {}, "artifact_type": "code_change"}

        out = gp.execute_approved(root, cid, capability_fn=fake_cap)
        moved = next(e for e in out["executed"]
                     if "验证" not in e["task"].get("title", ""))
        r = moved["result"]
        assert r["state"] == "COMPLETED", r  # NO_OP → 完成 (非假失败)
        assert r["verification"] == "PASS"

    def test_real_failure_still_failed(self, tmp_path: Path) -> None:
        """真实失败 (executor 报错且无已存在证据) → FAILED。"""
        from factory_console import conversation_app as ca
        root = str(tmp_path / "factory")
        cid = ca.ConversationApplicationService(root).create(title="t")["id"]
        _mk_approved(root, cid, feats=["移动"])

        def fail_cap(inp: dict) -> dict:
            return {"ok": False, "error": "真正执行失败: 编译错误",
                    "output": {}, "artifact_type": "code_change"}

        out = gp.execute_approved(root, cid, capability_fn=fail_cap)
        assert any(e["result"]["state"] == "FAILED" for e in out["executed"])
        assert any(e["result"]["state"] != "COMPLETED"
                   for e in out["executed"])


class TestBlockedDependency:
    def test_verify_blocked_when_feature_fails(self, tmp_path: Path) -> None:
        """依赖失败 → run FAILED + 下游 (验证叶) 未执行 (production_run 图语义)。"""
        from factory_console import conversation_app as ca
        root = str(tmp_path / "factory")
        cid = ca.ConversationApplicationService(root).create(title="t")["id"]
        _mk_approved(root, cid, feats=["移动", "射击"])

        fail_first = {"first": True}

        def cap(inp: dict) -> dict:
            t = (inp.get("task") or {}).get("title", "")
            if "移动" in str(t) and fail_first["first"]:
                fail_first["first"] = False
                return {"ok": False, "error": "真实失败",
                        "output": {}, "artifact_type": "code_change"}
            return {"ok": True, "output": {"msg": "ok"},
                    "artifact_type": "code_change"}

        out = gp.execute_approved(root, cid, capability_fn=cap)
        states = {str(e["task"].get("title")): e["result"]["state"]
                  for e in out["executed"]}
        # 至少一个功能 FAILED
        assert any(s == "FAILED" for s in states.values()), states
        # production_run 依赖失败 → 下游 (验证叶) 未执行/未 COMPLETED
        # (execute_production_run 串行依赖: node FAILED → run FAILED, 后续不创建)
        verify_done = any("验证" in t and s == "COMPLETED"
                          for t, s in states.items())
        assert not verify_done, states
