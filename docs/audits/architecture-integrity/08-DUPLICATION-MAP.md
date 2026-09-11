# 08 — Duplication Map
- 巨型模块: orchestrator 4209/actions 4133/agent_loop 3840/board 3230 行 —
  职责超载 (P2)
- session 域 12+ 文件 (session.py/conversation.py/chat.py/production_session/
  topic_ledger/...) — 会话职责碎片化 (P2 收敛候选)
- legacy fallback 常驻: 多模块含 legacy/fallback 路径无退出条件 (P2)
- 域 truth 内重复: 少 (健康)
