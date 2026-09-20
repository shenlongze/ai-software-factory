"""拆解粒度（granularity）—— 判"这个叶拆到位了吗"。

【判据来源（Founder 定的, 见 skill ⑥/⑦）】
  「④ 拆解: ★ 每个叶能不能【用一句话写出验收标准】? 不能 ⇒ 还没拆到位」
  以及 ⑦ 的防重犯: **质量不靠"模型一次做对"（换 3 版 prompt 都试过了, 全 0 children）**,
  而靠【人机协作】: LLM 出初稿 → 人看得懂 → 人改（`tasktree expand`）→ 人确认。
  ⇒ 所以本模块**不改 prompt 逼模型递归**, 只做两件事:
     ① 把"拆得不够"变成**可判断的**（下面三条代理判据, 每条都给证据）
     ② 把结果**报出来** + 给出该敲的命令, 让"人改"这一步真的能发生

【代理判据（在真实树 17 叶上校准过: 挑出 15, 放过 2 个真单件的）】
  ① 没验收: 验收为空 ⇒ 写不出验收 ⇒ 谈不上"一句话"
  ② 验收分段: 验收里用 "；" 分成 ≥2 段 ⇒ 至少两个可独立验收的结果
  ③ 标题枚举: 标题里顿号 "、" ≥3 项 ⇒ 多件事拼在一句里
     （≥3 而非 ≥2: "发票渲染为 PDF/图片" 这种两项是天然一件事, 不该误报）
  每条都回报证据（第几段/第几项）, 便于人判断 —— 判据本身也要能被质疑。
"""

from __future__ import annotations

from typing import Any

_SEG = "；"          #: 验收里的并列交付物分隔
_ENUM = "、"         #: 标题里的枚举分隔
_MAX_ENUM = 3        #: 标题顿号 ≥ 这个数 ⇒ 多件事


def reasons_for(node: dict[str, Any]) -> list[str]:
    """逐条判据 ⇒ 命中原因（带证据）。空列表 = 拆到位了。

    ★ 只判【叶】（kind=task）: 域/模块本来就不是"一件事", 拿"一句话验收"去卡它没意义
      （守卫抓出过: 没拦 kind ⇒ 域也被判成"没拆到位"）。
    """
    if str(node.get("kind") or "task") != "task":
        return []
    out: list[str] = []
    acc = str(node.get("acceptance") or "").strip()
    title = str(node.get("title") or node.get("display_name") or "").strip()
    if not acc:
        out.append("没有验收标准（写不出 ⇒ 谈不上'一句话'）")
    segs = [s for s in acc.split(_SEG) if s.strip()]
    if len(segs) >= 2:
        out.append(f"验收分成 {len(segs)} 段独立交付（每段都是一个可验收结果）")
    enums = [x for x in title.split(_ENUM) if x.strip()]
    if len(enums) >= _MAX_ENUM:
        out.append(f"标题里枚举 {len(enums)} 件事（顿号分隔）")
    return out


def oversized(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """可能没拆到位的叶（只判 kind=task）—— [{id, title, reasons}]。"""
    out: list[dict[str, Any]] = []
    for n in nodes:
        if n.get("kind") != "task":
            continue
        why = reasons_for(n)
        if why:
            out.append({"id": str(n.get("id") or ""),
                        "title": str(n.get("display_name") or n.get("title") or ""),
                        "reasons": why})
    return out


def summary(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    """粒度汇总（给 CLI / 视图 / 进度用同一口径）—— 含"怎么改"的命令提示。"""
    leaves = [n for n in nodes if n.get("kind") == "task"]
    over = oversized(nodes)
    return {
        "leaves": len(leaves),
        "oversized": len(over),
        "samples": over[:3],
        "basis": f"验收含'{_SEG}'≥2 段 · 标题'{_ENUM}'≥{_MAX_ENUM} 项 · 或没验收",
        "how_to_fix": "factory tasktree expand <plan> --node <域 id> --deep"
                      "（判据同: 一个 agent 一次能做完 + 能独立验收）",
    }
