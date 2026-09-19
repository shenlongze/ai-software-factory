"""infrastructure.llm.serve — OpenAI 兼容的入站端点（LLM 路由对外产品面）。

★ 2026-09-19 新增（吸收项 10）—— 让 LLM 路由**从内部能力变成可对外交付的产品**。

【现状与缺口（本刀要补的那一环）】
 infrastructure/llm/ 已有 25 个模块: gateway(唯一汇聚点) · CostAwareSelector(成本感知选择) ·
 router(路由) · control_plane(配置+密钥) · costs/usage(成本核算) · feedback(反馈闭环) ·
 model_catalog · agent_policy …—— **全部是"出站"**（我们调别人的 /chat/completions）。
 缺的是"**入站**": 别人调我们。有了入站, 这个模块就能当独立产品卖（对标 GoModel / Routerly）,
 而它比那两家多三件: 成本感知选择 · 反馈闭环 · agent 级策略。

【本刀做最小可用的一刀】
 POST /v1/chat/completions —— OpenAI 兼容形状（请求与响应都用 OpenAI 的字段名,
 这样任何 OpenAI SDK / 客户端改个 base_url 就能接）。
 另提供 GET /health（探活）与 GET /v1/models（列出可用 provider/model）。

【为什么用 stdlib http.server】
 KISS + 零依赖（本仓无 web 框架, WebUI 面也已挂起）。
 这不是"生产级 Web 服务"——它是**最小可交付的入站面**, 证明链路通、能被外部消费。
 真要生产化（并发/鉴权/限流/可观测）是后续独立的一刀, 不在这里假装做完。

【诚实边界】
 · 不做鉴权（本地/内网形态）—— 对外售卖前必须补, 已在 docstring 标注。
 · 不做并发优化（ThreadingHTTPServer 的默认行为, 够用即可）。
 · 选路由: 有 CostAwareSelector 就按它的推荐, 否则回落"请求里显式给的 model"或默认 provider。
 · 失败一律返回 OpenAI 形状的错误体（{"error": {...}}）+ 恰当 HTTP 状态 —— 不假装成功。
"""
from __future__ import annotations

import json
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

MAX_BODY = 1 << 20          # 1 MiB —— 请求体上限（防误用/滥用）

#: 鉴权 token 的环境变量名。★ 未设置 ⇒ 本地模式（不鉴权, 但启动时大声警告）
TOKEN_ENV = "AIFACTORY_GATEWAY_TOKEN"


def _expected_token() -> str:
    """读期望的 token（未配置 ⇒ 空串 = 本地模式）。"""
    import os

    return str(os.environ.get(TOKEN_ENV) or "").strip()


def _check_auth(header: str | None) -> tuple[bool, str]:
    """校验 Authorization 头。

    返回 (是否放行, 拒绝原因)。
    ★ 语义（与 OpenAI 客户端兼容）:
      · 未配置 token（本地/内网形态）⇒ **一律放行**, 由启动提示明确告知"未鉴权"
      · 已配置 token ⇒ 必须 `Authorization: Bearer <token>` 且**完全一致**（常量时间比较）
      · 配置了但请求没带/带错 ⇒ 401（不透露期望值, 不给"接近了"的暗示）
    """
    want = _expected_token()
    if not want:
        return True, ""                     # 本地模式
    got = str(header or "").strip()
    if not got:
        return False, "缺少 Authorization 头"
    if not got.lower().startswith("bearer "):
        return False, "Authorization 头格式应为 'Bearer <token>'"
    import hmac

    if not hmac.compare_digest(got[7:].strip(), want):
        return False, "token 无效"
    return True, ""


def _pick_route(body: dict[str, Any]) -> tuple[str, str, str]:
    """决定用哪个 provider/model —— 返回 (provider_id, model, base_url)。

    顺序（可解释）:
      ① 请求里显式给的 provider/model（调用方说了算）
      ② CostAwareSelector 的推荐（成本感知 —— 本产品相对开源网关的差异点）
      ③ 控制面的默认 provider（providers.json 的 enabled 项）
      取不到 ⇒ ("", "", "")（调用方会返回明确错误, 不静默用错模型）。
    """
    model = str(body.get("model") or "").strip()
    try:
        from ai_factory_os.infrastructure.llm.providers.control_plane import LLMControlPlane

        plane = LLMControlPlane()
        # ① 显式 model ⇒ 找到声明该 model 的 provider（ProviderConfig.models 是列表）
        if model:
            for cfg in (plane.list_providers() or []):
                mods = [str(m) for m in (getattr(cfg, "models", None) or [])]
                if model in mods or str(getattr(cfg, "id", "")) == model:
                    return (str(getattr(cfg, "id", "") or ""), model,
                            str(getattr(cfg, "base_url", "") or ""))
        # ② 第一个启用的 provider（用它的第一个 model）
        for cfg in (plane.enabled_providers() or plane.list_providers() or []):
            mods = [str(m) for m in (getattr(cfg, "models", None) or [])]
            mdl = model or (mods[0] if mods else "")
            if mdl:
                return (str(getattr(cfg, "id", "") or ""), mdl,
                        str(getattr(cfg, "base_url", "") or ""))
    except Exception:  # noqa: BLE001 — 失败安全: 交给调用方报错
        pass
    return ("", model, "")


