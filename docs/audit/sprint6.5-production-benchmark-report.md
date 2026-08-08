# Sprint 6.5 Production Benchmark

> 日期: 2026-08-08 | 类型: 真实生产测量 (27 次 v4-pro 执行, 禁 mock)
> 模型: deepseek-v4-pro | Runtime: EmployeeExecutor → DeveloperAgent → 沙箱 → 验证 → 经验

## 1. Executive Summary

```
✅ 达到生产标准 (单任务级):
  27/27 runs 成功 (score≥4) | 满分 25/27 (93%) | 总成本 $0.789
  Level 1 (简单) 9/9 满分 | Level 2 (中等) 9/9 满分 | Level 3 (复杂) 7/9 满分 + 2/9 4分

结论: AI Factory 已具备真实单任务生产能力 (Python 项目)
  - 简单/中等任务: 可放心自动完成 (满分率 100%)
  - 复杂跨模块重构: 需人工审核 (patch 有效但 2/3 runs 测试未全过)
```

## 2. Test Environment

```
模型: deepseek-v4-pro (DeepSeek 端点, OpenAI 兼容)
Runtime: EmployeeExecutor.execute → AgentRuntime → DeveloperAgent
沙箱: 副本 + git + 验证循环 (1 初始 + ≤2 修复)
验证: python3 -m unittest discover
评分: 5 维 (patch 生成/有效/沙箱测试/report/经验) 每维 0/1
项目: s6b (5 模块 Python 包 + 5 测试文件, 基线 16 测试)
成本: 估算口径 (gpt-4o 费率, DeepSeek 实际更低)
```

## 3. Sample Results

| 任务 | 等级 | Run1 | Run2 | Run3 | 均分 | 成本 |
|:-----|:----:|:----:|:----:|:----:|:----:|:----:|
| T1 sum_list 漏首元素 | L1 | 5 | 5 | 5 | 5.0 | $0.048 |
| T2 truncate 默认值 | L1 | 5 | 5 | 5 | 5.0 | $0.048 |
| T3 factorial 边界 | L1 | 5 | 5 | 5 | 5.0 | $0.044 |
| T4 新增 clamp 函数 | L2 | 5 | 5 | 5 | 5.0 | $0.078 |
| T5 跨模块 API 修正 | L2 | 5 | 5 | 5 | 5.0 | $0.048 |
| T6 输入校验 | L2 | 5 | 5 | 5 | 5.0 | $0.048 |
| T7 跨模块重构 (重命名) | L3 | 4 | 5 | 4 | 4.3 | $0.234 |
| T8 新增模块+集成 | L3 | 5 | 5 | 5 | 5.0 | $0.092 |
| T9 数据结构变更适配 | L3 | 5 | 5 | 5 | 5.0 | $0.150 |

```
汇总: 成功率 100% (27/27) | 满分率 93% (25/27) | 总成本 $0.789
延迟: L1 ~5-9s | L2 ~10-28s | L3 ~20-270s (T7 重构最慢 269s)
```

## 4. Capability Analysis

```
🟢 Green (可自动完成, 满分):
  - 单文件 Bug 修复 (求和/边界/逻辑)
  - 参数默认值调整
  - 新增小功能函数 + 测试
  - 跨模块 API 修正 (B 调 A 错误参数)
  - 输入校验增强
  - 新增模块 + 集成
  - 数据结构变更 + 全量适配

🟡 Yellow (需人工审核):
  - 跨模块重构 (接口重命名 + 全量适配): patch 有效但测试偶发未全过
    (T7: 2/3 runs test=0 — 需人工确认修改完整性)

🔴 Red (暂不能交付):
  - 无 (27/27 成功) — 但复杂任务成本/延迟高 (T7: $0.23, 4.5 分钟)
```

## 5. Production Boundary

```
✅ 可以处理:
  - Python 项目: bug 修复/参数调整/小功能/跨模块修正/新模块/结构变更
  - 单任务规模: 3-5 文件, ≤500 行变更
  - 预算: 单任务 $0.01-0.23 (v4-pro)

❌ 不能处理 (当前):
  - 大型项目 (markpad 2.2G 沙箱慢) — 需选择性复制优化
  - 多阶段协作 (PM→Design→Dev 接力未实现)
  - 全栈 (前端/后端/DB) — 无专门工具
  - Build/Package/发布
  - 非 Python 项目 (未验证; Dart/JS 需验证)
```

## 6. Recommendation（最小必要修改）

```
1. T7 类重构增强: 重构后运行全量测试 + 缺失引用检测 (减少 test=0)
2. 沙箱选择性复制默认化 (大项目可用)
3. Tester 角色 executable (验证循环升级为角色化)
4. 成本/延迟记录真实费率 (DeepSeek 定价回填 Capability Registry)
```

## 最终回答

```
"用户明天提交什么任务可放心交给 AI Factory?"

✅ 放心交付 (自动):
  - Python 项目的 Bug 修复 / 参数调整 / 简单逻辑修正
  - 新增小功能函数 (+ 测试)
  - 跨模块 API 修正 / 输入校验

🟡 需审核后交付:
  - 跨模块重构 (接口重命名/结构变更) — AI 产出 patch, 人工验证完整性

❌ 暂不交付:
  - 完整新软件 / 前端后端全栈 / 非 Python 大项目 / 发布部署

结论: 单任务级生产 ✅ (Python, 5 文件内) — "可以开始用了"
```
