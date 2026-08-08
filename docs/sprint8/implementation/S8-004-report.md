# S8-004 — Release Agent（Completion Report）

> 日期: 2026-08-09 | 状态: 完成 (待人工审核) | pytest 6274 (6204 + 70)
> 目标: devops executable — Code + Test(VALIDATED) → Release Artifact (5 节)

## 实现说明

```
roles.py      devops planning → executable; _DEVOPS_PROMPT 5 节 (build_result/version/
              package/release_notes/deployment) + 质量门禁 ("未通过测试禁止发布");
              workflow_stages: deployment → release
release.py    新建: ReleaseAgent (Code+Test 双输入, Test 必须 VALIDATED 强校验,
              artifact_refs=[code_id, test_id]) + ReleaseArtifact 5 节 + 解析链/垃圾拒绝
artifact.py   CONTRACTS release 3 字段 → 5 节 (build_result dict status/command,
              version, package dict name/type/files, release_notes, deployment)
demo.py       _DEMO_RELEASE_METADATA 5 节 (S7-005 兼容)
Workflow      release stage (role_ref=devops, input=[code,test]); test VALIDATED→READY,
              未过→BLOCKED (Runner 零修改)
```

## Release Artifact Schema（5 节）

| # | 字段 | 类型 | 规则 |
|---|------|------|------|
| 1 | build_result | dict | required_keys [status, command] |
| 2 | version | str | 非空 (如 0.1.0) |
| 3 | package | dict | required_keys [name, type, files] |
| 4 | release_notes | str | 非空 (changelog) |
| 5 | deployment | str | 非空 (部署步骤) |

## Agent 设计

```
ReleaseAgent.develop(code, test):
  - 双输入构造强校验 (缺任一 → ReleaseError)
  - Test 未 VALIDATED → 响亮拒绝 (禁止发布未测代码)
  - 输出含 artifact_refs=[code_id, test_id] (可审计来源)
  - build_release_executor (Workflow 适配器)
```

## 测试（70 新增，s8 套件 254）

```
release_role 10 (executable/prompt 5 节/质量门禁)
release_contract 27 (契约 5 节/required_keys/Registry 全链)
release_agent 30 (双输入强校验/Test 门禁/解析/响亮拒绝/artifact_refs)
release_workflow (BLOCKED+READY/事件)
修复: 1 实现 bug (质量门禁文案) + 18 旧断言同步 (deployment→release/3 字段→5 节/6 角色)
```

## S8-005 Demo 准备

```
全链: PM → UX/UI → Arch → Dev → Test → Release 6 角色全 executable (mock 测试)
真实 v4-pro: 记账 Web App (HTML/CSS/JS + 静态测试 + zip 打包)
Release 门禁: Test VALIDATED 强制 — 质量保障闭环完整
```

## 验证门

```
pytest 全量: 6274 passed, 0 failed
Core/Runtime/Console/Desktop diff = 0
```
