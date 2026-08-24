# AI Factory Board 功能指南

> 版本: v1.1.75 · 2026-08-24 · Board = 项目中心监控面板（单项目视图 + 全生命周期）
> 定位: 以项目为中心 — 先选项目，再看它的各种面板；AI Factory 自身进度降级为次要入口。

---

## 1. 是什么

Board 是 AI Factory 的**项目监控与管理面板**：把每个产品项目（记账App、markdown 编辑器…）
当作一个独立单元，展示它的**全生命周期**（发现→确认→PRD→工程→开发→测试→验收→交付→部署→运维→更新）、
任务树、依赖图、任务链、生命线、汇报、文档 —— **一个项目一个视图，绝不跨项目混淆**。

核心设计：
- **项目隔离**：同一时刻只显示一个项目，不猜项目、不扫描兜底
- **数据实事求是**：所有数据来自真实文件/事件，标注来源，无臆造
- **可配置**：文档目录、扩展名、刷新间隔、默认项目都可设置

---

## 2. 入口

### 会话（CLI）
```
/board                   主线面板（AI Factory 开发进度, 降级入口）
/board project [slug]    项目列表 / 单项目全生命周期视图
/board project           无参 → 项目列表（select 切换）
/board task split <slug> <任务ID> <子任务,...>   细化任务（L 层+1）
/board default [slug]    查看/设置默认项目
/board docs list|add-dir|add-ext|rm-dir <项目>  文档配置
/board graph|chain [项目]  依赖图 / 任务链
/board timeline [项目]    生命线（项目过滤）
/board report [项目]      项目汇报 / 主线汇报
```

### Web
```
http://127.0.0.1:8011/api/board                       首页 = 当前/默认项目视图
/api/board?view=projects                              项目列表
/api/board?view=project&project=<slug>                单项目全生命周期
/api/board/tasks?project=<slug>                       任务树（L1-L4+）
/api/board/graph|chain?project=<slug>                 依赖图 / 任务链
/api/board/timeline?project=<slug>                    生命线
/api/board?view=report&project=<slug>                 项目汇报
/api/board/docs?project=<slug>                        文档管理（文件树）
/api/board/docs/config?project=<slug>                 文档配置（设置）
/api/board/summary                                    项目监控聚合 JSON
```

---

## 3. 八大视图

| 视图 | 内容 | 数据来源 |
|---|---|---|
| 📊 项目（生命周期） | 11 段进度条 + 当前卡点 + 文档产物 + 任务进度 | product.json / 文件存在性 / tasks.json |
| 🗂 任务树 | L1 epic → L2 feature → L3 task → L4+ 子任务；依赖标记 + 关键路径★ + 时间线；可细化 | tasks.json / execution_state.json / plan.json |
| 🔗 依赖图 | plan.json 任务节点 + 依赖边 + ★关键路径 | plan.json |
| ⛓ 任务链 | 关键路径链（★关键节点 ▲汇聚点）+ 状态色 + 工期 | plan.json |
| ⏱ 生命线 | 项目审计事件时间线（中文标签 + 高频折叠 ×N + 同秒聚合） | audit_events.json |
| 📄 汇报 | 项目生命周期/任务/文档/最近事件 markdown 汇报 | 上述数据派生 |
| 📚 文档 | 项目实际目录/git 仓库的文档文件树（可配置多目录+扩展名） | workspace_dir / docs_config.json |
| 📋 AI主线面板 | AI Factory 自身开发进度（M1-M7/P0/Sprint/章节/SDK） | 待办清单 / 验收报告 / 方案书 |

---

## 4. 项目选择与默认项目

- **全页项目选择器**：7 个 tab 顶部 select，切换后所有视图跟随该项目
- **默认项目**：`/board default <slug>` 或 Web 卡片"⭐设为默认"，首页优先打开
- **优先级**：默认项目 > 会话当前项目 > 项目列表
- 项目隔离：只读 `projects/<slug>/` 该项目文件，无显式项目 → 空态提示

