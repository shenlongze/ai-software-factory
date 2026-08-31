# K5 Conversation ↔ Work Bridge

> 日期: 2026-08-29

## 闭环
```
Conversation (conv_ 实体)
    ├── Requirement (req_ 实体, parent=conv)
    ├── Decision (decision_ 实体, parent=conv)
    ├── Approval (S17, subject_type=task)
    └── Work (project_ → sprint_ → task_ → run → evidence)
         ↓
    Quality Report (8 维评分, conversation_quality)
    ↓
    Golden Suite (G1-G20 验证)
```

## 统一
- 全链 S43 Entity/ID/Lineage (conv→req→project→task→evidence)
- Conversation 可 drill-down 到 Task (operational_state.drill_down)
- Quality 挂钩: 每 conversation 可算质量分 (清晰/一致/不跑题/不遗忘/不幻觉/不越权/不过度行动/结果解释)
