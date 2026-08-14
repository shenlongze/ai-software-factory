# S10-034 Task 001 — Repository Cleanup Audit

> 日期:2026-08-14 | Sprint: S10-034 Open Source Release | 只读审计,未修改仓库
> 目标:公开前识别需清理的文件(不删除重要历史/Sprint 文档)

---

## 1. 根目录文件检查

| 文件 | 状态 | 是否需要处理 | 原因 |
|---|---|---|---|
| README.md | ✅ 已跟踪 | 否(保留) | 用户向产品文档(S10-031) |
| LICENSE | ✅ 已跟踪 | 否 | Apache-2.0 |
| CONTRIBUTING.md | ✅ 已跟踪 | 否 | 贡献指南 |
| SECURITY.md | ✅ 已跟踪 | 否 | 安全策略 |
| CODE_OF_CONDUCT.md | ✅ 已跟踪 | 否 | 行为准则 |
| CHANGELOG.md | ✅ 已跟踪 | 否 | 版本记录 |
| pyproject.toml | ✅ 已跟踪 | 否 | 包配置 |
| .gitignore | ✅ 已跟踪 | 需修改 | 补 coverage/ + 根目录中文 md |
| CLI命令参考文档.md | ❌ 未跟踪 | **需忽略** | 早期工作文档,非开源内容 |
| LLM智能路由设计说明.md | ❌ 未跟踪 | **需忽略** | 同上 |
| 软件市场价值评估-v1.md | ❌ 未跟踪 | **需忽略** | 同上 |
| 商业评测-v1.md | ❌ 未跟踪 | **需忽略** | 同上 |
| 项目代码逻辑总结.md | ❌ 未跟踪 | **需忽略** | 同上 |
| 项目级RAG方案-v1.md | ❌ 未跟踪 | **需忽略** | 同上 |
| 项目全量扫描总结-v2/v3.md | ❌ 未跟踪 | **需忽略** | 同上 |
| 项目扫描报告.md | ❌ 未跟踪 | **需忽略** | 同上 |
| 项目总纲.md | ❌ 未跟踪 | **需忽略** | 同上 |
| 行业竞品分析-v1.md | ❌ 未跟踪 | **需忽略** | 同上 |
| 验证报告-idea到产品完整路径.md | ❌ 未跟踪 | **需忽略** | 同上 |

## 2. 其他目录检查

| 路径 | 状态 | 是否需要处理 | 原因 |
|---|---|---|---|
| docs/sprint10/S10-021-reality-check.md 等 5 个 | ❌ 未跟踪 | **保留(忽略清单外)** | 重要 Sprint 历史文档,应 add 或保留 |
| docs/audit/LLM-CAPABILITY-AUDIT.md | ❌ 未跟踪 | 保留 | 审计历史 |
| frontend/coverage/ (1.9M) | ❌ 未跟踪 | **需忽略** | 构建产物(coverage 报告) |
| docs/sprint10/ 已跟踪文档 | ✅ | 保留 | Sprint 交付 |

## 3. 敏感信息检查

| 检查项 | 结果 | 证据 |
|---|---|---|
| API key 明文 | ✅ 无 | 全仓扫描无命中(排除 test 假 key) |
| .env 被跟踪 | ✅ 无 | git ls-files 无 .env/secret/pem |
| 个人路径 | ✅ 仅"不读取"注释 | config.py/workflow_runner.py |
| 私人配置 | ✅ 无 | gitignore 完整 |

## 4. 清理方案(不删除,gitignore 忽略)

```
1. .gitignore 增加:
   # 早期工作文档 (公开仓库不展示)
   /*.md  ← 太宽? 不用; 精确列:
   /CLI命令参考文档.md
   /LLM智能路由设计说明.md
   /软件市场价值评估-v1.md
   /商业评测-v1.md
   /项目代码逻辑总结.md
   /项目级RAG方案-v1.md
   /项目全量扫描总结-v2.md
   /项目全量扫描总结-v3.md
   /项目扫描报告.md
   /项目总纲.md
   /行业竞品分析-v1.md
   /验证报告-idea到产品完整路径.md
   # 前端覆盖率
   factory-console/web/frontend/coverage/

2. docs/sprint10 未跟踪 5 个早期文档 → git add (保留历史)
   docs/audit/LLM-CAPABILITY-AUDIT.md → git add (保留)
```

**原则:不删除任何文件;未跟踪文件要么 add(重要历史)要么 gitignore(工作文档/产物)。**

## 5. 结论

- **无敏感信息风险** ✅
- **无临时/调试/实验脚本** ✅(仅前端 coverage 产物)
- **11 个根目录中文 md = 早期工作文档**(gitignore 忽略,不删除)
- **5 个 docs/sprint10 早期文档 = 重要历史**(add 保留)
- 需修改 .gitignore(1 处)+ add 历史文档

---

> Task 001 完毕 | 只读审计 | 无敏感信息 | 清理方案: gitignore 忽略工作文档 + add 历史文档