---

## 5. 数据实事求是

| 视图 | 来源标注 | 原则 |
|---|---|---|
| 任务树 | "待办清单解析" 或 "执行系统记录" | 区分推断 vs 真实执行 |
| 依赖图/任务链 | "方案书里程碑顺序(非执行)" 或 "M3b 真实拆解" | 无臆造估时/依赖 |
| 文档 | "项目实际目录" + 📂 路径 + 🌐 git | 只显示配置扩展名的真实文件 |
| 生命线 | audit 事件 | append-only 审计 |

**规则**：任何手动登记的数据带 meta（source/generated_by/note）；执行系统产生的数据标注"执行记录"。

---

## 6. 文档管理（可配置）

```
配置存储: projects/<slug>/docs_config.json
{
  "dirs": ["/项目/实际/目录1", "/项目/实际/目录2"],   # 多目录, 每目录一棵树
  "exts": [".md", ".json", ".doc", ".docx"]          # 默认扩展名, PPT/Excel 需配置
}
```

- **默认扩展名**：md / json / doc / docx
- **文件树**：目录默认折叠、目录在上文件在下 A-Z、紧凑行、搜索即时过滤、类型筛选
- **隐藏过滤**：`.` 开头文件/目录不展示；排除 demo/examples 等示例目录与源码
- **设置入口**：文档页"⚙ 配置"（Web 表单）+ CLI `/board docs list|add-dir|add-ext|rm-dir`

---

## 7. 实时性

| 页面 | 刷新 |
|---|---|
| 单项目视图 / 任务树 | 15s 默认（可配 5s/30s/60s/关闭, ?refresh=N） |
| 主线面板 | 30s + 监控数字 5s 增量 |
| 文档/配置 | 保存后自动跳转刷新 |

---

## 8. 使用示例

```bash
# 看当前项目生命周期
factory → /board project

# 细化一个任务（拆子任务）
/board task split ai-factory-self M3-5 "PRD 深化, UX 模板引擎, QA 真引擎"

# 设默认项目
/board default P-e023a04c

# 文档管理加一个目录 + 扩展名
/board docs add-dir ai-factory-self /path/to/docs
/board docs add-ext ai-factory-self pptx

# Web 全流程
打开 /api/board → 顶部选项目 → 生命周期/任务树/依赖图/任务链/生命线/汇报/文档
```

---

## 9. 版本演进（v1.1.27 → v1.1.75）

| 版本 | 功能 |
|---|---|
| v1.1.27-42 | 主线面板 / graph / chain / timeline / report / done / sync / HTML / 多源加载 / 空态 |
| v1.1.49 | 单项目管理视图（全生命周期 11 段） |
| v1.1.50 | 监控聚合 + 实时刷新 + SDK 第四数据源 + Sprint 判定放宽 |
| v1.1.51-52 | 任务树 + 状态汇总 + 统一导航 + 项目选择器（准确/实时/同步） |
| v1.1.53 | 刷新间隔可选 |
| v1.1.54 | 项目优先架构（默认首页=项目视图） |
| v1.1.55-56 | 生命线可读化 + demo/无项目引导 |
| v1.1.57 | 选择器与 URL 一致 |
| v1.1.58-59 | 生命线/汇报项目化 + 全页面可选项目 |
| v1.1.60 | 文档管理 + 任务逻辑（依赖/关键/时间线） |
| v1.1.61 | 默认项目 |
| v1.1.62-64 | 任务链格式 + 递归任务树(L1-L4+/细化) + 模块卡片 |
| v1.1.65 | 数据实事求是（来源标注 + 剔除臆造） |
| v1.1.66-70 | 文档扫描 README/docs + 文件夹 + 全类型 + 指向实际目录/git |
| v1.1.71-75 | 文件树 + 搜索 + 隐藏过滤 + 文档配置(多目录/扩展名) + 保存修复 + 树去重排序 |
