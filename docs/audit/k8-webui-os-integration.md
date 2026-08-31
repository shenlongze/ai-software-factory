# K8 WebUI ↔ OS Integration

> 日期: 2026-08-29 | 纯审计

## 架构图
```
User
 ↓
WebUI (Human Console: Conversation/Work/Tower)
 ↓
API Contract (api/client.ts → /api/*)
 ↓
AI Factory OS (Service 层: conversation_os/project_os/operational_state)
 ↓
Core (unified_contract/SSOT/Governance/Evidence)
 ↓
Plugin / Workforce / Execution (codex/pytest)
 ↓
Evidence → Projection → API/Realtime → WebUI
```

## 职责边界
| 层 | 负责 |
|----|------|
| WebUI | Presentation / Interaction / Navigation / Human Approval / Visualization |
| OS | Identity / Entity / Lifecycle / Command / Event / State / Governance / Resolution / Execution / Evidence / Lineage / Intelligence |

## WebUI 是否第二业务层?
- **否**: K6 三页全 API 驱动, 零业务状态 (test_k6-human-console 证明)
- 前端不计算 task.status / progress / agent.status (全从 SSOT 投影)
- 唯一前端逻辑 = 轮询刷新 + 呈现 (polling fallback)

## Unified Contract 消费
- 前端用统一 /api/conversations + /api/projects-os + /api/ops/* (S43 风格: {items} 集合 / entity 字段)
- 历史 /api/sessions /api/board 仍被旧页面消费 (未收敛)
