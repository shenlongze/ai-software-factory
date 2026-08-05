# ADR-0013 — Phase 5A: Production Example Layer (MarkPad)

> 日期: 2026-08-06 | 状态: Accepted

## 背景

Core 稳定后接入真实项目。第一个 Example: MarkPad (examples/markpad/)。不改 factory-core 核心逻辑。

## 决策

### 1. Example 层 = 声明式配置
examples/markpad/ 五个文件 (project/agents/skills/workflows.yaml + README) 定义项目接入；factory-core/project/ 提供只读加载器 (discover/load, FACTORY_EXAMPLES_DIR 可覆盖)。

### 2. 新增依赖 PyYAML
仓库无 yaml 解析；PyYAML 6.0.3 (纯 wheel ~170KB) 轻量, 声明进 pyproject dependencies。

### 3. CLI project 命令只读
factory project list/show 读配置 + 发 project.viewed 事件, 不改任何状态。

### 4. 步骤 role/skill 与 agents.yaml 严格匹配
(ADR-0008 语义) 保证 workflow run --auto 可跑通；内置 workflow 定义骨架复用 (feature/bug-fix/release)。

## 验证

- pytest 1237 全绿 (1203 + 34)
- 真实链路: MP-BUG-004 bug-fix 4 步 COMPLETED (echo runtime)
- 真实 Hermes: reproduce 步骤 SUCCESS (EX-001); 开放 instruction 超时 → adapter 正确转 FAILED (失败处理验证)
- Validation PASS + Dashboard 汇总正常
