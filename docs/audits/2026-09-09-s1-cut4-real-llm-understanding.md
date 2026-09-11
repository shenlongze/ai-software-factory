# S1 第 4 刀 — 真实 LLM 理解链路复验报告

> Date: 2026-09-09 | 性质: 复验 + 证据落盘 | 判定: **REAL**
> 目的: 消除第 3 刀环境偏差 (当时 shell 未导出 DEEPSEEK_API_KEY, 理解段走 deterministic)
> 范围: 只到 Plan 确认; 未执行「开始做」; 未重跑 codex; 零代码改动; 无 commit

---

## 1. 冒烟结果 (opt-in 真实 LLM)

```
FACTORY_REAL_LLM=1 .venv/bin/python -m pytest tests/console/test_real_llm_smoke.py
→ 1 passed in 2.35s  (真实 DeepSeek 调用, 非降级)
```

key 来源: ~/.hermes/.env (只读引用, 不回显; len=35) → export → llm_raw 可用。

## 2. 输入与推进 (真实对话, 无内部命令)

```
INPUT: 做一个简单的倒计时网页：页面中央显示秒数倒计时，到 0 停止并播放提示音，支持重新开始。

AI: 明白了，我先记录下你的需求：一个倒计时网页，中央显示秒数，到0停止并播放提示音，
    支持重新开始。请问倒计时的初始时长是固定值还是需要用户输入？
    ← 真模型语义追问 (deterministic 只问固定平台/登录模板, 绝不问"初始时长固定还是输入")

USER: 时长由用户输入，默认 60 秒。
AI: 好的，已记录：倒计时时长由用户输入，默认60秒。

USER: 整理成 PRD → PRD-b3a3744eab23 v1 (draft)
USER: 就按这个做 → PRD approved
USER: 生成计划 → PLAN-052b9a88 (tasks=5, LLM 拆解)
USER: 确认计划 → PLAN approved
STOP (未输入「开始做」, 按要求)
```

## 3. 证据

### conversations/{cid}.json (conv-391071f2a2e0, understanding_version=5)

| type | content | status |
|------|---------|--------|
| IDEA | 做一个简单的倒计时网页 | PROPOSED |
| REQUIREMENT | 页面中央显示秒数倒计时 | PROPOSED |
| REQUIREMENT | 倒计时到0停止并播放提示音 | PROPOSED |
| REQUIREMENT | 支持重新开始功能 | PROPOSED |
| REQUIREMENT | 倒计时时长由用户输入，默认60秒 | PROPOSED |

**超出 deterministic 范围的证据**: deterministic 规则只产出"运行平台/无需登录/
以后可以/就用X"类模板 (conversation_app 规则集), **绝无能力产出**
"到0停止并播放提示音""支持重新开始功能""时长由用户输入默认60秒" 这类
语义级 REQUIREMENT — 这些只能来自真 LLM 语义理解。

### PRD content (PRD-b3a3744eab23 v1, approved)

```
functional_requirements: ['页面中央显示秒数倒计时', '倒计时到0停止并播放提示音',
                          '支持重新开始功能', '倒计时时长由用户输入，默认60秒']
```

PRD 忠实反映 LLM 理解的 facts (来源 understanding_version=5)。

### 任务树 (task_trees/PLAN-052b9a88.json)

```
degraded: False | decomposer: llm | leaves: 5
- 创建计时器核心模块，管理倒计时的开始、暂停、重置与状态变更
- 将倒计时状态与UI元素绑定，实现每秒更新显示与到0停止逻辑
- 构建用户输入时长与重新开始按钮的界面交互逻辑，并接入计时器
- 添加提示音播放（到0时触发），并创建基础页面结构与倒计时显示样式
- 验证与交付
```

**LLM 拆解成功** (degraded=False): 叶描述是架构级拆解 (核心模块/UI绑定/交互/
提示音), 模板拆解只会产出 "实现功能: <原句>" 平铺 — 差异显著。

## 4. 判定: REAL

真实 LLM 理解链路全通:
1. llm_raw 冒烟 1 passed (真实 DeepSeek)
2. 对话中 AI 追问"初始时长固定还是输入" — 语义级澄清, 非模板
3. facts 含 4 条语义级 REQUIREMENT (deterministic 规则无法产出)
4. PRD 忠实反映 facts
5. LLM 拆解器产出架构级任务树 (degraded=False)

## 5. 与第 3 刀对比

| 维度 | 第 3 刀 (deterministic, 无 key) | 本刀 (REAL, 有 key) |
|------|-------------------------------|---------------------|
| 理解来源 | deterministic 规则 (conversation_app 规则集) | 真 DeepSeek 语义理解 |
| AI 追问 | 固定模板 (平台/登录等) | 语义级 ("初始时长固定还是输入?") |
| facts | 模板类 (运行平台/无需登录) | 丰富语义 ("到0停止播放提示音/重新开始/时长输入默认60") |
| PRD 丰富度 | 基础 | 完整反映用户语义 |
| 拆解器 | (第 3 刀未走 LLM) | LLM 拆解, degraded=False, 架构级叶 |

**结论**: 第 3 刀的环境偏差已消除 — 真实 LLM 理解 + LLM 拆解在真实 CLI 链路
验证通过。理解段不再受 deterministic 能力边界限制。

---
*报告文件: docs/audits/2026-09-09-s1-cut4-real-llm-understanding.md | 零代码改动 | 无 commit*
