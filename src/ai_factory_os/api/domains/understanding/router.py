"""需求分析 域 HTTP 适配（api/domains/understanding）。

纪律（见 docs/design/api-structure.md §2）:
  · 只做 HTTP 适配: 解析 → 调用 services/understanding/ 的用例 → 包络
  · 禁 import 任何 _pending_migration/** 的模块 ✗
  · 禁跨域直调 services/<别的域>/ ✗（跨域走 contracts/）
  · 禁在 router 里直接读写数据文件 ✗（存储只经 services/ 或 infrastructure/）

本域实况: 当前并入 conversation 域（Product Understanding）✓
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/understanding", tags=["需求分析"])
