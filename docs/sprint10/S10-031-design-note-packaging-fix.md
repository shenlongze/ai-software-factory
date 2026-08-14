# S10-031 Design Note — Release Packaging 修复(约束 8)

> 日期:2026-08-14 | Sprint: S10-031 | 发现问题后的 Reality Check + 修复设计
> 问题:Task 2(6295097)console script 指向 factory_console,但 wheel 构建为**空壳**(无代码包)

---

## 1. Reality Check(实测证据)

| 检查 | 结果 |
|---|---|
| wheel 构建 | ✅ 成功(ai_software_factory-1.0.0rc1-py3-none-any.whl,529KB) |
| wheel 内容 | ❌ **仅 dist-info,零代码包**(factory 相关条目只有 6 个 dist-info 文件) |
| pip install 后 factory 命令 | ❌ ModuleNotFoundError: No module named 'factory_console' |
| find_packages('.') | ⚠️ 返回 'factory-console'(连字符包名),build 时未正确入包 |
| packages.find where | ❌ where=["factory-core","factory-console","factory_console"] — factory_console 是"搜索根"而非"包",未被找到 |

## 2. 根因

1. `[tool.setuptools.packages.find] where` 把 `factory_console`(胶水包)当搜索根,setuptools 从 where 目录**内部**找包,不把 where 目录本身当包 → factory_console 未被打包
2. `factory-console` 目录名含连字符,不是合法 Python 包名 → 即使打包也无法 `import factory-console`
3. 胶水 factory_console/cli_factory.py 的 `import_module("factory-console.cli_factory")` 依赖源码根在 sys.path(源码运行 OK),但 wheel 安装后无源码根 → 失败

## 3. 修复方案:package_dir 映射(最小,不重构)

```toml
[tool.setuptools]
package-dir = { "factory_console" = "factory-console" }
packages = ["factory_console"]   # 显式: 映射后 factory_console = factory-console 目录内容
```

- factory_console 包 = factory-console 目录内容(cli_factory.py/config.py/llm_control.py/...)
- 内部相对导入 `from .config import ...` 自动解析为 factory_console.config ✅(41 个相对导入全部一致)
- console script `factory = "factory_console.cli_factory:main"` 直接可用,不再需要胶水转发
- 删除 factory_console/cli_factory.py 胶水(映射后 factory_console 目录被 factory-console 覆盖语义)
- factory-core 子包(events/agents/...)仍需打包:where 需同时覆盖 factory-core

```toml
[tool.setuptools.packages.find]
where = ["factory-core", "."]   # "." 使 factory_console(映射包)可被发现? 需验证
# 或显式 packages = ["factory_console"] + find where=["factory-core"]
```

## 4. 验证方法(修复后)

```
1. python -m build --wheel → wheel 内容含 factory_console/ 代码
2. pip install wheel 到干净 venv
3. factory --help → 统一入口 (init/doctor/config/start/project/run)
4. factory doctor → 可运行
5. 全量 pytest 不破坏 (8144 + 0)
```

## 5. 失败预案

- package_dir + packages 显式组合若 setuptools 拒绝(映射包名含连字符目录)→ 备选:源码树内软链接 factory-console → factory_console(不推荐,污染)
- 或:wheel 只打包 factory-core 子包 + factory_console 胶水 + package-data 包含 factory-console 源码目录 → console script 运行时 sys.path 注入源码目录(复杂,备选)

## 6. 范围

- 修改:pyproject.toml(package_dir/packages/find)
- 删除:factory_console/cli_factory.py 胶水(若映射后不需要)
- 测试:更新 test_release_packaging.py(验证 wheel 含代码包 + 安装后可运行)
- 不动:factory-console/ 业务代码、factory-exec/org/core、Router/Kernel

---

> Design Note 完毕 | 根因:packages.find where 配置错误 + 连字符包名 | 方案:package_dir 映射
