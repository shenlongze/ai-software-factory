# 吸收规格：三项缺口（OpenClaw / Hermes → AI Factory OS）

> 日期: 2026-09-14 · 版本: v1.2.1
> 来源依据: 三家 CLI 实测对照（我们 84 命令 vs OpenClaw 55+ vs Hermes 61）
> 原则: 每家只拿【最强的机制】，不是抄命令清单；落点必须是已有的七层

## 缺口总览

| # | 缺口 | 来源 | 为什么值得拿 | 我们的现状 |
|---|------|------|--------------|-----------|
| ① | 渠道接入 | OpenClaw | 产品定义第一条「会话是唯一业务入口」目前只有 CLI/Web | 0 个命令 |
| ② | 凭据池 + 降级链 | Hermes | external-ai 是单点，一个 key 挂了整条链断 | 0 个命令 |
| ③ | 技能生态 | Hermes | 有 skill 单命令，没有组合/维护/时间线 | 1 个命令 |

---

## ① 渠道接入（从 OpenClaw 拿）

**要拿的机制**（不是 55 个命令，是三层）：
```
 1 网关（Gateway）：常驻进程，持有渠道连接 + 会话路由（ws://127.0.0.1:PORT）
 2 渠道适配器：每渠道一个适配器，只做两件事
     · 收：渠道消息 → 归一化成内部消息（channel/target/sender/text/thread）
     · 发：内部回复 → 渠道原生格式
 3 消息归一化：所有渠道统一成一种 Message，内核不感知渠道差异
```

**落点**：
```
 plugins/connectors/<渠道>/     ← 适配器实现（该层已存在，槽位空）
 infrastructure/messaging/      ← 网关与消息总线（该层已存在）
 api/                           ← 对外接口（已填 cli+dashboard）
 services/conversation/         ← 接收归一化消息（该层已存在）
```

**最小可用版本（MVP）**：
```
 1 一个 Gateway（本机 ws 服务）+ 一个渠道适配器（先做 CLI 本地渠道，验证闭环）
 2 Message 归一化契约（contracts/conversation/ 下新增 message 契约）
 3 CLI: factory gateway start/status + factory channels list/add/status
 4 闭环验证：从渠道发一条消息 → 网关归一化 → 会话 → 执行 → 回复回渠道
```

**验收**：从外部渠道发"创建一个项目 X"，收到真实回复，且 ~/.factory 下有对应的会话与执行记录。

---

## ② 凭据池 + 降级链（从 Hermes 拿）

**要拿的机制**：
```
 1 凭据池：同一 provider 多把 key，轮换 + 标记耗尽 + 重置
 2 降级链：主模型失败 → 自动试下一个（链式，不是单点）
 3 状态可见：每条凭据的可用/耗尽状态、每个 provider 的健康
```

**落点**：
```
 infrastructure/llm/            ← 池化与降级（Provider 抽象已在此）
 contracts/llm/?  或 resource   ← 凭据契约
 api/cli/                       ← 对应命令
```

**MVP**：
```
 1 CredentialPool（多 key 轮换 + 耗尽标记 + reset）
 2 FallbackChain（provider/model 列表，失败逐个降级，记录降级事实）
 3 CLI: factory auth add/list/remove/reset + factory fallback list/add/remove
 4 验证：故意让主 key 失效 → 请求自动落到第二把 → 事件里留下降级记录
```

**验收**：主 key 失效时任务仍成功，且审计里能看到 provider.fallback 事件。

---

## ③ 技能生态（从 Hermes 拿）

**要拿的机制**：
```
 1 Bundle：把多个 skill 打包成一个别名（一次加载一组）
 2 Curator：后台维护（跑通统计 / 暂停 / pin 常驻）
 3 Journey：技能 + 记忆的【时间线】（什么时候学到什么）
```

**落点**：
```
 plugins/skills/                ← 技能实现（该层已存在）
 services/learning/             ← 学习域（本轮刚打通写经验+刷画像）
 audit/              → 已搬到 services/governance/audit（时间线数据源）
 api/cli/                       ← 命令
```

**MVP**：
```
 1 Bundle：`factory skill bundle create/list/use`
 2 Journey：读 audit + learning store 产出时间线（只读命令，无新数据）
 3 Curator：统计每个 skill 的使用/成功，标出长期未用的（只读 + 建议）
```

**验收**：`factory skill journey` 能列出"从哪天起学到哪些 skill、各自用过多少次"。

---

## 建议顺序与理由

```
 先 ② 凭据池+降级       —— 最小、纯技术、无产品决策；直接提升现有链路可靠性
 再 ③ 技能生态          —— 复用刚打通的 learning，增强已有能力
 最后 ① 渠道接入        —— 需要产品决策（接哪个渠道？谁的消息能进系统？权限？）
                           且工作量最大（网关 + 适配器 + 归一化）
```

## 与"10 项能力清单"的关系

```
 本规格的 ①（渠道）对应那份清单之外的新项；
 ②（凭据池）不在旧清单里，是这次对比 Hermes 才发现的；
 ③（技能生态）对应旧清单第 10 项（GEPA 技能进化的落地形态之一）。
 旧清单里的 Hooks / Sandbox / Cost / Heartbeat / Goal 等仍待做，本规格不覆盖。
```
