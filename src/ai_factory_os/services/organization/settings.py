"""services.organization.settings — 设置解析链（逐级继承）。

★ 2026-09-19 新增（吸收项 4 · 吸收自 amux 的 "settings resolve card → worker → group → global"）。

【为什么必须有】
    同一个设置（超时 / 并行度 / 用哪个模型 / 预算上限）在不同粒度上应有不同取值:
      · 某个任务卡要特事特办
      · 某个员工（Agent）有自己的偏好
      · 某个部门统一口径
      · 公司级默认
      · 全局兜底
    没有解析链 ⇒ 每个调用点自己写 if/else ⇒ 规则散落、行为不可预测、无法审计。
    有了解析链 ⇒ **一处定义优先级, 处处一致**, 且能回答"这个值为什么是这个"（可解释）。

【优先级（从最具体到最泛, 命中即返回）】
    ① task         任务卡（最具体 —— 特事特办）
    ② member       员工 / Agent（人的偏好）
    ③ department   部门（团队口径）
    ④ company      公司（组织默认）
    ⑤ global       全局兜底（全平台默认）
    ⇒ 新区的组织层级（公司/部门/角色/员工）**比 amux 的 group 更丰富**, 故链更长更贴合"多公司"。

【数据形态（不新增存储）】
    `<root>/org/settings.json`:
      {
        "global":     {"max_parallel": 3, "model": "deepseek-chat"},
        "company":    {"<company_id>": {"model": "deepseek-v4-pro"}},
        "department": {"<department_id>": {"max_parallel": 5}},
        "member":     {"<member_id>": {"model": "deepseek-chat"}},
        "task":       {"<task_or_node_id>": {"max_parallel": 1}}
      }
    每层是"id → {key: value}"。缺层/缺 id/缺 key ⇒ 继续往上一级找（**不报错, 不猜值**）。

【诚实边界】
    · 本模块**只做解析**（读 + 逐级回退）, 不做写入（设置怎么来的由各域自己决定）。
    · 解析结果**带 provenance**（记下"这个值来自哪一级"）—— 可解释是硬要求, 不是装饰。
    · 失败安全: 文件缺失/损坏/层结构不对 ⇒ 当作"无该层", 继续回退到 global / default。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

#: 解析链的层级顺序（从最具体到最泛）—— 改这里即改全局优先级
LAYERS: tuple[str, ...] = ("task", "member", "department", "company", "global")


def _settings_file(root: Path | str) -> Path:
    return Path(root) / "org" / "settings.json"


def _load(root: Path | str) -> dict[str, Any]:
    """读设置库; 任何异常 ⇒ 空 dict（失败安全: 解析链必须能在"没配置"时正常工作）。"""
    p = _settings_file(root)
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 — 失败安全
        return {}


def resolve(
    root: Path | str,
    key: str,
    *,
    task_id: str = "",
    member_id: str = "",
    department_id: str = "",
    company_id: str = "",
    default: Any = None,
) -> dict[str, Any]:
    """按解析链取设置值 —— 返回 {"key", "value", "from", "found", "chain"}。

    `from`: 命中层级名（task/member/department/company/global）或 "default"。
    `chain`: 逐层探查轨迹（每层看到什么）—— 用于回答"为什么是这个值"。
    """
    data = _load(root)
    ids = {"task": task_id, "member": member_id,
           "department": department_id, "company": company_id, "global": ""}
    chain: list[dict[str, Any]] = []

    for layer in LAYERS:
        scope = ids.get(layer, "")
        bucket = data.get(layer) or {}
        # global 层是平铺的 {key: value}; 其余层是 {id: {key: value}}
        if layer == "global":
            if isinstance(bucket, dict) and key in bucket:
                chain.append({"layer": layer, "hit": True, "value": bucket[key]})
                return {"key": key, "value": bucket[key], "from": layer,
                        "found": True, "chain": chain}
            chain.append({"layer": layer, "hit": False, "reason": "global 无此键"})
            continue
        if not scope:
            chain.append({"layer": layer, "hit": False, "reason": "调用方未提供 id"})
            continue
        got = (bucket or {}).get(scope) or {}
        if isinstance(got, dict) and key in got:
            chain.append({"layer": layer, "hit": True, "value": got[key], "scope": scope})
            return {"key": key, "value": got[key], "from": layer,
                    "found": True, "chain": chain}
        chain.append({"layer": layer, "hit": False, "scope": scope, "reason": "该层无此键"})

    return {"key": key, "value": default, "from": "default",
            "found": False, "chain": chain}


def explain(root: Path | str, key: str, **ids: Any) -> str:
    """人类可读的解析说明（"这个值为什么是这个"）—— 逐层轨迹。"""
    r = resolve(root, key, **ids)
    lines = [f"{key} = {r['value']!r}  （来自 {r['from']}）"]
    for c in r["chain"]:
        if c.get("hit"):
            lines.append(f"  ✓ {c['layer']}: {c.get('value')!r}")
        else:
            lines.append(f"  · {c['layer']}: 未命中（{c.get('reason', '')}）")
    return "\n".join(lines)
