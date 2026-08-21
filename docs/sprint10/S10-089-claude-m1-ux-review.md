I've read the review package, the four core implementations (`repo_mode.py`, `backlog_sweeper.py`, `evidence.py`, `exec/approval.py`), the CLI wiring, and the passing test suites. Here is the user-value review, grounded in what's actually in the code — not the plan.

---

## 事实核对（已有 / 未做 / 规划中）

| 能力 | 状态 | 证据 |
|---|---|---|
| `factory repo --patch`：理解→计划→改副本→pytest | **已有**，但 `--patch` 是手动文件；LLM 只做 30 字计划、**不生成 patch** | `repo_mode.py:74-105, 125-141` |
| 积压清道夫：分诊→dependency 确定性修复→bug/feature 走 LLM | **已有**，dependency 修复是真的（解析 requirements/pyproject 生成 unified diff） | `backlog_sweeper.py:264-437` |
| 无 LLM 时 dependency 照修、bug/feature 诚实 skipped | **已有**（真实不伪造） | `backlog_sweeper.py:645-672`；`test_workload_backlog.py:157-175` 断言 `fixed==1, skipped==2` |
| 证据包 diff+测试+决策+变更文件落盘 + 审计事件 | **已有** | `evidence.py:86-158`；`test_session_evidence.py` |
| 分级审批（low/medium/high）+ pending→approved/rejected 状态机 | **已有** | `exec/approval.py:44-152` |
| 审批后 `apply`（git apply 到本地仓库） | **已有**（库函数 + `factory-exec exec approval apply`），**但未接入 `factory` 主 CLI** | `exec/approval.py:166-206`；`exec/cli.py:370-398` vs `cli_factory.py:2800-2813`（`factory approval` 只有 list/decide） |
| 审批→ GitHub/Jira 真实集成、PR 创建（E4） | **未做** | issue 源是本地 `issues.json`（`backlog_sweeper.py:597-609`） |
| Web 证据展示 | **未做**（CLI only） | `cli_factory.py:1257-1322` |
| 组织记忆回流（M1c） | **规划中**，M1 没有 | 审查包 §4 自述；prompt 问题 3 把"记忆"列为差异化但此刻是空 |

---

## UX 问题列表

| 严重度 | 环节 | 问题 | 用户影响 | 修复建议(可执行) |
|---|---|---|---|---|
| **Critical** | 第 5 步·审批落地 | `factory approval` 只有 `list/decide`，**没有 `apply`**。`approve` 之后用户在 `factory` 里就走到死路了；真正能 apply 的是另一个 CLI `factory-exec exec approval apply --id APR --project DIR`，用户不知道它的存在 | 核心承诺"从证据到签字到落地"在主入口断裂。演示者 approve 完只能干瞪眼说"patch 已批准"，观众看不到任何落地，说服力归零 | 成本最低的闭环：把已写好的 `ApprovalGate.apply`（`exec/approval.py:166`）暴露成 `factory approval apply <id> --project X`，并在 `decide approve` 成功后打印下一句"`factory approval apply <id> --project <repo>` 可应用"。这是 1 个 subcommand 的活 |
| **Major** | 第 1 步·首体验 | 无 LLM 时，一份典型 3-issue 清单（1 dep + 1 bug + 1 feature）只有 **1 个能修**，另外 2 个 skipped（诚实，但价值感崩塌）。demo 仓库 `demo/repo` 的默认 issues 正是这个结构 | 用户第一次跑，看到的产出是"1/3 修了、2/3 被跳过"，第一印象是"这工具能干活的只有依赖升级" | 两条腿：① 首次体验默认给一个**全 dependency** 的 demo（3/3 都能确定性修完，先让用户看到"真能干完活"）；② 把"配置 LLM 后解锁 bug/feature"做成运行时提示 + 一条 `factory doctor` 里能一键检查 provider 的路径 |
| **Major** | 第 1 步·输入 | `issues.json` 的 dependency 意图靠正则精确匹配（`缺少 X 依赖`/`升级 X 到 V`/`missing X`/`add X`），句式写不对 → `空 patch → skipped` | 用户不知道必须用特定中文句式，写"requests 版本太老"这种自然表达就直接 skipped，且原因文案是技术黑话"issue 标题无法解析依赖意图" | 解析失败时，把该 issue 的类型**在报告里降级提示**："标题无法解析，建议改成 `缺少 X 依赖` 或 `升级 X 到 V`"（给模板而不是报错）；或加 `--issue-type` 手动覆盖 |
| **Major** | 第 4 步·证据可信 | 仓库**没有 pytest 时**，issue 仍标记 `fixed`（`test_ok=None`），证据里只有一句"未发现 pytest 测试" | "企业敢签字"的核心卖点是证据，但无测试场景下"fixed"没有任何验证背书，CTO 看到会质疑"凭什么说你修好了" | `fixed` 与 `verified` 分离：无测试时状态标 `fixed(unverified)`，审批默认走 higher risk（`classify_risk` 已能按 changed_files 判 medium，但未把"无测试"纳入）；或在无测试时**默认不请求审批**而是标记"待测试补写" |
| **Major** | 第 3 步·谁来看证据 | 证据包只有 CLI，付钱的人（CTO/合规）恰恰是"看证据签字"的人，却打不开一个可读的页面 | 差异化能力"证据+审批"对真正的决策人不可见，只能靠工程师转述 | 复用已有 `factory-console/web` + `dashboard`（仓库里已存在 web 后端），做一个只读的 evidence/approval 列表页；甚至先出一个 `factory evidence export --html` 静态页都比纯 CLI 强 |
| **Major** | 差异化叙事 | 审查问题 3 说"证据+审批+记忆"，但**记忆（M1c）此刻不存在**。当前差异化实际只有 2/3 是实的 | 对内对外把"记忆"写进卖点会变成过度承诺；对外演示时被问"你们的组织记忆呢"会穿帮 | 在宣传材料里把 M1 明确定位为"证据+审批"（已交付），"记忆"标"规划中"；或立刻做一个最小记忆回流（把 `decisions` 字段回写，成本低）再谈 |
| **Minor** | `factory repo` 修复循环 | docstring 写"测试失败→把输出回喂计划重试一次"，实际代码只是 `result.error = "测试失败(已重试上限)"`，**没有真的重试** | 不会误导用户（它诚实标了失败），但文档夸大，且"改→测→修"里的"修"形同虚设 | 要么实现一次真实回喂（把 `test_output` 塞回 `_plan` 再跑一次），要么把 docstring 改成"测试失败→如实报错" |
| **Minor** | 交叉引用 | `approval list` 给 `APR-xxx`，`evidence list` 给 `ev-xxx`，两者无跳转；唯一把它们连起来的是 `workload status` 报告 | 用户在 list/decide/show 之间要手工记两个 id，容易断链 | `approval list` 每行附上对应 bundle_id；`evidence show` 附 approval 状态 |
| **Minor** | 能力不一致 | `factory repo --patch` 需要人工喂 patch（LLM 只做计划），但 backlog 里 LLM 能生成 patch —— 同一产品两处行为相反 | 用户会困惑"为什么 backlog 能自己改，repo 模式还要我喂 patch" | 让 `repo` 模式复用 backlog 的 `_generate_patch` 路径（无 `--patch` 时 LLM 生成），保持一致性 |

