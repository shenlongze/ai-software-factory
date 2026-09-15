# API 目录结构设计 v1

> 日期: 2026-09-15 | 性质: 设计（规格）| 状态: 实施中（刀1 建骨架）
> 依据: Founder 三条口径 —— ①API 与 CLI 统一动作/统一数据 ②按功能分类，不堆砌 ③接口文档跟上

## 0. 一句话

**API 只干一件事：把「域用例」暴露成 HTTP。域用例只写一次（`services/` 里），
CLI 和 API 都是它的薄适配器。**

## 1. 目标树形

```
src/ai_factory_os/api/
├── app.py                    create_app(): 装配全部 router + 中间件 + 包络（唯一装配点）
├── registry.py               域 → router 注册表（单一事实源，装配只能读它）
├── envelope.py               响应/错误包络（唯一实现，全端点强制）
├── errors.py                 错误码表
├── deps.py                   共享依赖：data_root · trace_context · 鉴权
└── domains/
    ├── conversation/         会话        router.py · schemas.py · README.md
    ├── understanding/        需求分析
    ├── architecture/         架构分析（当前无实现 → 空壳 + 明确 TODO）
    ├── decomposition/        任务拆解
    ├── orchestration/        编排
    ├── execution/            执行
    ├── validation/           验收
    ├── delivery/             交付
    ├── operations/           运维
    ├── metrics/              监控
    ├── audit/                审计
    ├── governance/           治理
    ├── organization/         组织/人力（基座域）
    └── platform/             平台（config · doctor · dashboard · health）
```

每个域包三个文件，形态完全一致 —— 这就是「结构统一」的落点：

| 文件 | 职责 | 纪律 |
|---|---|---|
| `router.py` | 只做 HTTP 适配（解析 → 调用例 → 包络） | 不写业务逻辑 |
| `schemas.py` | 请求/响应模型（pydantic） | 不 import services |
| `README.md` | 该域接口说明 | 由 OpenAPI 生成，不手写 |

## 2. 依赖规则（谁能 import 谁）

允许：

```
api/domains/<域>/router.py  →  services/<域>/      ← 域用例，唯一业务入口
                            →  contracts/<域>/     ← 契约
                            →  api/{envelope,errors,deps}.py
```

禁止（写进 lint，违反即红）：

```
✗ import 任何 _pending_migration/** 的模块
✗ 跨域直调 services/<别的域>/（要跨域走 contracts）
✗ router 里直接读写数据文件（存储只能经 services/ 或 infrastructure/）
```

## 3. 统一动作 = 统一用例（口径①）

一个动作 = `services/<域>/` 里的一个**用例函数**。

| 入口 | 位置 | 行为 |
|---|---|---|
| CLI | `api/cli/<域>.py` | 调用该用例函数 |
| API | `api/domains/<域>/router.py` | 调用同一个用例函数 |

**守卫**：用例函数必须被两侧调用。只被一侧调用 → 检查报红。
数据统一是自然结果：用例只读写自己域的一份 store，两侧拿到同一份。

## 4. 命名与形态（消灭组名漂移）

- 路径前缀 = `/api/<域>`；OpenAPI tag = `<域>`；**组名必须等于域目录名**
  （不再出现 approvals / approval-requests / approval-gates 三个名字在同一域）
- 包络/错误码沿用 `docs/API规范.md`：集合 `{items,count}` · 错误带 `code` ·
  创建 201 · 删除 `{deleted,id}`
- router 一律 `APIRouter(prefix="/api/<域>", tags=["<域>"])`；`app.py` 只 `include_router`

## 5. 文档（口径③）

| 层 | 位置 | 生成方式 |
|---|---|---|
| 单一事实源 | `docs/api/openapi.json` | 构建时由 router 自动产出 |
| 人读版 | `docs/api/README.md` | 由脚本从 openapi 生成（禁手写） |
| 规范 | `docs/API规范.md` | 保留为**可执行 lint 规则**（包络/命名/状态码） |

守卫三条（全部进验证据组）：

1. **文档 vs 端点一致性** —— openapi 的路径/方法数 == 实际端点
2. **端点归属** —— 每个端点必须挂在某个域的 router 上（禁止 app 直挂）
3. **动作对照齐全** —— 每个用例函数都有 CLI + API 两侧接线

## 6. 迁移映射（391 端点 → 新结构）

| 域 | 现有组 | 处置 |
|---|---|---|
| conversation | conversations(17) + sessions(14) | ★先收敛：择一 |
| understanding | 并入 conversations | 并入 |
| decomposition | task-trees(3) · tasks(3) · schedules(5) | 归位 |
| orchestration | workflows(3) · projects(57) · projects-os(5) · board(12) | ★先收敛 |
| execution | production-runs(15) · runtimes(4) · runtime-sessions(6) · agents(8) | 归位 |
| validation | acceptances(3) · approval-gates(1) | 补全 API 面 |
| delivery | artifacts(3) · releases(11) · releases-truth(1) · rollbacks(6) | 归位 |
| operations | ops(4) · incidents(7) · health-incidents(3) · recovery(4) | 归位 |
| metrics | control-tower(4) · monitor(1) · decisions(1) | 归位 |
| audit | audit(2) | 补 CLI 实实现 |
| governance | approvals(5) · approval-requests(4) · approval-gates(1) | 三名归一 |
| organization | workforces(7) · workforce(4) · workforce-os(1) · organizations(2) · agents(8) · skills(4) · agent-profiles(4) · agent-runs(4) · capabilities(2) · mcp(4) · plugins(8) | 11 组进 1 域 |
| platform | config(4) · dashboard(1) · system(2) | 归位 |
| （待定） | entities · contracts · events · exec · experiences · experiment-samples · handoffs · intelligence · memory · context · memory-conflicts · operations · promotions · rag · recommendations · review-feedback · runs · runtime · selection · learning · optimization(23) · optimizations(5) · experiments(11) · external-ai(13) · local-ai(3) · providers(1) | 逐个定域 |

## 7. 要收敛的两处（口径① 的硬缺口）

| 动作 | 留 | 退/降级 |
|---|---|---|
| 会话 | canonical（`/api/conversations` → conversation_app → `conversations/*.json`） | `/api/sessions` 14 端点 → 改为 canonical 只读投影，或随 `console_sessions` 一起退 |
| 编排 | 主链 `golden_path`（裸 factory + `/api/conversations/{id}/plan`） | `professional_workflow` 与 `/api/workflows` 降级或退 |

这两处不收敛，router 拆出来只是把两套栈分别整理整齐，以后还是麻烦。

## 8. 落地顺序（分刀）

| 刀 | 内容 | 验证 |
|---|---|---|
| **刀1** | 建骨架：`app.py` · `registry.py` · `envelope.py` · `deps.py` · `errors.py` + `domains/` 14 个空壳 | 导入全绿 + 空 app 可构建 |
| **刀2** | 迁 7 个已同源的域 —— 实测 CLI 侧已接线者：`conversation` · `execution` · `learning` · `metrics` · `organization` · `validation` · `work`（另 2 个例外：`governance` 两侧未接 · `resource` 仅声明） | 端点数不变 + 文档一致 |
| 刀3 | 收敛 2 处多套（conversation · orchestration） | 每个动作只剩一行 |
| 刀4 | 补 2 处不对齐（audit CLI · validation API） | 两侧都有接线 |
| 刀5 | 挂守卫三条 + 生成 openapi.json / README.md | 三条守卫全绿 |

每刀 = 1 commit + 全量验证 + STOP。
