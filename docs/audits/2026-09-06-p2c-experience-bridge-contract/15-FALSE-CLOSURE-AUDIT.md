# 15 — FALSE CLOSURE AUDIT (P2-C CONTRACT, 2026-09-06)

| # | 风险 | 现状 |
|---|---|---|
| F1 | entity 存在≠数据存在 | exp 84 真 (非仅代码) |
| F2 | FK 字段存在≠填充 | 现 FK=0 — P2-C 要修 |
| F3 | Service 存在≠生产调用 | AutoLearner M3 调 (非 P0 链) — P2-C 修 trigger |
| F4 | trigger 函数存在≠连接 | 现无 P0 hook — P2-C 建 |
| F5 | Release→exp 代码存在≠真生成 | 现 0 — P2-C 建 |
| F6 | exp count>0≠canonical | 84 全 M3 legacy — 需标记 (不称 canonical) |
| F7 | 历史≠当前 canonical | 是 — legacy 隔离 |
| F8 | 测试过≠E2E | P2-C 需真 E2E |
| F9 | CLI 存在≠写 canonical | CLI 只读 (无写) |
| F10 | API 存在≠用 canonical writer | API 读 store (OK) |
| F11 | WebUI 显示≠canonical 投影 | WebUI 展示 (OK) |
| F12 | learning 读 exp≠真消费 | P2-D 范围 |
| F13 | M3 AutoLearner≠Prod Loop | 是 legacy |
| F14 | event 存在≠domain | 无 exp event truth |
| F15 | 字符串 task_id≠FK | 现 84 条全是 — P2-C 新 exp 用真 FK |
| F16 | 1 exp/execution≠正确语义 | P2-C 语义已定 (终态 1 条) |

**F2/F4/F5/F15 = P2-C 需消除; F6/F7/F13 = legacy 标记不修。**
