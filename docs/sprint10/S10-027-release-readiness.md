# S10-027 Task 5 — Release Readiness Check

> 日期:2026-08-14 | Sprint: S10-027 Hardening | 模拟真实用户 + 隔离环境实测
> 流程:clone → setup.sh → factory init → factory doctor → factory start → factory demo

---

## 1. 模拟路径实测(隔离 HOME)

| 步骤 | 实测结果 | 人工/自动 |
|---|---|---|
| 1. git clone | ⚠️ **私有仓库**(需 GitHub 权限) | 人工(权限) |
| 2. bash scripts/setup.sh | ✅ 幂等:venv + pip install -e . + 可选 npm + init 冒烟 | 自动 |
| 3. ./bin/factory init | ✅ 实测(S10-026-E):workspace 创建 + providers.json 引导(交互/非交互) | 半自动(选 provider) |
| 4. ./bin/factory doctor | ✅ 实测:5 维诊断 PASS/WARN/FAIL + 建议 | 自动 |
| 5. ./bin/factory start | ✅ 实测:环境预检 → uvicorn 8011 + 前端 5180 + 浏览器 | 自动 |
| 6. ./bin/factory demo | ✅ 实测:隔离 ~/.factory-demo init/status/reset | 自动 |

## 2. 需要人工的步骤

| 步骤 | 人工内容 | 能否自动化 |
|---|---|---|
| clone | GitHub 权限(私有仓库) | 否(分发问题) |
| setup | 无 | ✅ |
| init | ① 选 provider ② **配置 API key 环境变量**(export DEEPSEEK_API_KEY=...) | ② 不能(安全:key 不自动写入) |
| doctor | 无(只读) | ✅ |
| start | 无 | ✅ |
| demo | 无 | ✅ |

**结论:唯一必须人工 = 配置 API key**(安全设计,key 绝不自动落盘)。

## 3. 应该自动化的缺口

| # | 缺口 | 严重度 | 建议 |
|---|---|---|---|
| G1 | **仓库私有** → 外部用户无法 clone | 高 | 转公开 / release tarball / pipx |
| G2 | **setup.sh 依赖 Node**(无 node 跳过 npm → start 前端不可用) | 中 | 确认 dist 随 release 分发;或 setup 明确提示 |
| G3 | **README 首次指引脱节**(旧 7 页描述) | 中 | 更新为 clone→setup→init→doctor→start 四步 |
| G4 | **LLM key 配置说明不足** | 中 | init 输出明确"如何配置 key"(export 示例) |
| G5 | npm install 无重试/超时 | 低 | setup 加重试提示 |
| G6 | demo 完整流程需 key | 低 | demo status 提示"需配置 key 才真实执行" |
| G7 | 无版本号/更新机制 | 低 | factory version + CHANGELOG |

## 4. 是否可给陌生用户运行?

**基本可以,但有条件:**

| 条件 | 状态 |
|---|---|
| 陌生用户能安装 | ❌ 私有仓库阻塞(需先解决 G1) |
| 安装后能启动 | ✅ setup.sh + init + start 全自动 |
| 能看 UI/流程 | ✅ demo 隔离 workspace 就绪 |
| 能真实执行 LLM | ⚠️ 需用户自配 key(文档化即可) |
| 出问题能自查 | ✅ doctor 诊断 + audit |

**判定:功能上可给陌生用户(除 key 外全自动);分发上不行(私有仓库)。**

## 5. Release 就绪度评分

| 维度 | 评分 | 说明 |
|---|---|---|
| 安装自动化 | 9/10 | setup.sh 幂等 |
| 运行自动化 | 8/10 | start 全自动;前端 node 依赖是前提 |
| 首次体验 | 7/10 | demo 隔离;完整执行需 key |
| 分发渠道 | 3/10 | **私有仓库是最大阻塞** |
| 文档 | 5/10 | README 脱节 |
| 陌生人可运行 | 6/10 | 功能 OK,分发/文档待补 |

**总分:6.3/10 — 功能就绪;发布前置 = 解决分发(G1)+ 文档(G3/G4)。**

## 6. Release 前必做清单

```
P0 (阻塞发布):
  [ ] 仓库转公开 / 打 release tarball + 发布说明 (G1)
  [ ] README 更新: clone→setup→init→doctor→start 四步 + LLM key 配置说明 (G3/G4)
  [ ] 确认前端 dist 构建产物随 release 分发 (G2)

P1 (发布质量):
  [ ] factory version 命令 + CHANGELOG (G7)
  [ ] demo status 提示 key 需求 (G6)
  [ ] setup.sh npm 重试 (G5)
```

---

> 检查完毕 | 含隔离环境实测 | 判定:功能可发布,分发渠道是唯一硬阻塞
