"""架构 域命令注册（apps/cli/domains/architecture）。

★ 2026-09-15 新增: 兑现 `registry.py` 里登记的 `"architecture": ("arch",)`。

此前该域**只有能力、没有命令入口**:
  ✅ 能力   plugins/agents/architect.py:ArchitectAgent（Product + UX/UI → Design Artifact 7 节）
  ✅ 契约   services/organization/artifact.py 的 CONTRACTS["design"]（7 节必填 + 规则）
  ✅ 阶段   services/organization/projects.py  Stage.ARCHITECTURE
  ✅ 门     factory product approval request <artifact_id> --gate architecture
  ❌ 命令   registry 承诺了 `arch`, 但 domains/ 无实现 ⇒ 本文件补上（Founder 裁决 A）

命令（8 环里的第 4 环「架构设计」）:
    arch list  [--project P]      列 Design Artifact
    arch show  <artifact_id>      Design Artifact 详情（7 节）
    arch design --project P       触发 ArchitectAgent 产出 Design Artifact
    arch gates                    架构决策门的策略投影

底层: services/organization（ArtifactRegistry）+ plugins/agents（ArchitectAgent）。
"""

from __future__ import annotations

from typing import Any


def register(sub: Any, json_opt: Any) -> None:
    """注册 arch 命令（命令域 architecture; 见 apps/cli/registry.py）。"""
    p = sub.add_parser(
        "arch",
        help="架构设计 (8 环第 4 环): list / show / design / gates —— "
             "Architect Agent 产出 Design Artifact (7 节)",
    )
    p.add_argument(
        "arch_command", choices=["list", "show", "design", "gates"], nargs="?",
        default="list", metavar="动作",
        help="list — 列 Design Artifact; show <id> — 详情(7 节); "
             "design --project P — 触发 ArchitectAgent; gates — 架构门策略",
    )
    p.add_argument("artifact_id", nargs="?", default=None, metavar="<id>", help="Design Artifact id（show）")
    p.add_argument("--project", default=None, help="项目 id（list 过滤 / design 必填）")
    p.add_argument("--product", default=None, help="(design) Product Artifact id（缺省自动取项目最新）")
    p.add_argument("--ux-ui", dest="ux_ui", default=None, help="(design) UX/UI Artifact id（缺省自动取项目最新）")
    json_opt(p)
