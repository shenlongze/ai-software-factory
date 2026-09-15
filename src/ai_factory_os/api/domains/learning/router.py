"""学习 域 HTTP 适配（api/domains/learning）。

补记（2026-09-15）: 这一域是**补上的** —— 契约域（12）与服务域（9）都有 `learning`,
产品核心定位里「学习自治」也是头等事, 唯独 API 面漏了, 导致老 CLI 有一整类命令
无归处（`learn` / `learning` / `promotion` / `experience` / `optimization` /
`optimize` / `select` / `strategy`）。补齐后三层对齐: 契约 = 服务 = API。

定位（主链第 8 环）: 经验回流 —— 执行与验收的产物沉淀成经验, 反过来影响后续的
选择（agent / provider / skill / workflow / project / decision）。

纪律（见 docs/design/api-structure.md §2）:
  · 只做 HTTP 适配: 解析 → 调用 services/learning/ 的用例 → 包络
  · 禁 import 任何 _pending_migration/** 的模块 ✗
  · 禁跨域直调 services/<别的域>/ ✗（跨域走 contracts/）
  · 禁在 router 里直接读写数据文件 ✗（存储只经 services/ 或 infrastructure/）

本域实况: **API 面尚无端点**（骨架）。服务侧已有 `services/learning/`
（history_search / 经验与决策等）。老区对应实现仍由 `_pending_migration` 承担 ——
端点搬迁待排。
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/learning", tags=["学习"])
