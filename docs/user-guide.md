# 用户手册 — 如何使用 AI Software Factory（当前真实版本）

> 日期: 2026-08-08 | 真实命令版 (实测验证) | 对应代码: HEAD=469bba1, pytest 5521
> 审计依据: docs/audit/operating-capability-audit-v2.md

## 0. 这是什么

```
AI Software Factory 当前 = 半自动软件工厂 (单任务可自动执行, 完整生产需人工配合)
能力边界: 组织管理 ✅ / 任务生命周期 ✅ / 单任务 LLM 执行 ✅ (DeepSeek v4-pro)
         多阶段协作 ❌ / 发布部署 ❌ / UI 无 (全部 CLI)
```

## 1. 安装/启动

```bash
# 前置: Python 3.12+, git, DeepSeek API key
cd /Users/Shared/work/ai-software-factory
python3 -m venv .venv && .venv/bin/pip install -e factory-core -e factory-org -e factory-exec
export PYTHONPATH=factory-core:factory-org:factory-exec

# 配置 LLM key (DeepSeek):
export OPENAI_API_KEY='sk-...'   # DeepSeek key (兼容端点)

# 初始化工厂 (数据根默认 ~/.factory):
.venv/bin/python -m cli.main --root ~/myfactory init
```

## 2. 创建公司

```bash
# 创建软件公司 (自动建部门 + 5 角色: CEO/Product Manager/Architect/Developer/QA)
.venv/bin/python -m org.cli --root ~/myfactory company create \
  --template software_company --name "我的软件公司"
# → 输出 company_id (记下来, 如 C-b84d508f)

# 查看:
.venv/bin/python -m org.cli --root ~/myfactory company list
```

## 3. 创建项目/团队

```bash
# 雇佣开发者 (注意: 角色名精确匹配模板, 大小写敏感)
.venv/bin/python -m org.cli --root ~/myfactory employee hire \
  --company C-xxx --name "开发者1" --role Developer
# → 输出 employee_id (E-xxx)

# 查看员工:
.venv/bin/python -m org.cli --root ~/myfactory employee list --company C-xxx
```

## 4. 提交需求

```bash
# 创建任务 (需求/缺陷):
.venv/bin/python -m cli.main --root ~/myfactory task create \
  --title "修复 sum_list 漏第一个元素" --type bug
# → 输出 task_id (T-xxx)

# 产品链路 (可选, 从想法到任务):
.venv/bin/python -m cli.main --root ~/myfactory product idea --text "记账APP" 
.venv/bin/python -m cli.main --root ~/myfactory product analyze --idea I-xxx
.venv/bin/python -m cli.main --root ~/myfactory product approve --idea I-xxx
```

## 5. 执行 (AI 干活 — 核心)

```bash
# 让 Developer 员工真实执行 (调用 DeepSeek v4-pro):
.venv/bin/python -m exec.cli --root ~/myfactory run \
  --task T-xxx \
  --employee E-xxx \
  --project-dir /path/to/your/project \
  --objective "修复 sum_list: 遍历从索引 0 开始" \
  --requirement "Python 函数, 遍历整个列表求和"

# 内部发生: 沙箱副本 → v4-pro 生成修改 → 验证 → patch+report+test_result
# 源项目零修改 (沙箱外铁律); 输出 execution_id (EX-xxx)
```

## 6. 查看执行/结果

```bash
# 执行结果:
.venv/bin/python -m exec.cli --root ~/myfactory status --id EX-xxx

# 审批应用 patch (把修改真正应用到项目):
.venv/bin/python -m exec.cli --root ~/myfactory approval approve --execution EX-xxx

# 全貌 (Dashboard/事件/指标):
.venv/bin/python -m cli.main --root ~/myfactory dashboard
.venv/bin/python -m cli.main --root ~/myfactory event logs
.venv/bin/python -m cli.main --root ~/myfactory metrics
```

## 7. 如何让它开发软件 (实战路径)

```
场景: 修复现有代码 Bug (今天能做的)
  1. task create --type bug "描述问题"
  2. exec run (如上) → AI 生成 patch + 报告
  3. 审阅 report → approval approve → patch 应用到项目
  4. 人工验证 (AI 沙箱内已测, 但复杂逻辑需人工确认)

场景: 新功能开发 (部分能做)
  1. product idea → analyze → approve (需求确认)
  2. task create --type feature
  3. exec run --objective "实现..." → 检查产物
  4. 注意: 多文件/复杂功能成功率未验证 (9 样本 Benchmark 未跑)

场景: 全新软件 (今天不能全自动)
  ❌ 前端+后端+数据库+测试+发布 全链 — 需人工大量参与
  只能: 逐任务拆解 → 每任务 exec run → 人工拼装
```

## 8. 如何让它修复自身

```bash
# 今天: 半自动 (AI 生成修复 patch, 人工批准)
1. 发现 AI Software Factory 的 Bug:
   .venv/bin/python -m cli.main --root ~/myfactory task create --title "修复 factory-core xxx bug" --type bug
2. 执行 (项目目录 = factory 自身):
   .venv/bin/python -m exec.cli --root ~/myfactory run \
     --task T-xxx --employee E-xxx \
     --project-dir /Users/Shared/work/ai-software-factory \
     --objective "修复 xxx"
3. 审批 apply → 跑 pytest 验证 → 人工确认后 commit
# 限制: 无法自动发现 bug / 无法自动 apply / 无法自动提交
```

## 9. 已知限制（重要）

```
1. 无 UI — 全部命令行 (Console 是只读管理台, 非工作台)
2. 只有 Developer 角色可执行 (PM/UI/Architect/Tester/DevOps = 规划)
3. 复杂任务成功率未验证 (只验 1 个简单 Python 任务)
4. 角色名大小写敏感 (Developer 非 developer)
5. employee hire --capabilities 疑似未生效 (实测 caps=0)
6. apply 需人工审批 (半自动)
7. 无 Build/Package/部署能力
8. 仅 DeepSeek LLM (v4-pro)
```

## 10. 典型 10 分钟上手

```bash
export PYTHONPATH=factory-core:factory-org:factory-exec
F=~/myfactory; .venv/bin/python -m cli.main --root $F init
CID=$(.venv/bin/python -m org.cli --root $F company create --template software_company --name Demo | grep -o 'C-[a-z0-9]*')
EID=$(.venv/bin/python -m org.cli --root $F employee hire --company $CID --name D1 --role Developer | grep -o 'E-[a-z0-9]*')
TID=$(.venv/bin/python -m cli.main --root $F task create --title "demo task" --type bug | grep -o 'T-[0-9]*')
echo "公司=$CID 员工=$EID 任务=$TID"
# 然后 exec run (需真实项目目录 + objective)
```
