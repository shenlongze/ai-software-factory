# S10-035 Task 002 — Fresh User Installation Test

> 日期:2026-08-14 | Sprint: S10-035 | 真实全新环境模拟(未修改代码)
> 目标: 验证陌生用户能否完整走通 install → init → doctor → config → project → run

---

## 1. 测试环境

```
全新 venv: python3.12 -m venv /tmp/s10035-venv
安装方式: pip install -e .(模拟陌生用户源码安装; wheel 已在 S10-031 验证)
数据隔离: HOME=/tmp/s10035-home
LLM key: DEEPSEEK_API_KEY 环境注入(不落盘)
```

## 2. 执行结果

| 步骤 | 命令 | 结果 | 用户体验 |
|---|---|---|---|
| 1. 安装 | pip install -e . | ✅ exit 0 | 干净 |
| 2. 命令可用 | factory --help | ✅ 统一入口 | 清晰 |
| 3. init | factory init --non-interactive --provider deepseek | ✅ 3 ✓(环境/workspace/providers.json) | 良好 |
| 4. doctor | factory doctor | ✅ 1 PASS / 4 WARN | WARN 有修复提示 |
| 5. config | factory config show | ✅ 配置显示 | 良好 |
| 6. project create | factory project create --repo-path | ✅ P-fef2fe9f 注册 | 良好 |
| 7. project list | factory project list | ✅ 显示项目 | 良好 |
| 8. run | factory run --project --task --agent | ✅ **success** | 真实执行 |
| 9. artifact | run-status 输出 | ✅ patch/report/usage | 完整 |

## 3. 真实执行证据

```
status      success
artifact    patch        ~/.factory/exec/patches/EXS-a3f52711.patch
artifact    report       ~/.factory/exec/EXS-a3f52711.report.md
usage       prompt 1793 + completion 3787 = 5580 tokens
            estimated_cost_usd $0.002093
event_seq   8 (审计事件)
```

## 4. 用户体验问题

| # | 问题 | 严重度 | 建议 |
|---|---|---|---|
| 1 | doctor 4 个 WARN(provider key 缺失提示正确) | 低 | 正常(未注入 key 时) |
| 2 | config show 显示"未配置"(data_dir 默认) | 低 | 正常语义 |
| 3 | run 前需手动 mkdir 项目目录 | 低 | 文档已说明 |
| 4 | doctor 的 WARN 不阻断 exit 0 | 低 | 设计如此 |

**无阻塞问题。**

## 5. 结论

**陌生用户完整路径全部成功**: 安装 → 初始化 → 诊断 → 配置 → 创建项目 → 真实 LLM 执行 → 产物 + 审计。

- ✅ pip install 成功
- ✅ 全命令可用
- ✅ 真实执行(5580 tokens, $0.002)
- ✅ 无错误信息(除预期 WARN 提示)
- ✅ 体验良好(无阻塞)

---

> Task 002 完毕 | 全新用户安装测试全部通过 | 无阻塞
