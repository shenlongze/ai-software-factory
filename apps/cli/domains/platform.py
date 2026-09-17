"""平台 域命令注册（apps/cli/domains/platform）。

本域命令（依据 `apps/cli/registry.py` 的 `platform`）:
    create  统一创建入口（company / department / project）
    init / config / doctor / start / stop / status / service / llm / provider /
    router / update / help / demo / sync / git / rag / context / context-rank   ← 待搬/已在 main

搬迁来源: 老 CLI `_pending_migration/factory_console/cli_factory.py`
          · 参数注册 p_create（L10206）· 处理 create_cmd（L8600）
底层能力: **已在新地基** `ai_factory_os.services.organization.cli`
          （`_proxy_org_cli` 指向的就是它；函数实测可达:
           cmd_company_create / cmd_department_create / cmd_project_register）
"""
from __future__ import annotations

from typing import Any, Callable


def register(sub: Any, json_opt: Callable[[Any], None]) -> None:
    """注册 platform 域的命令。sub = 主 subparsers 容器; json_opt = 共享的 --json 选项。"""
    # factory create <type> [选项] —— 统一创建入口（§1.4.5 便捷铁律）
    p_create = sub.add_parser(
        "create", help="统一创建入口 (company/department/project, §1.4.5 便捷铁律)"
    )
    p_create.add_argument("create_type", choices=["company", "department", "project"],
                          help="创建类型")
    p_create.add_argument("--name", default="", help="名称 (company/department/project)")
    p_create.add_argument("--template", default="solo", choices=["solo", "software_company"],
                          help="公司模板 (company)")
    p_create.add_argument("--company", default="", help="所属公司 (department 必填 / project 可选)")
    p_create.add_argument("--departments", default="", help="关联部门逗号分隔 (project 可选)")
    p_create.add_argument("--goal", default="", help="项目目标 (project 可选)")
    p_create.add_argument("--id", default=None, help="实体 ID (默认自动生成 C-/D-/P-xxx)")
    p_create.add_argument("--language", default="", help="主语言 (project, 缺省自动检测)")
    p_create.add_argument("--framework", default="", help="框架 (project, 缺省自动检测)")
    p_create.add_argument("--build-command", dest="build_command", default=None,
                          help="构建命令 (project)")
    p_create.add_argument("--test-command", dest="test_command", default=None,
                          help="测试命令 (project)")
    p_create.add_argument("--project-type", dest="project_type", default=None,
                          help="项目类型 (project)")
    p_create.add_argument("--repo-path", dest="repo_path", default=None,
                          help="仓库路径 (project; 缺省 = 数据目录)")
    json_opt(p_create)
