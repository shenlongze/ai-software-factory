#!/usr/bin/env python3
"""conversation 事实层端到端冒烟 —— 需求获取（"目标实跑"）。

为什么需要它:
    本仓无 `tests/` + R16 禁新增顶层目录 ⇒ 功能验收靠可重复脚本。
    本脚本是「需求获取」搬迁（product_understanding → services/conversation/understanding.py）
    的验收证据。

★ 本脚本的重点是**承重环节**: supersession 语义 —— 它是这套机制存在的理由
   （"修改" 不产生新事实、不制造历史噪音）。三种分支都要走一遍。

覆盖:
    ① 创建会话 → understanding.version 从 0 起
    ② 首次 upsert → 1 条事实 · version 1
    ③ 同 key 再次 upsert → **原地更新**（仍 1 条, version 递增）—— 不产生重复
    ④ 同语义槽不同值 → **顶替**（旧 SUPERSEDED + superseded_by; 新 supersedes=[旧]）
       例: 平台 "手机端" → "网页端" = 修改不是新增
    ⑤ 不同槽 → 各自新增（多需求可共存）
    ⑥ transition_fact CONFIRMED → 版本递增 · snapshot 里 CONFIRMED 优先于 PROPOSED
    ⑦ DEFERRED/REJECTED 不参与有效快照, 且出现在 snapshot 的对应列表
    ⑧ 已 SUPERSEDED 的 fact 不可再转换（终态守卫）
    ⑨ build_context → 带 facts 分组
    ⑩ 真写盘核对 conversations/<id>.json

用法: python scripts/smoke_conversation_understanding.py   退出码 0=通过 / 1=失败
副作用: tempdir 数据根, 不碰真实数据 ✓
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ai_factory_os.services.conversation import understanding as U  # noqa: E402

root = Path(tempfile.mkdtemp())
results: list[tuple[str, bool, str]] = []


def chk(name: str, cond: bool, got: str = "") -> None:
    results.append((name, bool(cond), got if not cond else ""))


def main() -> int:
    conv = U.create_conversation(root, title="记账 App")
    cid = conv["id"]
    chk("① 创建会话 → version 0 · 0 事实",
        conv["understanding_version"] == 0 and conv["fact_count"] == 0, str(conv))

    # ② 首次 upsert
    f1 = U.upsert_fact(root, cid, fact_type="IDEA", content="做一个记账 App")
    chk("② 首次 upsert → version 1 · 1 事实",
        U.understanding_version(root, cid) == 1 and len(U.list_facts(root, cid)) == 1,
        f"v={U.understanding_version(root, cid)}")

    # ③ 同 key 再写 → 原地更新（不新增）
    #    注: 必须**完全相同**的 content —— normalize_content 做的是【空白折叠】不是
    #    【去空格】, 所以 "做一个记账 App" 与 "做一个记账App" 是**两个不同 key**。
    #    （这是真实行为, 不是 bug; 我第一版用例误以为两者同 key, 被冒烟抓出来。）
    U.upsert_fact(root, cid, fact_type="IDEA", content="做一个记账 App", confidence=0.9)
    facts = U.list_facts(root, cid, include_inactive=True)
    chk("③ 同 key 再写 → 原地更新（含失效仍 1 条, 无重复）", len(facts) == 1, f"{len(facts)} 条")
    chk("③ 版本仍递增（每次成功写入 +1）", U.understanding_version(root, cid) == 2,
        str(U.understanding_version(root, cid)))
    chk("③ 归一化: 标点全半角归一（，→, 。→.）",
        U.normalize_content("a，b。c") == "a,b.c", U.normalize_content("a，b。c"))

    # ④ 同语义槽不同值 → 顶替
    p_old = U.upsert_fact(root, cid, fact_type="REQUIREMENT", content="平台:手机端")
    p_new = U.upsert_fact(root, cid, fact_type="REQUIREMENT", content="平台:网页端")
    old_after = U.get_fact(root, cid, p_old["id"]) or {}
    chk("④ 同槽不同值 → 旧 fact 变 SUPERSEDED", old_after.get("status") == "SUPERSEDED",
        str(old_after.get("status")))
    chk("④ 旧 fact 记 superseded_by 指向新 fact", old_after.get("superseded_by") == p_new["id"], "")
    chk("④ 新 fact 记 supersedes=[旧]", p_new["supersedes"] == [p_old["id"]], str(p_new["supersedes"]))
    chk("④ 语义槽判定: 平台 → slot:platform",
        U.dimension_of({"type": "REQUIREMENT", "content": "平台:网页端"}) == "slot:platform", "")

    # ⑤ 不同槽 → 各自新增
    U.upsert_fact(root, cid, fact_type="REQUIREMENT", content="支持导出 CSV")
    reqs = U.list_facts(root, cid, fact_type="REQUIREMENT")
    chk("⑤ 不同槽 → 共存（平台 1 + 导出 1 = 2 条有效 REQUIREMENT）", len(reqs) == 2,
        f"{len(reqs)} 条")

    # ⑥ 确认 + 快照优先级
    U.transition_fact(root, cid, f1["id"], to="CONFIRMED", actor="user")
    snap = U.understanding_snapshot(root, cid)
    confirmed = [x for x in snap["facts"] if x["status"] == "CONFIRMED"]
    chk("⑥ CONFIRMED → 出现在有效快照", len(confirmed) == 1, f"{len(confirmed)} 条")
    chk("⑥ 快照 version 与实现一致", snap["version"] == U.understanding_version(root, cid), "")

    # ⑦ DEFERRED / REJECTED
    d = U.upsert_fact(root, cid, fact_type="FUTURE_IDEA", content="以后做多人账本")
    U.transition_fact(root, cid, d["id"], to="DEFERRED")
    r2 = U.upsert_fact(root, cid, fact_type="CONSTRAINT", content="不做云端同步")
    U.transition_fact(root, cid, r2["id"], to="REJECTED")
    snap = U.understanding_snapshot(root, cid)
    chk("⑦ DEFERRED/REJECTED 不进有效快照 · 但各自列出",
        len(snap["deferred"]) == 1 and len(snap["rejected"]) == 1
        and all(x["status"] in ("PROPOSED", "CONFIRMED") for x in snap["facts"]),
        f"deferred={len(snap['deferred'])} rejected={len(snap['rejected'])}")

    # ⑧ 终态守卫
    try:
        U.transition_fact(root, cid, old_after["id"], to="CONFIRMED")
        chk("⑧ 已 SUPERSEDED 不可转换（应抛错）", False, "没有抛错")
    except ValueError as exc:
        chk("⑧ 已 SUPERSEDED 不可转换（终态守卫）", "SUPERSEDED" in str(exc), str(exc)[:60])

    # ⑨ build_context
    ctx = U.build_context(root, cid)
    chk("⑨ build_context → 带 facts + 版本 + 标题",
        ctx["conversation_title"] == "记账 App" and len(ctx["facts"]) > 0
        and ctx["understanding_version"] == U.understanding_version(root, cid), str(list(ctx)))

    # ⑩ 真写盘
    f = root / "conversations" / f"{cid}.json"
    saved = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    chk("⑩ 真写盘: conversations/<id>.json 落地（messages + understanding.facts）",
        isinstance(saved.get("understanding"), dict) and len(saved["understanding"].get("facts", {})) >= 5
        and saved.get("title") == "记账 App",
        json.dumps(saved, ensure_ascii=False)[:110])
    chk("⑩ 项目归属字段存在（Founder 铁律）", "project_id" in saved, str(list(saved))[:80])

    print("── conversation 事实层冒烟（需求获取 · supersession 承重环节）")
    ok = sum(1 for _, v, _ in results if v)
    for n, v, got in results:
        print(f"   [{'PASS' if v else 'FAIL'}] {n}" + (f"   ← {got}" if got else ""))
    print(f"   {ok}/{len(results)} 通过")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
