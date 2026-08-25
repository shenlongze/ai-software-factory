# AI Factory — HTTP API 规范 v1（项目统一标准）

> 日期: 2026-08-26 · 状态: Founder 批准（"所有接口统一配置、格式"）· 生效: 全量收敛
> 用途: 所有 /api/* 端点必须遵守——响应包络 / 错误包络 / 命名 / 状态码 / 一致性强制。
> 契约测试: tests/console/test_s10_125_api_standard.py（断言全部端点合规）

---

## 1. 响应包络

| 场景 | 格式 | HTTP |
|---|---|---|
| **集合** | `{"items": [...], "count": N}` | 200 |
| **单个对象** | 直接返回对象 | 200 |
| **创建** | 直接返回对象 | 201 |
| **删除** | `{"deleted": true, "id": "..."}` | 200 |

集合必须是 `{items, count}`，禁止裸数组。

## 2. 错误包络（统一，带错误码）

```json
{
  "error": {
    "code": "E7404",
    "message": "人类可读的一句话",
    "detail": "附加信息(可选)",
    "suggestion": "建议下一步(可选)"
  }
}
```

- 错误码域: **E7xxx = HTTP API**（E4xxx CLI / E6xxx session / E5xxx 脚本）
- code 缺省 = `E7{status}`（E7400/E7404/E7409/E7422/E7500）
- 禁止裸 `{"detail": "..."}`（历史格式已收敛）
- 实现: FastAPI 全局异常处理器（HTTPException + 校验 + 500），一处覆盖全部端点

## 3. 命名规范

| 项 | 规则 |
|---|---|
| URL | 资源复数 + kebab-case: `/api/projects/{id}/backlog/task/{task_id}` |
| JSON 字段 | **snake_case**（project_id / server_url / tech_stack） |
| 时间 | ISO 8601 UTC（YYYY-MM-DDTHH:MM:SSZ） |

## 4. 状态码语义

| 码 | 语义 |
|---|---|
| 200 | 读取/更新成功 |
| 201 | 创建成功 |
| 400 | 参数错误（空值/非法值） |
| 404 | 资源不存在 |
| 409 | 冲突/状态非法（状态机、运行中） |
| 422 | 请求体校验失败 |
| 500 | 未预期异常（失败安全，不泄露堆栈） |

## 5. 一致性强制

- **契约测试** test_s10_125_api_standard.py:
  - 遍历注册表全部 /api 端点 → 集合响应断言 `{items, count}`
  - 触发 404/400/409 → 断言 error 包络 + code E7xxx
  - 命名断言（snake_case 抽查 + URL kebab-case）
- 新增端点必须过规范（开发纪律: 集合用 ok_list() 助手, 错误交给全局处理器）

## 6. 错误码表（E7xxx, 详见 docs/error-codes.md）

| 模块 | CODE | 消息 | 建议下一步 |
|---|---|---|---|
| http_api | E7400 | 参数错误 | 见 detail |
| http_api | E7404 | 资源不存在 | 检查 id/路径 |
| http_api | E7409 | 冲突/状态非法 | 见 detail |
| http_api | E7422 | 请求体校验失败 | 见 detail |
| http_api | E7500 | 服务器内部错误 | 查看日志 |
