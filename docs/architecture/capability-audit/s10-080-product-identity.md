# S10-080 — Product Identity Reality Audit

> 日期: 2026-08-18 | 产品身份审查 | 未修改代码

---

## 1. 为什么大量出现"未命名产品-{timestamp}"(根因)

```
_PRODUCT_FIELD_ORDER = ("problem", "user", "core_features")   ← 无 name!
Discovery 从不问产品名
→ ProductIntent.name = None
→ create_product: if not product.name: name = generate_temp_product_name()
→ "未命名产品-{timestamp}"
→ create_project(name=临时名) → project.json name=临时名
```

实证: ~/.factory/projects/ 下 6+ 项目全部 name="未命名产品-{ts}", 目录名=纯数字 timestamp。

## 2. product.name 生成链路 (真实)

```
用户想法 → Discovery (problem→user→core_features, 无 name)
→ ProductIntent.name=None
→ create_product → 临时名 "未命名产品-<ts>"
→ create_project (桥接) → project.json name=临时名
→ _slugify(name) → 中文剥除 → 目录 = "<ts>"
```

## 3. Product / Project / Workspace 名称关系 (实证)

| 层 | 名称 | 来源 |
|---|---|---|
| Product.name | 临时名/中文名 | ProductIntent (缺省 → 临时名) |
| Project.name | = Product.name (桥接复制) | project.json |
| 目录 slug | _slugify(name) | 中文 → '-' → 纯数字 |
| org Project.id | 独立 id (P-xxx / ts) | org 层 |
| Workspace | 数据根 (~/.factory) | 配置 |

问题: 同一名称在 Product/Project 复制, slug 从 name 派生但中文丢失 → 目录不可读。

## 4. 是否引入 display_name / internal_name / slug

**现状隐含分层** (无需新字段):
- display name = Product.name / Project.name (可中文)
- internal identity = Project.id (稳定, rename 不变 — service.py 已保证)
- slug = 目录名 (rename 时原子目录迁移)

**结论**: 不需要新增 display_name/internal_name 字段 — 缺的是 "name 有意义" + "改名能力暴露"。

## 5. 名称建议流程 (修复方案)

```
用户输入想法
→ Discovery (problem → user → core_features)     [现有]
→ 确认前: AI 从 idea/problem 提取产品名建议
     "建议名称: 台球计分助手"
     可接受 / 输入新名称
→ 用户确认 (y 或 改名)
→ create_product(name=确认名)                     [现有, 缺 name 时补]
→ create_project → 目录 = slug(确认名)
```

实现位置: conversation.py _enter_product_confirmation 前加 name 建议步骤 (复用 LLM 或规则提取)。

## 6. 历史未命名产品迁移

- service.py 已有 rename 事务 (confirm_project: 校验 → 快照 → project.json → 目录原子迁移 → 索引更新 → 回滚)
- **但 CLI/API 未暴露 rename**
- 迁移方案: 新增 `factory project rename <id> <新名>` + 说明 (已 confirmed 项目 rename 需放宽或走专门命令)

## 7. 重命名支持现状

| 层 | 支持 |
|---|---|
| Service (service.py confirm_project) | ✅ 事务式 (快照/回滚/目录迁移) |
| API | ⚠️ POST /projects/{id}/confirm (仅确认点前) |
| CLI | ❌ 无 |
| Intent | ❌ 无 |

## 修复方案摘要

1. **P0**: Discovery 确认前 AI 建议产品名 (conversation.py) — 用户可确认/改名
2. **P1**: CLI 暴露 rename (`factory project rename`) — 复用 service.py 事务
3. **P2**: Intent 支持改名 ("改名 XX"/"这个项目叫 XX") → rename
4. **P3**: 历史未命名批量迁移工具 (可选)

等待批准后实施。
