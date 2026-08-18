# S10-081 — Product Identity & Naming Intelligence

> 日期: 2026-08-18 | 消除"未命名产品-{ts}" | P0 命名 + P1 CLI rename + P2 NL rename

---

## P0: Discovery 命名阶段 ✅

```
用户想法 → problem → user → core_features
→ 命名: LLM 可用 → AI 建议; 否则 deterministic 提取 (naming.py)
→ 显示"建议名称: X (可直接输入新名称修改)"
→ 用户 y 确认 / 输入新名改名 / 取消词取消
→ create_product(最终 name)
```

- 新增 session/naming.py: suggest_name(LLM/deterministic)+ is_temp_name
- conversation.py: _enter_product_confirmation 命名 + handle_product_confirm 改名(取消词保留)
- 实证: "我想做一个命令行记账 App" → "命令行记账"(非临时名)

## P1: CLI rename ✅

```
factory project rename <id> <name>
```

- 复用 service.confirm_project 事务(校验/快照/目录原子迁移/索引更新/回滚)
- 实证: factory project rename P-58c43d11 台球计分 → ✅, /project 显示"台球计分"

## P2: 自然语言改名 ✅

```
"这个项目改名叫 记账助手" / "把项目名称改成 台球计分" → rename_project
→ 确认门 → confirm_project 事务
```

- intent.py: INTENT_RENAME_PROJECT + 规则(rename 优先于 current_project)
- session.py: _rename_project_via_nl(复用事务 + 确认门)

## 附带修复 (使 rename 真实可用)

1. org Project 模型 None 字符串兼容(null → 默认值, 历史 projects.json 兼容)
2. confirm_project 状态放宽: idea/discovery/product_defined 均可确认改名(刚创建的"未命名产品"正处 idea 期)

## 测试

```
新增 11 (test_s10_081_naming.py): 命名候选/LLM/改名/取消/意图/引导
更新 4 旧测试 (S10-081 行为变化: idea 允许确认、非 y=改名、非临时名断言)
console+api: 4520 passed, 0 failed
全量: 11777 passed + 1 skipped, 0 failed (零回归)
```

## 真实 CLI E2E

```
> 我想做一个命令行记账 App → Discovery → 建议名称: 命令行记账 → y
→ Product Created: 命令行记账
→ /project 显示: P-94ec0742 命令行记账 ✅ (真实名称)
> factory project rename P-58c43d11 台球计分 → ✅ 台球计分
```

## Git

```
17f1663 feat(S10-081): product identity & naming intelligence (12 files)
git clean ✅ | HEAD == origin/main ✅ | 已 push ✅
```