---

## 优先级排序

- **P0**：`factory approval apply` 接入主 CLI + `decide approve` 后打印下一步命令 —— 用 1 个子命令把"从证据到签字到落地"闭环闭上，这是整个产品价值主张的收口，也是演示最震撼的一击。
- **P0**：无 LLM / 无测试两种场景的诚实降级文案 + 默认 demo 改全 dependency 型 —— 消除首体验"2/3 被跳过"的价值崩塌。
- **P1**：issues.json 解析失败时给可执行模板（而不是技术报错）—— 首次输入门槛降一半。
- **P1**：证据/审批的只读 Web 页（复用已有 web/dashboard）—— 让"看证据签字的人"能真的看到证据，差异化才成立。
- **P2**：E4 GitHub/Jira 集成 —— 真实 issue 源 + PR，是"从 demo 走向生产"的门，但不是"先让用户看到闭环"的门，可排在本批之后。
- **P2**：记忆回流（M1c）最小切片 —— 补上叙事里缺的那 1/3，但优先级低于闭环和证据可见性。

---

## 用户价值结论

- **这个产品现在敢不敢拿给企业用户演示？—— 有条件地敢。** 条件是：**先把 `apply` 接入 `factory` 主 CLI 并让默认 demo 走全 dependency 型（3/3 确定性修完、approve 后当场看到 patch 落地）**。满足这两点，它已经是一个"真的干完了一件看得见的活 + 每次变更都有证据 + 必须人工签字"的可信演示；不满足，它会在 approve 之后死路、并在首体验就被"跳过 2/3"劝退。
- **最该先做的一件事：** 把已经写好的 `ApprovalGate.apply` 暴露成 `factory approval apply`（并在 `decide approve` 后自动提示）。这是成本最低、对演示冲击最大的一步，且不是新功能——是把"已存在但没接上"的最后一公里接上。

---

## 对 M2 的建议

**调整方向：M2 不要以"7 角色员工内核"为主叙事推进，改为「50% 收 M1 闭环 + 50% 员工内核地基」并行。**

理由（用户价值视角）：
1. 用户（CTO）此刻还没看到 M1 的完整闭环，就投入员工内核，等于"内部装修完成了，顾客还打不开大门"。员工内核是内部架构，不直接产生用户可感知价值；而 M1 的 apply 闭环 + 一个真实 issue 源，是用户能立刻感知、立刻决定"要不要继续买单"的东西。
2. 但员工内核不必暂停——`AgentEntity` 数据模型 + `HandoffBus` 接口可以按地基切片推进（它正是后续"多 agent 协作修 backlog"的前提，能让 bug/feature 修复从"单发 LLM patch"升级成"多角色协作"）。只是**对外叙事和演示重点必须落在 M1 闭环上**。
3. 一个具体建议：M2 的头号里程碑应该是"**审批通过 → 自动 PR（哪怕只支持 GitHub 只读导入 issue + 打开 PR）**"这一条真实链路。它是"企业敢让 AI 干活"从 CLI 玩具跨到生产工具的分水岭，比 7 角色编排更能证明"别人抄不动"。

一句话：**先让顾客看到门（闭环 + 可看的证据），再装修房间（员工内核）。**
