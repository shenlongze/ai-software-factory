# Phase 12B-1 — 验证项目选择: MarkPad

> 日期: 2026-08-06

## 项目背景

MarkPad 是 Typora 类跨平台 Markdown 编辑器 (Flutter 3.44, macOS 优先, 目标 Windows)。核心能力: 所见即所得渲染 + 源码编辑 + 双视图。项目已有完整工程 (lib/editor/block_editor.dart 等), 1000+ 测试, v0.3.0-alpha 已发布。

## 用户需求 (本次验证需求)

**MarkPad 表格编辑器增强**:
- 支持表格单元格逐格编辑 (当前仅整表编辑)
- Tab 键单元格导航
- 内联编辑, 保持 Typora 极简风格

## 为什么适合作为 Factory 验证

```
1. 真实项目: 已有工程/代码/测试 (非虚构)
2. 完整接入: Phase 5A 已配置 examples/markpad (project.yaml/agents/workflows)
3. 需求明确: 表格编辑是真实痛点 (用户提过), 复杂度适中
4. 生命周期完整: Idea→Research→PRD→UI→Architecture→Task 全链可验证
5. Phase 7 已识别: understanding 分析 markpad = PRODUCTION 0.95
```

## 验证目标

```
1. Factory 完整生命周期闭环: Idea→Research→PRD→[人工]→UI→[人工]→Architecture→Task→Experience
2. 每个阶段产生 Artifact + Event + Decision + Evidence
3. Intelligence: Provider Recommendation 四因素可解释
4. Experience Loop: 成功+失败经验影响推荐
5. 发现真实流程问题
```

## 验证环境

```
- 临时工厂根 (不污染真实数据)
- Provider 生成内容: Mock Adapter (固定产物; 生命周期/审批/决策/经验全部真实逻辑)
- 人工批准: shenlongze (PO)
```
