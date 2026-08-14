# Development — 源码构建 / 测试 / 贡献

> 面向开发者与贡献者的技术文档入口。用户安装与使用请回到 [README](../README.md)。

## 源码构建

```bash
git clone https://github.com/shenlongze/ai-software-factory.git
cd ai-software-factory
bash scripts/setup.sh        # venv + editable install + 冒烟验证 (幂等, 可重复执行)
```

手动方式 (等价):

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

## 测试

```bash
.venv/bin/python -m pytest -q                          # 全量: 基线 8148 passed, 0 failed
.venv/bin/python -m pytest <files> -q --no-header      # 定向测试
```

## 架构导读 (技术读者)

- 架构与依赖规则: [docs/architecture/](./architecture/)
- 生命周期 12 阶段模型: [docs/lifecycle-model.md](./lifecycle-model.md)
- 愿景与四条核心理念: [docs/vision.md](./vision.md)
- 应用场景: [docs/use-cases.md](./use-cases.md) · 状态与规模: [docs/status.md](./status.md)

## 贡献指南

欢迎贡献, 三条铁律:

1. **不修改 Core 行为** — Core 是冻结的通用原语, 新能力一律走 Extension 声明式注册
2. **测试先行, 只增不减** — 每个变更必须带测试; 全量跑通, 基线用例数只增不减
3. **依赖单向向下** — 禁止反向依赖与循环 import

流程: Fork → 分支 (`feature/<phase>-<描述>`) → 变更 + 测试 → PR。
设计决策先写 ADR (`docs/adr/`), 新模型先补设计文档 (`docs/`), 再写代码。
