"""apps/cli/registry.py — CLI 命令 → 域 的注册表（★ 单一事实源）。

为什么要有它（2026-09-15）:
    两个 CLI 的命令**都处于"分类只有形没有实"的状态**:
      · `factory` 入口（`_pending_migration/factory_console/cli_factory.py`, 10,155 行）
        —— 91 个命令**全部平铺在一个文件里**; `factory help` 里那 4 个"域"只是
        8600-8603 行的一个 dict, **只为打印**, 代码层零分类。
      · 新 CLI（`apps/cli/`）—— 91 个 handler 有命名前缀（26 组）,
        但**物理上也是一个文件**, 且前缀 ≠ 架构的域。
    ⇒ 本表给"命令属于哪个域"一个**唯一权威**, 后续拆文件 / 合并两套 CLI 都以它为依据。

域清单来源: `docs/ssot/architecture.md` §二「API 分组」（15 域, 2026-09-15 补 learning 后）。
**本表不再自己维护一份域名清单** —— 与 SSoT 漂移就是 R20 报红的那类错误。

判域依据: 命令的**功能语义**（主依据 = 官方 help 描述 + 它实际调的服务/模块）。
"同名不同义"的命令在 `COLLISIONS` 里单列 —— 合并两套 CLI 时必须逐一裁决, 不能按名字合。

状态: **草案, 待 Founder 核准**。核准后:
    ① 守卫加一条: 每个命令必须登记在本表（未登记 = 报红, 让"其他"垃圾桶生不出来）
    ② 按域拆文件（`apps/cli/domains/<域>.py`, 一次一域, 用 `--help` 对比验证命令面不变）
    ③ 老 CLI 的命令逐域并入, 之后老 CLI 主体退役
"""
from __future__ import annotations

#: 现有 `factory` 入口（cli_factory.py, 91 命令）→ 域。
#: 键 = SSoT 的 API 域名; 值 = 该域下的命令（全局唯一, 每个命令出现且仅出现一次）。
FACTORY_CLI: dict[str, tuple[str, ...]] = {
    # 会话面：老 CLI 无会话命令（会话是 Web/API 面）—— 空着, 不硬塞。
    "conversation": (),
    # 需求分析: Product Truth（REQ/PRD）与它的反查都属于"需求"这一面。
    "understanding": ("product", "ptrace"),
    # 架构选择（Founder 定为软件开发一等环节）。
    "architecture": ("arch",),
    # 任务拆解: task 数据本身 + 它的两个视图（todo 清单 / kanban 看板）。
    "decomposition": ("task", "tasktree", "todo", "kanban"),
    # 编排: 工作流 + 项目 + 组合 + 全链 trace。
    "orchestration": ("workflow", "project", "projectos", "composition", "trace"),
    # 执行: 真正"跑东西"的那一批 + 执行环境登记 + 外部执行器。
    "execution": ("run", "run-status", "exec", "runtime", "production", "repo",
                  "workload", "external-ai", "local-ai"),
    # 验收: 评测 / 证据 / 验证事实。
    "validation": ("eval", "evd", "evidence", "verification"),
    # 交付: 发布 + 产出物 + RELEASE 事实。
    "delivery": ("release", "artifact", "artifacts", "release-truth"),
    # 学习（主链第 8 环「经验回流」）: 经验 / 优化 / 选择 / 策略 / 实验 / 智能。
    "learning": ("learn", "learning", "promotion", "experience", "optimization",
                 "optimize", "select", "strategy", "intelligence", "experiment"),
    # 运维: 健康 / 自愈 / 恢复 / 可靠性 / 备份 / 调度 / 回滚。
    "operations": ("ops", "monitor", "health", "heal", "recovery", "reliability",
                   "backup", "schedule", "rollback"),
    # 监控: 控制塔 / 进度 / LLM 成本与留痕。
    "metrics": ("ct", "tower", "progress", "llm-cost", "llm-trace", "llm-experiment"),
    # 审计: 审计 / 历史检索 / 记忆 / 实体账。
    "audit": ("audit", "history", "memory", "memory-lifecycle", "entity"),
    # 治理: 审批三件（§6 说"三名归一", 这里先如实登记三个名字）。
    "governance": ("approval", "approval-request", "governance"),
    # 组织: AI 员工 / 技能 / 组织 / 人力 OS / 插件 / 变体 / 工具与 MCP。
    "organization": ("agent", "agent-run", "skill", "org", "workforce", "workforce-os",
                     "plugin", "variant", "mcp", "tools"),
    # 平台: 基座（初始化 / 配置 / 诊断 / 服务 / LLM 面 / 上下文 / RAG / 更新 / 帮助）。
    "platform": ("init", "config", "doctor", "start", "stop", "status", "service",
                 "llm", "provider", "router", "update", "help", "demo", "sync",
                 "git", "create", "rag", "context", "context-rank"),
}

