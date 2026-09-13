"""factory-core/demo — Phase 13A Demo Productization (产品化演示)。

`factory demo markpad` 演示编排: 从 examples/markpad-demo/ 读 idea/requirements
→ 临时工厂根 (tempfile) → 注入 Mock Provider (Phase 12B 模式, 只生成内容)
→ 跑完整生命周期 (idea→research→prd→[审批]→ui→[审批]→architecture→task→
experience)。生命周期/审批/决策/Task/经验全部走真实逻辑, Core 零修改。

Removal Isolation: 本包只被 cli.commands.cmd_demo_markpad 延迟导入; 删除
demo/ 不影响 CLI 加载 (同 product/providers 延迟导入模式)。
"""

from .markpad import DemoError, default_demo_dir, run_markpad_demo

__all__ = ["DemoError", "default_demo_dir", "run_markpad_demo"]