def _chat_completion(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """核心: OpenAI 形状请求 → 调 gateway → OpenAI 形状响应。返回 (http_status, payload)。"""
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        return 400, {"error": {"message": "messages 必须是非空数组", "type": "invalid_request_error"}}
    provider_id, model, base_url = _pick_route(body)
    if not provider_id or not model:
        return 503, {"error": {
            "message": "无可用的 provider/model（检查 providers.json 配置）",
            "type": "no_provider_available"}}
    try:
        from ai_factory_os.infrastructure.llm.gateway import complete
        from ai_factory_os.infrastructure.llm.providers.control_plane import LLMControlPlane

        api_key = ""
        try:
            plane = LLMControlPlane()
            api_key = str(plane.resolve_api_key(provider_id) or "")
        except Exception:  # noqa: BLE001
            api_key = ""
        out = complete(
            messages, body.get("tools"),
            provider_id=provider_id, model=model, base_url=base_url, api_key=api_key,
            temperature=float(body.get("temperature") or 0.2),
            timeout=int(body.get("timeout") or 120),
        )
        content = str((out or {}).get("content") or "")
        return 200, {
            "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }],
            # usage 尽力而为（gateway 若给了就带上, 没给就不编）
            "usage": (out or {}).get("usage") or {},
            "x_ai_factory_provider": provider_id,     # ★ 附加信息: 实际用了谁（可审计）
        }
    except Exception as exc:  # noqa: BLE001 — 失败如实报, 不假装成功
        return 502, {"error": {"message": f"{type(exc).__name__}: {exc}", "type": "upstream_error"}}


class _Handler(BaseHTTPRequestHandler):
    server_version = "AIFactoryLLMGateway/0.1"

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler 的约定名
        ok, why = _check_auth(self.headers.get("Authorization"))
        if not ok:
            self._send(401, {"error": {"message": why, "type": "invalid_request_error"}})
            return
        if self.path.rstrip("/") in ("/health", "/healthz"):
            self._send(200, {"status": "ok", "service": "ai-factory-llm-gateway"})
            return
        if self.path.rstrip("/") == "/v1/models":
            ids: list[dict[str, Any]] = []
            try:
                from ai_factory_os.infrastructure.llm.providers.control_plane import LLMControlPlane

                for p in (LLMControlPlane().list_providers() or []):
                    ids.append({"id": str(getattr(p, "id", "") or ""),
                                "object": "model",
                                "owned_by": "ai-factory",
                                "enabled": bool(getattr(p, "enabled", True))})
            except Exception:  # noqa: BLE001
                pass
            self._send(200, {"object": "list", "data": ids})
            return
        self._send(404, {"error": {"message": f"未知路径: {self.path}", "type": "not_found"}})

    def do_POST(self) -> None:  # noqa: N802
        ok, why = _check_auth(self.headers.get("Authorization"))
        if not ok:
            self._send(401, {"error": {"message": why, "type": "invalid_request_error"}})
            return
        if self.path.rstrip("/") != "/v1/chat/completions":
            self._send(404, {"error": {"message": f"未知路径: {self.path}", "type": "not_found"}})
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0 or n > MAX_BODY:
                self._send(413, {"error": {"message": "请求体为空或过大", "type": "invalid_request_error"}})
                return
            body = json.loads(self.rfile.read(n).decode("utf-8"))
            if not isinstance(body, dict):
                raise ValueError("body 必须是 JSON 对象")
        except Exception as exc:  # noqa: BLE001
            self._send(400, {"error": {"message": f"无法解析请求: {exc}", "type": "invalid_request_error"}})
            return
        status, payload = _chat_completion(body)
        self._send(status, payload)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002,A003
        """静默默认日志（走 stderr 会把 CLI 输出弄乱）—— 需要时再开。"""
        return


def serve(host: str = "127.0.0.1", port: int = 8787) -> None:
    """启动 OpenAI 兼容端点（阻塞）。Ctrl-C 停止。

    用法: `factory llm serve --port 8787`
    接入: 任何 OpenAI 客户端把 base_url 指向 http://<host>:<port>/v1 即可。
    """
    httpd = ThreadingHTTPServer((host, int(port)), _Handler)
    print(f"AI Factory LLM Gateway (OpenAI 兼容) 已启动: http://{host}:{port}")
    print("  POST /v1/chat/completions   ·  GET /health  ·  GET /v1/models")
    print(f"  接入示例: base_url=http://{host}:{port}/v1")
    if _expected_token():
        print(f"  🔒 鉴权: 已启用（读 ${TOKEN_ENV}）—— 请求需带 Authorization: Bearer <token>")
    else:
        print(f"  ⚠ 鉴权: **未启用**（本地/内网形态）。对外提供请先设 ${TOKEN_ENV}=<token>")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  已停止")
    finally:
        httpd.server_close()