#: 新 CLI（`ai_factory_os/api/cli/`, **真顶层 24 个** —— 子命令不在此列）→ 域。
#: 注: 它的 handler 已有命名前缀（26 组）, 但与架构域不一一对应; 本表是**按域**的权威。
API_CLI: dict[str, tuple[str, ...]] = {
    "conversation": ("console", "conversation"),   # console=只读视图; conversation=会话入口（2026-09-15 补, 链路第 1 环）
    "understanding": ("understand", "product"),
    "architecture": ("arch",),
    "decomposition": ("task", "tasktree", "kanban"),
    "orchestration": ("workflow", "project"),
    "execution": ("execution", "exec", "runtime", "run", "run-status"),
    "validation": ("validate", "change", "evd", "verification"),
    "delivery": (),
    "learning": ("intelligence",),
    "operations": ("checkpoint", "recover", "backup"),
    "metrics": ("dashboard", "metrics"),
    "audit": ("event",),
    "governance": ("approval",),
    "organization": ("agent", "skill", "org"),
    # init/status 是**无赋值写法**的顶层命令（`sub.add_parser("init", ...)`），
    # 第一次提取时被正则漏掉 —— 由 R23 守卫抓回（2026-09-15）。
    "platform": ("init", "status", "demo", "git", "provider", "workspace",
                 "create", "history", "plugin", "update"),
}

#: 两套 CLI **同名**的命令 —— 合并时必须**逐一裁决**, 不能按名字简单合并。
#: 实测（2026-09-15）: 13 个真重名, 且多数**同名不同义**。
COLLISIONS: tuple[str, ...] = (
    "agent", "demo", "exec", "git", "intelligence", "org", "product",
    "project", "provider", "runtime", "skill", "task", "workflow",
)

#: 同名但**语义完全不同**的（裁决优先级最高 —— 按名字合并必然出错）。
#: 左 = 现有 factory 入口的语义; 右 = 新 CLI 的语义。
COLLISION_SEMANTICS: dict[str, tuple[str, str]] = {
    "exec":   ("执行记录（S10-083 真实执行历史/时间线）", "执行闭环（run/status/approval, 独立数据空间）"),
    "git":    ("Git 操作: push 推送到 origin", "Git 只读查询: status/diff/commits"),
    "demo":   ("隔离 Demo Workspace（~/.factory-demo, 零污染）", "产品化演示（一键跑通完整生命周期）"),
    "product": ("Product Truth（P1 canonical: REQ/PRD/PLAN）", "Product Intelligence（Idea/Artifact/Approval/Workflow）"),
    "intelligence": ("Intelligence（S23: analyze/root-cause/recommendations）", "决策智能（分析/评分/推荐/风险/Approval）"),
}


def domain_of(cmd: str, *, source: str = "factory") -> str:
    """命令 → 域（查表; 找不到 → 空串）。source ∈ {factory, api}。"""
    table = FACTORY_CLI if source == "factory" else API_CLI
    for dom, cmds in table.items():
        if cmd in cmds:
            return dom
    return ""


def all_commands() -> dict[str, tuple[str, ...]]:
    """全部已登记命令（供守卫核对"命令面 ⊆ 本表"）。"""
    return {"factory": tuple(c for v in FACTORY_CLI.values() for c in v),
            "api": tuple(c for v in API_CLI.values() for c in v)}
