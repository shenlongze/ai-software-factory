# S10-103 — 发现流程命令分流 + CLI 输入健壮性：独立验收报告

> 日期: 2026-08-24 | 版本: v1.1.24 | 验收人: Hermes (CTO, 独立验证 — 非 Codex 自报告)
> 实现: `db3623a` (feat(S10-103), 13 files)
> 前置: v1.1.23 · S10-099~102 产品发现链已验收

---

## 验收矩阵

| # | 验收项 | 结果 | 证据 |
|---|---|---|---|
| 1 | 发现中 "/status" → 显示状态不当字段 | ✅ | 模型层 passthrough + problem 不被填; 宿主级 registry 执行 → "=== 会话状态 ===" 输出 |
| 2 | "exit" → 退出 | ✅ | 模型层 exit_requested + problem 不被填; 宿主级 running=False + "已退出会话" |
| 3 | 确认中 slash 同样分流 | ✅ | handle_product_confirm("/status") → passthrough, 名称不被改; "exit" → exit_requested |
| 4 | project 提示含 status | ✅ | "错误: project 需要子命令 (create / list / rename / status), 收到: None" + rc 2 |
| 5 | create 无 name → rc 2 | ✅ | "错误: create project 需要 --name <项目名>" + rc 2 |
| 6 | 字段收集正常 | ✅ | 普通字段答案原样入字段 |
| 7 | 全量回归 0 新增 | ✅ | console+api: **4991 passed / 1 skipped / 0 failed** |
| 8 | 版本 v1.1.24 | ✅ | pyproject = 1.1.24; 版本断言通过; CHANGELOG v1.1.24 |

## 1. 独立验证实录（我的脚本, 20/20）

```
模型层:
✅ 发现中 "/status" → passthrough, problem=None (不再填 '/status')
✅ 发现中 "exit"/"quit" → exit_requested, problem=None (不再推进到确认)
✅ 确认中 "/status" → passthrough, 名称不被改; "exit" → exit_requested
✅ "退出" → 仍取消发现 (向后兼容, 非退出会话)
✅ 字段收集正常: "记账麻烦, 月底对不上账" → problem 正确入字段
✅ handle() "/help" → passthrough (不再死胡同消息)

宿主级 (InteractiveSession):
✅ 发现中 "/status" → registry 执行: "=== 会话状态 ===\nsession_id: ..." (不当字段)
✅ "exit" → running=False

CLI (真实模块):
✅ factory project (无子命令) → rc 2 + 提示含 status
✅ factory create project (无 --name) → rc 2 + "错误: create project 需要 --name <项目名>"
```

## 2. 关键设计验证（反虚标）

- **命令分流确定性**: _command_escape 纯规则 (slash 前缀 / EXIT_COMMANDS 精确匹配), 不依赖 LLM
- **向后兼容顺序**: _product_control 先于命令分流 → "退出" 保持"取消发现"语义 (EXIT_COMMANDS 含"退出"
  但被取消短语先行拦截); 剩余 exit/quit/再见/退出会话 → exit_requested
- **两路径**: handle_product_answer + handle_product_confirm 对称接入; handle() 顶部 slash 分支改 passthrough
- **单一来源**: EXIT_COMMANDS 移至 discovery_guide (session 改 import, 集合内容不变 — 既有测试零影响)
- **宿主复用**: slash passthrough 走既有重分发机制 (_dispatch 递归 → registry); exit_requested 新增宿主处理

## 3. 契约测试

- 新增 `test_s10_103_command_routing.py` 20 用例 (计划 §2 契约 1-9)
- 既有更新: test_handle_slash_keeps_state (slash 行为变化 → passthrough, 注释); 版本断言 1.1.23→1.1.24
- 全量: 4991 passed / 1 skipped / 0 failed (console+api, env -u) — 本次连 m3e flaky 都未出现

## 4. 诚实记录（工程资产）

- 我的验收脚本 3 处修正: (1) 宿主级 /status 断言误以为 problem 应为空 (实际该轮已合法填了 problem,
  关键断言是 problem ≠ "/status"); (2) FactoryCLI 类名在别名包不存在 (repo-root factory_console/ 是
  S10-031 import 别名包, 只转发 main) → 改 import_module("factory-console.cli_factory") 载真实模块;
  (3) data_dir 需 Path。均脚本问题, 非实现缺陷 — 也印证了 S10-031 别名包设计 (非遮蔽 bug)
- Codex 报告全量 console 4906 (沙箱) vs 我的 4991 (console+api) — 环境差异 (其沙箱 m3e flaky 一次)

## 5. 结论

- **通过**。🔴 命令被当字段的严重逻辑 bug 修复: slash → passthrough (宿主真正执行), exit/quit → 退出信号,
  发现/确认两路径全覆盖, 字段不再被命令污染; 🟡 CLI 小修完成 (project 提示补 status, create --name 必填)。
- 范围声明遵守: prompt_toolkit / 会话历史持久化 未做 (进 backlog)。
