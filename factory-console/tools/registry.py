"""factory-console/tools/registry.py — 统一工具注册表 (U-1, v1.1.168)。

Founder 2026-08-26: 工具要和 CLI/WebUI 连接、正确调用; 现在 39 工具分散 5 套系统。
本模块 = 唯一工具清单 (事实源): 设计/开发/测试/部署/运维 五阶段 × 39 内置工具。

每个工具元数据:
  id, name, stage(阶段), status(implemented|planned), desc, 
  keywords(触发词), cli/api/intent(入口), fn(执行函数; planned → None)

入口:
- CLI: factory tools [list|show <id>] (增强现有 tools 命令)
- API: /api/tools (返回注册表清单)
- 会话: 可查工具清单 (后续 U-5 三端统一)
选择规则见 docs/tools-selection-rules.md (U-1 验收基准)。
"""

from __future__ import annotations

from typing import Any

STAGES = ["设计", "开发", "测试", "部署", "运维"]

#: 39 内置工具注册表 (唯一事实源)
TOOL_DEFS: list[dict[str, Any]] = [
    # ============================ 设计 (7) ============================
    {"id": "req_discovery", "name": "需求分析", "stage": "设计", "status": "implemented",
     "desc": "想法→需求梳理 (discovery/对话)", "keywords": ["需求", "想法", "梳理"],
     "cli": "factory create/project", "api": "/api/projects", "intent": "create_project", "fn": "pipeline.discovery"},
    {"id": "prd_generate", "name": "PRD 生成", "stage": "设计", "status": "implemented",
     "desc": "产品需求文档生成", "keywords": ["prd", "需求文档", "产品需求"],
     "cli": "pipeline", "api": "/api/projects/{id}/artifacts", "intent": None, "fn": "actions.generate_prd"},
    {"id": "arch_design", "name": "架构设计", "stage": "设计", "status": "implemented",
     "desc": "技术方案+架构审批门", "keywords": ["架构", "方案", "设计"],
     "cli": "pipeline", "api": "/api/board", "intent": None, "fn": "actions.engineering_plan"},
    {"id": "task_decompose", "name": "任务拆解", "stage": "设计", "status": "implemented",
     "desc": "需求→Backlog 任务树", "keywords": ["拆解", "拆任务", "细化"],
     "cli": "factory task", "api": "/api/projects/{id}/backlog", "intent": "create_task", "fn": "FeatureTaskGenerator"},
    {"id": "impact_analysis", "name": "影响分析", "stage": "设计", "status": "implemented",
     "desc": "需求变更影响分析", "keywords": ["影响", "变更", "改动影响"],
     "cli": "ChangeControl", "api": "/api/projects/{id}/change", "intent": None, "fn": "change_control"},
    {"id": "tech_select", "name": "技术选型", "stage": "设计", "status": "planned",
     "desc": "技术/模型选型对比 (V-5)", "keywords": ["选型", "对比", "技术选择"],
     "cli": None, "api": None, "intent": None, "fn": None},
    {"id": "ui_prototype", "name": "原型设计", "stage": "设计", "status": "planned",
     "desc": "UI 原型生成 (V-6)", "keywords": ["原型", "界面设计", "ui"],
     "cli": None, "api": None, "intent": None, "fn": None},
    # ============================ 开发 (11) ============================
    {"id": "code_exec", "name": "代码生成/执行", "stage": "开发", "status": "implemented",
     "desc": "任务→代码真实产出", "keywords": ["开发", "实现", "做"], 
     "cli": "factory run/exec", "api": "/api/projects/{id}/start", "intent": "create_task", "fn": "exec run"},
    {"id": "code_search", "name": "代码检索", "stage": "开发", "status": "implemented",
     "desc": "仓库内 grep 检索", "keywords": ["代码", "在哪", "搜索代码"],
     "cli": None, "api": None, "intent": None, "fn": "tools.adapters.code_search"},
    {"id": "quality_score", "name": "质量评分", "stage": "开发", "status": "implemented",
     "desc": "执行质量分+多候选优选", "keywords": ["质量分", "评分", "优选"],
     "cli": "factory eval", "api": "/api/board/quality", "intent": "project_quality", "fn": "tools.adapters.quality_score"},
    {"id": "retry_switch", "name": "失败重试/换资源", "stage": "开发", "status": "implemented",
     "desc": "低分重试有界+换资源", "keywords": ["重试", "换资源"],
     "cli": "exec", "api": None, "intent": None, "fn": "B-5 路由"},
    {"id": "experience_reuse", "name": "经验复用/学习", "stage": "开发", "status": "implemented",
     "desc": "经验入库+引用 (M4)", "keywords": ["经验", "学习", "复用"],
     "cli": "factory todo", "api": "/api/learning", "intent": None, "fn": "learning_loop"},
    {"id": "git_ops", "name": "Git 操作", "stage": "开发", "status": "implemented",
     "desc": "status/push/仓库信息", "keywords": ["推送", "push", "仓库", "git"],
     "cli": "factory git", "api": None, "intent": "git_push", "fn": "cli_factory.git"},
    {"id": "code_review", "name": "代码审查", "stage": "开发", "status": "planned",
     "desc": "PR/改动自动审查 (V-1)", "keywords": ["审查", "review", "代码评审"],
     "cli": None, "api": None, "intent": None, "fn": None},
    {"id": "code_refactor", "name": "代码重构", "stage": "开发", "status": "planned",
     "desc": "安全自动重构 (V-7)", "keywords": ["重构", "refactor"],
     "cli": None, "api": None, "intent": None, "fn": None},
    {"id": "dep_secure", "name": "依赖安全", "stage": "开发", "status": "planned",
     "desc": "licenses/CVE 扫描 (F-2/V)", "keywords": ["依赖安全", "cve", "license"],
     "cli": None, "api": None, "intent": None, "fn": None},
    {"id": "template_gen", "name": "模板生成", "stage": "开发", "status": "planned",
     "desc": "产品模板一键生成 (F-6)", "keywords": ["模板", "脚手架"],
     "cli": None, "api": None, "intent": None, "fn": None},
    {"id": "inject_guard", "name": "注入防护", "stage": "开发", "status": "planned",
     "desc": "Prompt 注入防护 (F-1)", "keywords": ["注入", "安全防护"],
     "cli": None, "api": None, "intent": None, "fn": None},
    # ============================ 测试 (7) ============================
    {"id": "test_run", "name": "测试运行", "stage": "测试", "status": "implemented",
     "desc": "pytest 集成运行", "keywords": ["测试", "跑测试", "test"],
     "cli": "exec --test-cmd", "api": None, "intent": None, "fn": "pytest"},
    {"id": "coverage", "name": "覆盖率统计", "stage": "测试", "status": "implemented",
     "desc": "模块覆盖率报告 (F-10)", "keywords": ["覆盖率", "coverage"],
     "cli": "factory eval", "api": "/api/board/quality", "intent": None, "fn": "tools.adapters.quality_score"},
    {"id": "quality_gate", "name": "质量门/评测", "stage": "测试", "status": "implemented",
     "desc": "7 维评测 + 发布门", "keywords": ["评测", "质量门", "gate"],
     "cli": "factory eval --gate", "api": None, "intent": None, "fn": "tools.adapters.scan"},
    {"id": "contract_test", "name": "契约测试", "stage": "测试", "status": "implemented",
     "desc": "schema/接口/错误码契约", "keywords": ["契约", "一致性"],
     "cli": "pytest", "api": None, "intent": None, "fn": "test_s10_125"},
    {"id": "longrun", "name": "长跑/并发测试", "stage": "测试", "status": "implemented",
     "desc": "smoke_longrun/24h", "keywords": ["长跑", "并发"],
     "cli": "factory eval", "api": None, "intent": None, "fn": "smoke_longrun"},
    {"id": "test_gen", "name": "测试自动生成", "stage": "测试", "status": "planned",
     "desc": "从需求/代码生成测试 (V-2)", "keywords": ["生成测试", "自动测试"],
     "cli": None, "api": None, "intent": None, "fn": None},
    {"id": "sec_eval", "name": "安全评测", "stage": "测试", "status": "planned",
     "desc": "8 威胁×防御实测 (V-9)", "keywords": ["安全评测", "渗透"],
     "cli": None, "api": None, "intent": None, "fn": None},
    # ============================ 部署 (5) ============================
    {"id": "version_mgmt", "name": "版本管理", "stage": "部署", "status": "implemented",
     "desc": "pyproject/CHANGELOG bump", "keywords": ["版本", "bump"],
     "cli": "dev 流程", "api": None, "intent": None, "fn": "version 流程"},
    {"id": "release_gate", "name": "发布门", "stage": "部署", "status": "implemented",
     "desc": "eval --gate patch/minor", "keywords": ["发布", "gate"],
     "cli": "factory eval --gate", "api": None, "intent": None, "fn": "eval gate"},
    {"id": "build_pkg", "name": "构建打包", "stage": "部署", "status": "planned",
     "desc": "源码→安装包 (V-3)", "keywords": ["构建", "打包", "build"],
     "cli": None, "api": None, "intent": None, "fn": None},
    {"id": "deploy_auto", "name": "部署自动化", "stage": "部署", "status": "planned",
     "desc": "安装/发布/环境 (V-4)", "keywords": ["部署", "发布上线"],
     "cli": None, "api": None, "intent": None, "fn": None},
    {"id": "rollback", "name": "回滚", "stage": "部署", "status": "planned",
     "desc": "版本回滚/快照恢复 (V-8)", "keywords": ["回滚", "回退"],
     "cli": None, "api": None, "intent": None, "fn": None},
    # ============================ 运维 (9) ============================
    {"id": "monitor", "name": "监控采集", "stage": "运维", "status": "implemented",
     "desc": "端口/版本/服务状态", "keywords": ["监控", "状态", "健康"],
     "cli": "factory status", "api": "/api/monitor", "intent": "monitor", "fn": "tools.adapters.monitor"},
    {"id": "alert", "name": "告警", "stage": "运维", "status": "implemented",
     "desc": "端口/失败/质量告警", "keywords": ["告警", "警报"],
     "cli": "factory doctor", "api": "/api/monitor", "intent": "monitor", "fn": "monitor.check_alerts"},
    {"id": "health_check", "name": "健康检查/诊断", "stage": "运维", "status": "implemented",
     "desc": "factory doctor 诊断", "keywords": ["诊断", "体检", "doctor"],
     "cli": "factory doctor", "api": None, "intent": None, "fn": "cli_doctor"},
    {"id": "audit_trace", "name": "审计/链路", "stage": "运维", "status": "implemented",
     "desc": "audit + trace_id 贯穿", "keywords": ["审计", "链路", "追溯"],
     "cli": "factory audit", "api": "/api/board/audit", "intent": None, "fn": "audit_trace"},
    {"id": "backup", "name": "备份/恢复", "stage": "运维", "status": "implemented",
     "desc": "~/.factory 备份导出 (X-1)", "keywords": ["备份", "导出", "恢复"],
     "cli": "factory backup", "api": None, "intent": None, "fn": "tools.adapters.backup"},
    {"id": "crash_recover", "name": "崩溃恢复", "stage": "运维", "status": "planned",
     "desc": "中断 checkpoint 恢复 (X/D-2)", "keywords": ["崩溃", "恢复", "中断"],
     "cli": None, "api": None, "intent": None, "fn": None},
    {"id": "upgrade_migrate", "name": "升级/迁移", "stage": "运维", "status": "planned",
     "desc": "数据结构版本化迁移 (X-5/D-3)", "keywords": ["升级", "迁移"],
     "cli": None, "api": None, "intent": None, "fn": None},
    {"id": "security_compliance", "name": "安全/合规", "stage": "运维", "status": "planned",
     "desc": "数据出境/权限/沙箱 (X/D-4)", "keywords": ["合规", "安全", "沙箱"],
     "cli": None, "api": None, "intent": None, "fn": None},
    {"id": "data_govern", "name": "数据治理", "stage": "运维", "status": "planned",
     "desc": "脏数据/归档/生命周期", "keywords": ["治理", "脏数据", "归档"],
     "cli": None, "api": None, "intent": None, "fn": None},
]

#: id → def 索引
TOOL_REGISTRY: dict[str, dict[str, Any]] = {t["id"]: t for t in TOOL_DEFS}


def list_tools(stage: str = "") -> list[dict[str, Any]]:
    """注册表清单 (按阶段; 失败安全)。"""
    if stage and stage in STAGES:
        return [t for t in TOOL_DEFS if t["stage"] == stage]
    return list(TOOL_DEFS)


def get_tool(tool_id: str) -> dict[str, Any] | None:
    """按 id 取工具 (不存在 → None)。"""
    return TOOL_REGISTRY.get(tool_id)


def summary() -> dict[str, Any]:
    """注册表统计 (总数/按阶段/按状态)。"""
    by_stage = {s: sum(1 for t in TOOL_DEFS if t["stage"] == s) for s in STAGES}
    by_status = {
        "implemented": sum(1 for t in TOOL_DEFS if t["status"] == "implemented"),
        "planned": sum(1 for t in TOOL_DEFS if t["status"] == "planned"),
    }
    return {"total": len(TOOL_DEFS), "by_stage": by_stage, "by_status": by_status}
