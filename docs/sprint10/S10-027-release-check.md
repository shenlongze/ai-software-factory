# S10-027 Task F — Release Readiness Checklist

> 日期:2026-08-14 | Sprint: S10-027 Hardening | 模拟新用户安装路径
> 对象:Mac/Linux 新用户第一次安装运行

---

## 1. 模拟安装路径(clone → setup → init → doctor → start → demo)

```
Step 1: git clone https://github.com/shenlongze/ai-software-factory.git
Step 2: bash scripts/setup.sh
Step 3: ./bin/factory init
Step 4: ./bin/factory doctor
Step 5: ./bin/factory start
Step 6: ./bin/factory demo
```

## 2. 逐步检查

### Step 1: git clone ✅
- 仓库私有(需用户有 GitHub 权限)
- **缺口**:私有仓库外部用户不可 clone。发布需:① 转公开 ② 或提供 release tarball ③ 或 pipx 安装包

### Step 2: bash scripts/setup.sh ⚠️
已验证(脚本 4100 字节,幂等):
- ✅ Python 3.12+ 检测(自动选 python3.13/3.12/3.11)
- ✅ venv 创建 + pip install -e .
- ✅ 可选 npm install(node 存在时)
- ✅ --check 就绪验证 + init 冒烟(setup 末尾调 factory init 验证)
- **缺口**:
  1. **依赖 Node.js ≥18**(前端);无 node → 跳过 npm(factory 核心可用,但 start 前端不可用)
  2. npm install 可能慢/失败(网络)无重试
  3. setup 不配置 LLM key(正确——init 引导)

### Step 3: ./bin/factory init ✅(S10-026-E 已实现)
- ✅ 环境检测 → workspace 创建 → providers.json 引导(交互/非交互)
- ✅ 只写 api_key_ref 引用,无明文 key
- ⚠️ **人工步骤**:用户需自行配置 API key 环境变量(如 export DEEPSEEK_API_KEY=...)——init 只提示不代劳(正确设计,但文档需说明)

### Step 4: ./bin/factory doctor ✅(S10-026-A 已实现)
- ✅ 5 维诊断:环境/Provider/Model/Runtime/Router
- ✅ 清晰 PASS/WARN/FAIL + 处理建议
- ✅ exit code 0/1/2

### Step 5: ./bin/factory start ⚠️
- ✅ 环境/依赖预检 → 后端 uvicorn → 前端(vite dev 或 dist 托管)→ 浏览器
- ✅ 端口预检/幂等/健康检查
- **缺口**:
  1. 前端依赖:node_modules 存在(dist 托管时也应可用;但 dist 是否随 repo 提交?**需确认**——若 dist 不入库,新用户仍需 npm build)
  2. LLM key 未配置时 start 成功但执行会 FAILED(提示在 doctor,start 不强制)

### Step 6: ./bin/factory demo ✅(S10-026-F 已实现)
- ✅ 隔离 ~/.factory-demo,init/status/reset
- ✅ providers/models 种子 + 示例项目
- ⚠️ demo 完整流程(Idea→Artifact)需要 LLM key 才走真实执行;无 key 只展示 UI/流程

## 3. 缺口清单(按严重度)

| # | 缺口 | 严重度 | 影响 | 建议 |
|---|---|---|---|---|
| G1 | 仓库私有,外部用户无法 clone | **高** | 无法分发给新用户 | 发布时转公开 / release tarball / pipx |
| G2 | 前端 dist 是否随仓库分发未确认 | **中** | 无 node 用户 start 前端可能不可用 | 确认 dist 入库或 release 包含构建产物 |
| G3 | LLM key 配置是人工步骤(无自动检测引导) | 中 | 新用户执行 FAILED 需自己排查 | init 输出明确"如何配置 key"文档化 |
| G4 | npm install 无重试/超时处理 | 低 | 弱网用户安装失败 | setup.sh 加重试提示 |
| G5 | demo 完整流程需 key | 低 | 无 key 只能看 UI | demo status 提示"需配置 key 才能真实执行" |
| G6 | 无 release 版本号/更新机制 | 低 | 用户无法知道版本 | 后续 release Sprint |
| G7 | README 首次运行指引仍是旧 7 页描述 | 中 | 文档与实际脱节 | README 更新(clone→setup→init→doctor→start) |

## 4. 需要人工的步骤(总结)

| 步骤 | 人工内容 | 是否可自动化 |
|---|---|---|
| clone | GitHub 权限/认证 | 否(外部) |
| setup | 无(脚本自动) | ✅ 全自动 |
| init | 选择 provider + 配置 API key 环境变量 | 半自动(选择可自动,key 必须人工) |
| doctor | 无(只读诊断) | ✅ 全自动 |
| start | 无(自动起服务) | ✅ 全自动 |
| demo | 无(自动创建隔离) | ✅ 全自动 |

**结论:唯一必须人工的是 "配置 API key"**(安全设计,key 绝不自动写入)。

## 5. Release 就绪度评分

| 维度 | 评分 | 说明 |
|---|---|---|
| 安装自动化 | 9/10 | setup.sh 幂等 + init 引导 |
| 运行自动化 | 8/10 | start 全自动,前端依赖 node 是前提 |
| 首次体验 | 7/10 | demo 隔离,但完整流程需 key |
| 分发渠道 | 3/10 | **私有仓库是最大缺口** |
| 文档 | 5/10 | README 脱节待更新 |

**总分:6.4/10 — 功能就绪,分发/文档待补**

## 6. Release 前必做清单(建议)

1. [ ] 仓库转公开 / 或打 release tarball + 发布说明
2. [ ] 确认前端 dist 构建产物随 release 分发
3. [ ] README 更新为新 4 步(clone→setup→init→start)+ LLM key 配置说明
4. [ ] demo status 提示 key 需求
5. [ ] (可选)版本号 + CHANGELOG

---

> 检查完毕 | 只读(基于现有脚本/命令实测)
