# factory_console 拆分方案（只读分析，未动代码）

> 日期: 2026-09-14 · 版本: v1.2.1 · 分析对象: `src/ai_factory_os/_pending_migration/factory_console/`
> 结论先行：**它不能用"搬迁模式"处理，必须按【功能】逐块重写替换。**

## 一、体量与结构

```
 总计 311 py / 128,393 行

 子目录
   session            128 py /  58,831 行   ← 会话/编排（最大）
   web                  3 py /   8,604 行   ← Web 后端（fastapi_adapter 单文件 8,597 行）
   api                 24 py /   4,243 行   ← DTO/服务层
   memory              12 py /   2,519 行
   audit               10 py /   2,234 行
   external_executor   11 py /   2,011 行
   retrieval            7 py /   1,361 行
   tools                3 py /     351 行

 顶层散文件（按行数前 12）
   cli_factory.py      8,578   ← CLI 装配（84 命令注册 + 实现）
   service.py          4,928   ← ConsoleService（业务门面）
   workflow_runner.py  1,331 · models.py 1,011 · product_truth.py 861
   node_runtime.py       785 · professional_workflow.py 711 · flow_views.py 658
   golden_path.py        630 · conversation_app.py 589 · console_sessions.py 582
   learning_truth.py     580 · （另有约 30 个顶层 .py）
```

## 二、为什么不能按子目录搬（实测依据）

```
 块间依赖矩阵：绝对 import 交叉 = 0，相对 import 合计 = 【1,113 处】
     «顶层» ↻458 · session ↻479 · api ↻71 · memory ↻36
     audit ↻22 · external_executor ↻17 · retrieval ↻15 · web ↻7 · tools ↻8

 含义：整个包内部【靠相对 import 互相引用】。
 单独移动任何子目录 → 它的相对 import 立刻失效
 （刀16 实测：只搬 api/ 一个子目录 → 断 71 处）

 对比：前面 54 刀搬的包，包内相对 import 数量少、且与新层无环；
       本包 1,113 处相对 import 且深度嵌套 → 搬迁模式失效。
```

## 三、已具备的有利条件

```
 · 已经依赖新层 117 处（ai_factory_os）→ 它在主动往新层靠
 · 别名桥已就位 → 旧名可解析，搬迁不必改消费方
 · 目标层的对应域已存在：services/conversation（空）、services/orchestration、
   services/learning、api/（已填 cli+dashboard）、infrastructure/retrieval（待建）
 · 外部依赖清单干净：fastapi 17 · pydantic 14 · rich 6 · yaml 5（都是标准三方）
⚠ 3 处可疑旧依赖需先查：artifact_lifecycle(2) · verification_domain(2) · evidence_domain(2)
```

## 四、拆分方案（四块）

| 块 | 来源 | 行数 | 目标层 | 性质 |
|----|------|------|--------|------|
| **A Web 接口** | `web/` (3py/8,604) + `api/` (24py/4,243) | 12,847 | `api/` | 单文件 396 路由 → 拆成多个 router 模块 + DTO 装配 |
| **B 会话与编排** | `session/` (128py/58,831) + conversation_app / console_sessions / cli 相关 | ~59,000 | `services/conversation` + `services/orchestration` | 最大一块；会话状态机 + 动作 + 编排 |
| **C 记忆/检索/审计** | `memory/` `retrieval/` `audit/` | 6,114 | `services/learning` · `infrastructure/retrieval` · `services/governance` | 三块职责清晰、相对独立 |
| **D CLI 装配 + 门面** | `cli_factory.py` (8,578) `service.py` (4,928) + ~30 顶层散文件 | ~20,000 | `api/cli`（已建）· `services/*`（按职责散入） | 命令注册 → 新 CLI 入口；门面 → 各域 service |

## 五、推荐做法：按【功能】绞杀，不按【目录】搬

```
 错误做法（不可行）：一刀一个子目录 → 1,113 处相对 import 全断
 正确做法（可验证）：一刀一个【功能】，走完整四步

   ① 选定一个功能（例：`factory evidence` 证据包）
   ② 在新层把它重写出来（api/ 或 services/ 下，按其域归属）
   ③ 把 CLI 命令指向新实现 + 删旧实现
   ④ 全量导入验证 + 产品冒烟 + 提交

 每刀产出一个"功能已在新层"的可验证结果，且工厂始终可跑。
 全部功能切完后，factory_console 自然空掉 → 删除。
```

## 六、工作量与风险

```
 按功能粒度估计：factory_console 承载约 84 个命令 + 若干内部能力
   ≈ 40~60 刀（每刀 1~3 个功能），远超前 54 刀的单刀体量
 最大风险：
   ① web/fastapi_adapter.py 单文件 8,597 行 / 396 路由 —— 拆分需先做路由清单
   ② session/ 128 文件 / 58,831 行 —— 会话状态机是产品心脏，重写风险最高
   ③ service.py 4,928 行门面 —— 被大量内部引用，动它牵连面广
 缓解：
   · 先做 A（Web 接口）或 C（记忆/检索/审计）—— 相对独立、风险低、能建立信心
   · 把 B（会话）放最后 —— 它依赖面最广
   · 每刀都必须过"全量导入 502/502 + 产品命令冒烟"
```

## 七、建议的第一步

```
 推荐从 C（记忆/检索/审计，29 py / 6,114 行）开始：
   · 三块职责清晰、与 session 的耦合面最小
   · 目标层已存在：services/learning（memory 归此）、
     services/governance（audit 归此）、infrastructure/retrieval（新建）
   · 预计 6~10 刀，可作为"重写替换"模式的试点 —— 验证方法可行后再攻 A 和 B
```
