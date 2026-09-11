# 03 — RECOMMENDED TARGET STRUCTURE (2026-09-06)

## 推荐方案: 保持单发行版拓扑 + 演进归位 (不引入 apps/ 现在)

### 判断 (Q7: apps/ vs clients/)
**apps/ > clients/** (若未来归位)。理由:
- 当前各"入口"是**可部署产品入口** (web build + desktop app + CLI 命令),
  不是"OS 的 API 客户端库"
- backend console (factory-console) 是共享内核 + 自带 web 入口, 它不属于
  client 层
- "clients/" 语义暗示存在多个消费方共用一套 client SDK — 当前不成立

### 何时建顶层 apps/
**不现在**。触发条件 (任一):
- Desktop 真正复用 Web 作为主界面 (Tauri 内嵌同源 build) → desktop 归
  apps/desktop + web 前端抽出 apps/web (前后端拆部署)
- Mobile (Flutter) 落地 → apps/mobile
- 第二独立富客户端出现

### 当前真实推荐 (渐进, 非大爆炸)
保留现有拓扑 (已正确表达 单内核+多入口 依赖方向), 只修结构债:
```
ai-software-factory/
├── factory-core/ factory-console/ factory-exec/ factory-org/  # 单 Python 发行版
│   └── factory-console/web/{backend,frontend}                  # API + Web client (同发行版)
├── factory-runtime/          # 独立发行版 (backend 生命周期 CLI)
├── desktop/                  # Tauri 壳 (src-tauri + src/ui + 构建产物忽略)
├── bin/factory               # CLI 薄入口
├── docs/ tests/ scripts/
└── (清理) $SMOKE_ROOT/, 顶层 exec/checkpoints.json
```

### 未来目标拓扑 (第二客户端触发时, 参考)
```
ai-software-factory/
├── apps/
│   ├── web/        (自 factory-console/web/frontend 迁出, 拆部署后)
│   ├── desktop/    (自 desktop/ 迁入)
│   └── mobile/     (Flutter, 未来)
├── server/         (= 现 factory-console backend+domain 内核, 若前后端拆)
├── factory-core/ factory-exec/ factory-org/ factory-runtime/
├── cli/            (若 CLI 独立分发; 现 bin/factory 薄包装已够)
└── packages/contracts (共享 API 类型 — 前端 types.ts 已内联, 拆 client 时抽)
```

### 边界铁律 (现状已满足, 保持)
- apps/* / frontend → HTTP → backend API → domain (禁直写 store)
- desktop Rust 禁 spawn Core/uvicorn (走 factory-runtime)
- CLI = 薄参数层 → console services (禁第二业务后端)
- 所有 client 零 Production Truth 写入
