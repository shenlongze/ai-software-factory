# AI Factory 目录重构 — 迁移计划 (供审批)

> 日期: 2026-08-31 | 状态: 待审批 (不执行, 直到批准)
> 备份: git tag `pre-restructure-20260831-165027` + tar (6.5MB clean / 725MB full)
> 回滚: `git checkout pre-restructure-20260831-165027` 或解压 tar

---

## 1. 目标 (为什么重构)

**现状问题**: UI 入口分散在 5+ 位置, 无统一目录:
```
factory-console/web/frontend/   ← WebUI (埋在 console 后端目录下)
desktop/                        ← Tauri 壳 (独立根目录)
factory_console/                ← 打包别名壳 (import 胶水)
dist/.../console_web            ← 打包副本
build/lib/web                   ← 构建缓存副本
```

**目标**: UI 统一收拢到 `ui/`, 后端保持不动 (方案 C, 本轮只动前端)。

## 2. 目标结构 (本轮)

```
ai-software-factory/
├── ui/                          ← 新增: 统一 UI 目录
│   ├── web/                     ← WebUI (从 factory-console/web/frontend 迁入)
│   │   ├── src/  dist/  package.json  vite.config.ts  tsconfig.json
│   │   └── ...
│   └── desktop/                 ← Tauri 壳 (从 desktop 迁入)
│       ├── src-tauri/  package.json  README.md
│       └── (ui symlink 指向 ../web/dist)
│
├── factory-console/             ← 后端 (不动)
├── factory-core/  factory-exec/  factory-org/   ← 不动
├── factory_console/             ← 打包别名 (不动, 后续单独规划)
├── tests/  docs/  pyproject.toml ← 不动
```

## 3. 迁移步骤 (每步独立可回滚)

### Step 1: 创建 ui/ 目录
```bash
mkdir -p ui
```

### Step 2: 迁移 WebUI
```bash
git mv factory-console/web/frontend ui/web
# 保留 factory-console/web/backend (后端 API 不动)
```

### Step 3: 迁移 desktop
```bash
git mv desktop ui/desktop
# 更新 desktop symlink: ui/desktop/ui → ../web/dist
```

### Step 4: 修复引用 (关键风险点)
需要 grep 并更新:
```
1. 后端静态服务路径:  fastapi_adapter create_app(static_dir=...) 指向 ui/web/dist
2. 构建脚本:          scripts/ 里 build 前端的路径
3. factory start:     cli_factory 找前端 dist 的路径
4. 测试引用:          vitest/tsconfig 相对路径
5. desktop runtime:   ui/desktop/src-tauri 的 frontendDist 指向
```

### Step 5: 验证
```
- 后端测试全量 (1117 passed)
- 前端 tsc + vitest (747/748)
- vite build PASS
- factory start → 5180 打开正常
- desktop (若构建) 正常
```

## 4. 影响面与风险

| 项 | 影响 | 风险 |
|----|------|------|
| import 路径 | 无 (后端不动) | 低 |
| pyproject 包映射 | 无 | 低 |
| 静态服务路径 | fastapi_adapter 1 处 | 中 (改错则 5180 白屏) |
| 构建脚本 | scripts/ 若干 | 中 |
| desktop symlink | 1 处 | 低 |
| 测试引用 | 相对路径 | 低 (测试在 frontend/src 内) |
| git 历史 | git mv 保留 | 低 |

## 5. 回滚方案
```
git checkout pre-restructure-20260831-165027  (整体回滚)
或单步: git mv 反操作
```

## 6. 审批点
- [ ] 方案 C (只收拢前端到 ui/) 批准
- [ ] Step 4 引用修复范围确认 (static_dir/scripts/desktop)
- [ ] 执行后跑全量验证

## 7. 后续规划 (本轮不做)
```
方案 A/B: 后端目录改名 (factory-console → console), 根治双目录 — 需单独评估
移动端: 未来加 ui/mobile
打包副本统一: dist/build 同步机制
```
