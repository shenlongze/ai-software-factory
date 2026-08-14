# S10-046 Task 003 — PyPI Release Preparation

> 日期:2026-08-14 | Sprint: S10-046 Public Release | 真实验证
> 目标: 确认 package 可发布 PyPI, 全新环境可安装可运行

---

## 1. pyproject 元数据

| 项 | 值 | 状态 |
|---|---|---|
| name | ai-software-factory | ✅ |
| version | 0.1.0 | ✅ |
| description | AI Software Factory — An AI Workforce Operating System (build, manage and govern AI workers) | ✅ 用户向 |
| readme | README.md | ✅ |
| requires-python | >=3.12 | ✅ |
| license | Apache-2.0 (LICENSE 文件) | ✅ |
| console script | factory = factory_console.cli_factory:main | ✅ |

## 2. 依赖(完整)

```
pydantic>=2 / rich>=13 / pyyaml>=6 / httpx>=0.27 / fastapi>=0.110 / uvicorn>=0.29
```

## 3. Wheel 构建验证

```
✅ ai_software_factory-0.1.0-py3-none-any.whl
   内容: factory_console 41 文件 + exec 50 + org 18 + frontend dist 3
```

## 4. 全新环境安装验证(真实)

```
✅ python3.12 -m venv → pip install wheel → factory 命令可用
✅ factory --help → "AI Factory v0.1.0 — AI Workforce Operating System"
✅ factory init → workspace + providers.json
✅ factory demo run "给 main.py 加 hello" → 真实执行 success
   result-id: EXS-5341a391
```

## 5. PyPI 发布就绪判定

**✅ 可发布。** 技术全通(构建/安装/运行)。

发布步骤(用户决策后):
```bash
# 1. 需要 PyPI 账号 + API token
# 2. 上传
python -m pip install twine
python -m twine upload /tmp/s10046-dist/ai_software_factory-0.1.0-py3-none-any.whl
# 3. 验证
pip install ai-software-factory
factory demo run "hello"
```

## 6. 备注

- README 中 "pip install ai-software-factory 即将支持" → 发布后改为正式安装方式
- 版本 0.1.0 与 tag v0.1.0 一致

---

> Task 003 完毕 | wheel 构建 + 全新环境安装 + 真实执行全通过 | PyPI 可发布
