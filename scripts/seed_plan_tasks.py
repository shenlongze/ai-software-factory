#!/usr/bin/env python3
"""scripts/seed_plan_tasks.py — 把待办清单/债务清单全部未实现项导入 ai-factory-self backlog。

Founder 2026-08-26: "把我们之前的计划, 和没有实现的全部数据都做进去"。
- 用真实 backlog (management store) 建 史诗→模块→故事→任务 四层树
- 幂等: 按名查重, 重复运行不产生重复
- 数据源: docs/sprint10/待办清单-已发现未落地.md 的 ⬜ 项 + 债务清单 2026-08-26

用法: .venv/bin/python scripts/seed_plan_tasks.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
_FACTORY_CORE = ROOT / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))

import importlib  # noqa: E402

_adapter = importlib.import_module("factory-console.web.backend.fastapi_adapter")

PROJECT = "ai-factory-self"

#: 计划树: epic(系列) → feature(模块) → tasks(未实现项)
PLAN: dict[str, dict[str, list[tuple[str, str]]]] = {
    "C 产出物契约": {
        "契约闭环": [
            ("C-4", "契约配置 UI（设置→产出物契约 tab: 查看/编辑标准文件名 + 每项目 manifest + 校验）"),
            ("C-5", "存量迁移: legacy 资产 set_artifact 归位（版本链/追溯全有）"),
            ("C-6", "文档扫描配置 (docs_config dirs/exts) 在 5180 可配"),
            ("G1", "质量文件名统一: PRD.quality.json/engineering.quality.json → quality.json (双文件共享单槽位)"),
            ("G2", "quality.py Validator.save 直写统一走 set_artifact"),
            ("G3", "RepairManager 直写统一走 set_artifact"),
            ("G4", "lifecycle_store 三处同步写统一走契约入口"),
        ],
    },
    "W WebUI 迭代": {
        "页面完善": [
            ("W-2", "PRD/发现/Backlog 占位页做实（读 PRD.md/discovery 对话/tasks, 后端资产已有）"),
            ("W-3", "项目首页 Todo 编辑/归档/审计溯源（敏捷管理完整闭环）"),
            ("W-4", "文档页增强: 搜索/下载/HTML 渲染"),
            ("W-4b", "Markdown 渲染增强: 任务列表/脚注/嵌套列表/复杂语法 (v1.1.147 手写渲染器待补)"),
            ("W-4c", "文档语义检索增强: embedding/向量检索 提升中文召回 (当前词频, 口语化查询会漏)"),
            ("W-5", "设置增强: LLM Provider 删除 / Agent 详情页"),
        ],
        "体验与国际化": [
            ("/help", "CLI 命令分层/tree 优化（Founder: 一坨没逻辑）"),
            ("I18N-2", "i18n 长尾文案迁移（设置表格/项目详情/会话错误提示/后端 CLI/board）"),
        ],
    },
    "K 会话上下文": {
        "上下文管理": [
            ("K-7f", "上下文清单(Context Plan)+token 预算+自动/手动压缩+摘要落盘+切换恢复"),
            ("K-7g", "任务级作用域 + RAG 按需注入(K-6) + 经验/决策记忆接入(K-3)"),
        ],
    },
    "J 生命周期": {
        "全链路": [
            ("J-2", "全链路节点衔接端到端验证（主链 10 步每节点衔接实测）"),
            ("J-3", "交付后迭代状态机（delivered 后 ChangeControl 回退规则）"),
        ],
    },
    "H 深度验证": {
        "验证": [
            ("H-2", "项目可控性: 节点级暂停/恢复/取消/重试完整控制链"),
            ("H-3", "审计深度验证: 审计链校验/血缘追溯/报告生成 系统测试"),
            ("H-4", "治理深度验证: 审批门全场景/预算熔断/治理规则 测试"),
        ],
    },
    "D 运维可靠性": {
        "可靠性": [
            ("D-1", "备份/恢复: ~/.factory 数据目录导出/导入/迁移"),
            ("D-2", "崩溃恢复验证: 执行中断恢复, checkpoint 落地"),
            ("D-3", "升级/迁移: 数据结构版本化 + 迁移脚本"),
            ("D-4", "安全/数据合规: LLM 数据出境/审计权限/沙箱逃逸"),
            ("D-7", "外部依赖容错: provider 宕机/API 变更适配"),
            ("D-8", "CI 自动化: 测试自动跑 + 发布门"),
            ("E-4", "自我监控实时化/告警完善 (Monitor 已有底座, 告警阈值/推送增强)"),
        ],
    },
    "F 产品化/AI工程": {
        "安全": [
            ("F-1", "Prompt 注入防护: 任务/文档恶意内容诱导 Agent"),
            ("F-2", "供应链/依赖安全: licenses/CVE 扫描"),
        ],
        "产品化": [
            ("F-3", "模型评测: 同任务换模型对比表现"),
            ("F-5", "API/SDK 对外: public API 边界/文档/版本承诺"),
            ("F-6", "模板库: 常用产品模板一键生成"),
            ("F-7", "移动端体验: pad/手机完整流程"),
            ("F-10", "测试覆盖度: 模块覆盖率统计"),
            ("F-12", "数据归档/生命周期: audit 增长/旧项目归档"),
        ],
    },
    "G Web 产品化": {
        "收尾": [
            ("G-5", "Web Agent/Skill 管理增强 (设置已有人话管理, 详情/编辑增强)"),
            ("G-6", "Web 与 board 统一: 监控+操作一体"),
        ],
    },
    "I 调用链路": {
        "链路": [
            ("I-2", "调用链可视化: 一次请求经过的模块/action 链路图"),
            ("I-3", "链路可控: 链路级暂停/拦截/重试/回退"),
        ],
    },
    "数据治理": {
        "治理": [
            ("DATA-1", "markpad 示例项目清理"),
            ("DATA-2", "org 数据同步/脏数据清理"),
        ],
    },
    "L 长期企业级": {
        "企业级": [
            ("L-1", "50+ 消息平台（P1 20 渠道 / P2 长尾）"),
            ("L-2", "三级 RAG 完整（知识图谱/规则库）"),
            ("L-3", "纵深防御/安全事件响应落地"),
            ("L-4", "数据主权/合规认证（信创/SOC2/等保）"),
            ("L-5", "RBAC 角色表（Owner/Admin/Operator/Viewer/Auditor）"),
            ("L-6", "Skill 调用链进 Agent 循环 + 本机 AI CLI 委托"),
            ("L-7", "领域知识库"),
        ],
    },
}


def find_by_name(items: list[dict], name: str) -> dict | None:
    for it in items:
        if str(it.get("name") or "") == name:
            return it
    return None


def main() -> int:
    svc = _adapter.build_console_service(ROOT / ".." / ".." / ".factory" if False else Path.home() / ".factory", event_logger=None)
    created = 0
    for epic_name, features in PLAN.items():
        backlog = svc.list_backlog(PROJECT) or {}
        epics = backlog.get("epics", [])
        epic = find_by_name(epics, epic_name)
        if epic is None:
            epic = svc.create_epic(PROJECT, name=epic_name, description="待办清单/债务清单 系列 (Founder 导入)")
            created += 1
        for feat_name, tasks in features.items():
            backlog = svc.list_backlog(PROJECT) or {}
            features_list = backlog.get("features", [])
            feature = find_by_name(features_list, feat_name)
            if feature is None:
                feature = svc.create_feature(PROJECT, name=feat_name, epic_id=epic["id"])
                created += 1
            backlog = svc.list_backlog(PROJECT) or {}
            stories = backlog.get("stories", [])
            story = find_by_name(stories, f"{epic_name} · {feat_name}")
            if story is None:
                story = svc.create_story(PROJECT, name=f"{epic_name} · {feat_name}", feature_id=feature["id"])
                created += 1
            backlog = svc.list_backlog(PROJECT) or {}
            task_titles = {t.get("title") for t in backlog.get("tasks", [])}
            for tid, title in tasks:
                if title in task_titles:
                    continue
                svc.create_task(PROJECT, title=title, description=f"[{tid}] 待办清单未实现项", priority="P2", story_id=story["id"])
                created += 1
    print(f"✅ 计划树导入完成: 新增 {created} 节点 (史诗/模块/故事/任务) 于 {PROJECT}")
    backlog = svc.list_backlog(PROJECT) or {}
    print(f"   现在 backlog: epics={len(backlog['epics'])} · features={len(backlog['features'])} · stories={len(backlog['stories'])} · tasks={len(backlog['tasks'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
