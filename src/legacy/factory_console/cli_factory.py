"""factory_console.cli_factory — 统一 CLI 入口的导入别名 (S10-031 Task 2)。

真实实现: factory-console/cli_factory.py (main() 统一入口,
init/doctor/config/start/project/run 等 17+ 命令)。
目录名 factory-console 含连字符, 生成式 console script 只能生成
`from <有效标识符模块> import <attr>`, 故经本模块 importlib 转发,
使 pyproject [project.scripts] 的 `factory = "factory_console.cli_factory:main"`
在 pip install 后可用。零业务逻辑, 纯打包胶水。
"""

from importlib import import_module

main = import_module("factory-console.cli_factory").main

__all__ = ["main"]
