# Reality SSoT（当前代码真实状态）

> **自动生成，禁止手写。** 本目录下所有非 README 文件均由生成器产出。

## 定义

Reality SSoT = 仓库当前代码的**可验证真实状态**（不是设计意图，不是文档宣称）。
它是三层 SSoT 中优先级最高的一层（见 `../README.md` 引用顺序）。

## 数据来源

| 来源 | 内容 |
|------|------|
| `git ls-files` | 文件清单与路径 |
| `pytest --collect-only` | 测试清单与数量 |
| import 静态分析 | 模块依赖方向（是否违反铁律） |
| FastAPI `openapi.json` | API 契约 |
| `~/.factory` 扫描 | 运行时 store 与数据落点 |

## 生成命令（占位）

```
factory reality build
```

> 本阶段**不实装生成器**（下一阶段做），仅留约定。

## 自动生成约定

- 每个生成文件的首行必须是：
  ```
  <!-- AUTO-GENERATED: DO NOT EDIT -->
  ```
- 任何手写修改将在下次生成时被覆盖。
- 生成器缺失时，本目录保持为空（只有 README + .gitkeep）。
