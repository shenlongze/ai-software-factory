#!/usr/bin/env python3
"""会话链端到端冒烟 —— 需求获取 → 语义操作 → 事实 → PRD（"目标实跑"）。

为什么需要它:
    本仓无 `tests/` + R16 禁新增顶层目录 ⇒ 功能验收靠可重复脚本。
    本脚本是会话链三模块搬迁（proposal / interpreter / formalization）的验收证据,
    而且验的是**整条链**（单模块冒烟看不出链断没断）。

链（Golden Path §7）:
    用户消息 → interpreter（LLM）→ proposal（Domain 校验）→ apply → facts
              → formalization（derive）→ PRD（带 provenance 锚点）

覆盖:
    ① 无产品语义分流: 问候 → 不调 LLM、不写 Truth（operations 为空）
    ② ★ LLM 不可用/未接线 → **诚实降级**（CLARIFY），绝不部分写 Truth
    ③ 整链: 注入 LLM → proposal → apply → facts 落盘（带 provenance=semantic:add）
    ④ ★ 闸门: 非法 proposal（幻觉 op）→ 被 validate 挡住 → 降级, Truth 不变
    ⑤ ★ CONFIRM 无对象 → 拒绝（防 LLM 凭空确认）
    ⑥ PRD 派生: 从 facts 组章节 + **provenance 锚点 = 当时的 understanding version**
    ⑦ PRD 生命周期: draft → 有 draft 时再 create → 拒绝（走 update_prd）
    ⑧ PRD 更新 = 重新派生 → version+1 且锚点跟着 understanding 走
    ⑨ render_prd_markdown 只读派生（不改 Truth）
    ⑩ 真写盘核对 conversations/<id>.json（understanding.facts + prds 同文档）

用法: python scripts/smoke_conversation_chain.py       退出码 0=通过 / 1=失败
副作用: tempdir 数据根, 不碰真实数据 ✓
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ai_factory_os.services.conversation import formalization as F  # noqa: E402
from ai_factory_os.services.conversation import interpreter as I  # noqa: E402
from ai_factory_os.services.conversation import proposal as P  # noqa: E402
from ai_factory_os.services.conversation import understanding as U  # noqa: E402

root = Path(tempfile.mkdtemp())
results: list[tuple[str, bool, str]] = []


def chk(name: str, cond: bool, got: str = "") -> None:
    results.append((name, bool(cond), got if not cond else ""))


def main() -> int:
    cid = U.create_conversation(root, title="记账 App")["id"]

    # ① 无产品语义分流（不接线 LLM 也不该调它）
    p1 = I.llm_semantic_interpreter(str(root), cid, "你好", U.understanding_snapshot(root, cid))
    chk("① 问候分流 → operations 空 + 不写 Truth",
        p1["operations"] == [] and len(U.list_facts(root, cid, include_inactive=True)) == 0,
        str(p1)[:90])

    # ② 未接线 LLM → 诚实降级
    p2 = I.llm_semantic_interpreter(str(root), cid, "我要做一个记账 App", U.understanding_snapshot(root, cid))
    chk("② ★ LLM 未接线 → 降级为 CLARIFY（不写 Truth）",
        p2["operations"] == [] and bool(p2.get("question")) and U.understanding_version(root, cid) == 0,
        f"{str(p2)[:80]} v={U.understanding_version(root, cid)}")

    # ③ 接线假 LLM → 走整链
    fake = {"operations": [
        {"op": "ADD", "fact_type": "IDEA", "content": "做一个记账 App", "confidence": 0.95},
        {"op": "ADD", "fact_type": "REQUIREMENT", "content": "运行平台: 手机端"},
        {"op": "ADD", "fact_type": "REQUIREMENT", "content": "支持导出 CSV"},
    ], "reply": "记下了，先按手机端记账做。", "question": "需要多用户吗？"}
    I.bind_lookups(llm_fn=lambda _prompt: json.dumps(fake, ensure_ascii=False))
    prop = I.llm_semantic_interpreter(str(root), cid, "我要做一个记账 App", U.understanding_snapshot(root, cid))
    chk("③ interpreter → 合法 proposal（3 个操作）", len(prop["operations"]) == 3, str(prop)[:100])
    res = P.apply_operations(root, cid, prop["operations"], source_message_id="msg-1")
    chk("③ 链: apply → 3 条事实落盘", len(U.list_facts(root, cid)) == 3, f"{len(res)} ops → {len(U.list_facts(root, cid))} facts")
    idea = [f for f in U.list_facts(root, cid) if f["type"] == "IDEA"][0]
    chk("③ 事实带 provenance=semantic:add + source_message_id 可追溯",
        idea["provenance"] == "semantic:add" and idea["source_message_id"] == "msg-1",
        f"{idea['provenance']} / {idea['source_message_id']}")

    # ④ 闸门: 非法 op 被 validate 挡住
    try:
        P.validate_operation({"op": "DELETE_EVERYTHING", "fact_type": "IDEA", "content": "x"})
        chk("④ ★ 非法语义操作被 validate 挡（拒绝写入）", False, "没有抛错")
    except P.ProposalValidationError:
        chk("④ ★ 非法语义操作被 validate 挡（拒绝写入）", True, "")
    v_before = U.understanding_version(root, cid)
    I.bind_lookups(llm_fn=lambda _p: '{"operations":[{"op":"BOGUS"}],"reply":"x"}')
    p4 = I.llm_semantic_interpreter(str(root), cid, "随便做个东西", U.understanding_snapshot(root, cid))
    chk("④ ★ LLM 幻觉 op → 降级且 Truth 未被污染",
        p4["operations"] == [] and U.understanding_version(root, cid) == v_before,
        f"{str(p4)[:70]}")

    # ⑤ CONFIRM 无对象 → 拒绝
    try:
        P.apply_operations(root, cid, [{"op": "CONFIRM", "fact_type": "DECISION", "content": "从未记录过的决定"}])
        chk("⑤ ★ CONFIRM 无对象 → 拒绝（防凭空确认）", False, "没有抛错")
    except P.ProposalValidationError as exc:
        chk("⑤ ★ CONFIRM 无对象 → 拒绝（防凭空确认）", "无对象" in str(exc), str(exc)[:70])

    # ⑥ PRD 派生 + provenance 锚点
    snap_v = U.understanding_version(root, cid)
    prd = F.create_prd(root, cid, actor="user")
    chk("⑥ PRD 派生 → source 锚点 = 当前 understanding version",
        prd["source_product_understanding_version"] == snap_v and prd["version"] == 1,
        f"锚点={prd['source_product_understanding_version']} v={prd['version']}")
    chk("⑥ PRD 章节从 facts 组装（功能区含 CSV, 概述含想法）",
        any("CSV" in x for x in prd["content"]["functional_requirements"])
        and "记账" in prd["content"]["overview"]["problem"],
        str(prd["content"]["overview"])[:90])
    chk("⑥ PRD 记录 provenance.facts（可追溯来源事实）",
        len(prd["content"]["provenance"]["facts"]) == 3, str(len(prd["content"]["provenance"]["facts"])))

    # ⑦ 已有 draft → 再 create 被拒
    try:
        F.create_prd(root, cid)
        chk("⑦ 已有 draft 时再 create → 拒绝（走 update_prd）", False, "没有抛错")
    except ValueError as exc:
        chk("⑦ 已有 draft 时再 create → 拒绝（走 update_prd）", "draft" in str(exc), str(exc)[:70])

    # ⑧ update = 重新派生 → version+1 + 锚点跟随
    U.upsert_fact(root, cid, fact_type="REQUIREMENT", content="支持导出 Excel")
    new_v = U.understanding_version(root, cid)
    prd2 = F.update_prd(root, cid, prd["id"], actor="user")
    chk("⑧ update_prd → version+1 且锚点跟随新 understanding",
        prd2["version"] == 2 and prd2["source_product_understanding_version"] == new_v,
        f"v={prd2['version']} 锚点={prd2['source_product_understanding_version']} 现={new_v}")

    # ⑨ render 只读派生
    md = F.render_prd_markdown(prd2)
    chk("⑨ render_prd_markdown → 含标题/来源锚点/功能需求",
        md.startswith("# ") and "source understanding v" in md and "Excel" in md,
        md[:80].replace("\n", " "))

    # ⑩ 真写盘
    f = root / "conversations" / f"{cid}.json"
    saved = json.loads(f.read_text(encoding="utf-8"))
    chk("⑩ 真写盘: understanding.facts + prds 同文档（原子一致）",
        isinstance(saved.get("understanding"), dict) and isinstance(saved.get("prds"), list)
        and len(saved["prds"]) >= 1 and len(saved["understanding"]["facts"]) >= 4,
        f"facts={len(saved.get('understanding',{}).get('facts',{}))} prds={len(saved.get('prds',[]))}")

    print("── 会话链冒烟（需求获取 → 语义操作 → 事实 → PRD）")
    ok = sum(1 for _, v, _ in results if v)
    for n, v, got in results:
        print(f"   [{'PASS' if v else 'FAIL'}] {n}" + (f"   ← {got}" if got else ""))
    print(f"   {ok}/{len(results)} 通过")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
