"""factory-org — AI Software Factory 组织扩展 (Phase 16A, ADR-0036)。

独立 Extension 包 (factory-org/org/ — 测试/CLI 把 factory-org/ 目录挂到
sys.path 后以 `org` 导入; 目录名含连字符, 包名本身 `org` 合法)。
Core/Runtime/Desktop 零修改; 事件驱动 (org.* 经 factory-core EventLogger);
Default Deny 权限模型 (Authority 绑定 Role, 未声明即拒绝)。

Removal Isolation: factory-core 零顶层 imports 本包 (CLI 延迟导入, 缺包 →
rc 7 响亮配置缺口); 本包依赖 factory-core events 层 (Extension 依赖 Core,
反向不成立)。

顶层 __init__ 故意不 import 子模块 (延迟加载): `import org` 零副作用,
删除 factory-org 不影响 Factory 其余命令。
"""

__version__ = "0.1.0"
