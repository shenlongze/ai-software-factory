# Phase 7 Implementation Plan — Project Understanding Layer

> 日期: 2026-08-06 | 状态: 待确认
> 冻结约束: Core 零修改 / 零已有测试破坏 / Extension 扩展 / LLM 不写死 (Provider 抽象)

## 1. 新增目录

```
factory-core/understanding/          (新 Extension 模块)
├── models.py        ProjectUnderstandingReport + StageDetection + ArtifactDetection + MissingAnalysis
├── analyzers/
│   ├── project_analyzer.py     项目基本信息 (类型/技术栈/规模/状态)
│   ├── document_analyzer.py    文档检测 (PRD/UI/架构/部署文档)
│   └── artifact_detector.py    产物检测 (代码/测试/构建配置/发布配置)
├── service.py       UnderstandingService (编排: 分析→识别→缺失→建议)
├── events.py        事件辅助
└── __init__.py
```

## 2. 数据模型 (按 Development Strategy 细化)

```python
# 阶段: 10 个可扩展 (注册化 STAGES 列表)
STAGES = [IDEA, RESEARCH, PRD, UI_DESIGN, ARCHITECTURE, DEVELOPMENT, TESTING, RELEASE, PRODUCTION, OPERATION]

class StageDetection(Pydantic):
    stage: str            # 来自 STAGES 注册表 (可扩展)
    confidence: float     # 0.0-1.0
    evidence: list[str]   # 证据列表

# Artifact: 7 类注册化 (ARTIFACT_DETECTORS 注册表, 可扩展)
# PRD / UI_DESIGN / ARCHITECTURE / SOURCE_CODE / TEST / DEPLOYMENT / OPERATION
class ArtifactDetection(Pydantic):
    artifact: str         # 注册表键
    present: bool
    detail: str

class MissingAnalysis(Pydantic):
    missing: list[str]
    present: list[str]

class NextAction(Pydantic):
    action: str           # 建议 (仅建议, 不自动执行)
    reason: str           # 理由
    risk: str             # 风险
    approval_required: bool  # 是否需人工批准

class ProjectUnderstandingReport(Pydantic):
    path: str
    basic_info: dict       # 类型/技术栈/规模/状态
    stage: StageDetection
    artifacts: list[ArtifactDetection]
    missing: MissingAnalysis
    next_actions: list[NextAction]
    generated_at: str
```

## 3. Event 设计 (经 EventLogger)

```
understanding.started       — 分析开始
understanding.completed     — 分析完成 (payload: path/stage/confidence/artifacts)
understanding.failed        — 分析失败
(可选) stage.detected / artifact.detected — 细粒度
EventType 枚举扩展 (ADR-0002 路径, 加成员不改表)
```

## 4. Core 边界检查

| 检查项 | 结论 |
|:-------|:-----|
| 修改 Core 模块? | ❌ 零修改 (只新建 understanding/) |
| 读 Core 数据? | ✅ 只读 (project/workspace 配置; git 可选经既有 GitClient) |
| 既有测试破坏? | ❌ 不触碰 (新增独立 tests/understanding/) |
| LLM 写死? | ❌ 规则分析 + Mock; 未来经 Provider 抽象 (Phase 8) |
| Approval Gate | 只设计接口 (report 中标注 required_approval 字段), 不实现 Web UI |

## 5. CLI (Extension 命令)

```
factory understand <path>          — 生成 Project Understanding Report
factory understand <path> --json   — 结构化输出
factory understand --stage <path>  — 仅阶段识别
```

## 6. Dashboard (可选, 17 视图)

```
Understanding View: 项目列表 + 阶段 + 置信度 + 缺失产物
(include_understanding 默认关, 零回归)
```

## 7. 测试计划 (新增 ≥80)

- 空项目 (空目录) → 阶段 IDEA/UNKNOWN + 全缺失
- 新项目 (仅 README) → PRD 阶段
- 已有代码项目 (src+tests) → DEVELOPMENT
- 文档完整项目 (PRD+UI+架构+部署) → RELEASE/PRODUCTION 边界
- 多项目 Workspace → 各自报告
- 阶段识别 (12 阶段各场景 + confidence)
- 缺失检测 (各产物组合)
- Event 记录 (started/completed/failed)
- CLI (文本/--json/--stage/退出码)
- 只读性 (分析不修改任何文件)

## 8. 完成标准

- pytest 全绿 (2159 + ≥80)
- 零 Core 修改 (git diff 验证)
- 冒烟: factory understand 真实项目 (markpad) → Report 合理
- ADR-0021 + README/roadmap 同步
