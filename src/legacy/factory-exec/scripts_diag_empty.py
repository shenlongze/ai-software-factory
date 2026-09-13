"""诊断脚本 (只读): 真实调用 deepseek-v4-flash, 打印原始响应结构。

用途: 复现 BUG-MKP-001 空内容样本 — 确认是模型真返回空 vs 解析 bug vs 超时。
不修改任何生产代码; key 从 ~/.hermes/.env 进程内读取, 不打印明文。
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# 进程内注入 key (禁命令行明文)
env_path = Path.home() / ".hermes" / ".env"
if env_path.is_file():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

key = os.environ.get("DEEPSEEK_API_KEY", "")
assert key, "DEEPSEEK_API_KEY missing"
print(f"key loaded: {'yes' if key.startswith('sk-') else 'yes (non-sk prefix)'}, len={len(key)}")

sys.path.insert(0, "/Users/Shared/work/ai-software-factory/factory-exec")

import httpx  # noqa: E402

from exec.benchmark.samples import SAMPLES_BY_ID  # noqa: E402
from exec.developer import DeveloperAgent  # noqa: E402

BASE = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-v4-flash"

sample = SAMPLES_BY_ID["BUG-MKP-001"]
_agent = DeveloperAgent.__new__(DeveloperAgent)  # 仅用 build_prompt, 不需要 provider
from exec.developer import DEFAULT_CONVENTIONS as _DC  # noqa: E402

_agent._conventions = _DC  # type: ignore[attr-defined]
prompt = _agent.build_prompt(
    objective=sample.objective,
    project_context="建议先浏览以下路径 (沙箱已选择性复制, 其余项目文件不在沙箱内):\n- lib\n- pubspec.yaml",
    requirement=sample.requirement,
    sandbox_path="/tmp/benchmark-sbx",
)
print(f"\nprompt chars: {len(prompt)}")

body = {
    "model": MODEL,
    "max_tokens": 4096,
    "messages": [{"role": "user", "content": prompt}],
}
headers = {"Authorization": f"Bearer {key}", "content-type": "application/json"}

started = time.monotonic()
with httpx.Client(timeout=180.0) as client:
    resp = client.post(BASE, json=body, headers=headers)
latency = time.monotonic() - started
print(f"\nHTTP {resp.status_code} latency={latency:.1f}s")

data = resp.json()
if isinstance(data, dict) and data.get("choices"):
    msg = data["choices"][0].get("message", {})
    content = msg.get("content")
    print(f"finish_reason={data['choices'][0].get('finish_reason')!r}")
    print(f"content type={type(content).__name__} len={len(content) if content else 0}")
    print(f"content repr head: {repr(content)[:300]}")
    print(f"message keys: {list(msg.keys())}")
    if msg.get("reasoning_content") is not None:
        rc = msg["reasoning_content"]
        print(f"reasoning_content len={len(rc)} head: {repr(rc)[:200]}")
    print(f"usage: {json.dumps(data.get('usage'), ensure_ascii=False)}")
else:
    print(f"full body head: {json.dumps(data, ensure_ascii=False)[:500]}")
