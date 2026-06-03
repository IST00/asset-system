"""Story service — call DeepSeek chat completions for the Keke H5.

The original Tencent SCF function lived here:
  back/.../上线物料包/backend/index.py
We keep the same wire protocol (POST chat/completions, temperature 0.85,
max_tokens 6000) and the same translation of upstream error codes into
business-friendly Chinese messages so the H5 prompt stays unchanged.

Why urllib instead of httpx/requests: avoids adding a runtime dependency
and matches the original SCF code path. The slow 30-60s call is bounded
by `DEEPSEEK_TIMEOUT_SECONDS` (default 120).
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Any

from flask import current_app

from app.common import BusinessException
from app.services._prompts.keke_story import build_prompt


def _post_deepseek(*, api_url: str, api_key: str, prompt: str, timeout: int) -> dict[str, Any]:
    body = json.dumps(
        {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.85,
            "max_tokens": 6000,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        api_url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        payload = resp.read().decode("utf-8")
    return json.loads(payload)  # type: ignore[no-any-return]


def generate(*, keyword: str) -> dict[str, str]:
    """Return `{"content": "..."}` for the H5 to parse client-side."""

    keyword = (keyword or "").strip()
    if not keyword:
        raise BusinessException("缺少关键词")
    if len(keyword) > 100:
        raise BusinessException("关键词过长")

    api_key = current_app.config.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise BusinessException("故事生成服务未配置，请联系管理员")

    api_url = current_app.config.get(
        "DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions"
    )
    timeout = int(current_app.config.get("DEEPSEEK_TIMEOUT_SECONDS", 120))

    prompt = build_prompt(keyword)

    try:
        data = _post_deepseek(api_url=api_url, api_key=api_key, prompt=prompt, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise BusinessException("API Key 无效，请联系管理员") from e
        if e.code == 402:
            raise BusinessException("账户余额不足，请联系管理员充值") from e
        raise BusinessException(f"DeepSeek 请求失败（{e.code}）") from e
    except (urllib.error.URLError, socket.timeout) as e:
        raise BusinessException("网络错误，请稍后重试") from e

    choices = data.get("choices") or []
    if not choices:
        raise BusinessException("生成结果为空，请稍后重试")
    content = (choices[0].get("message") or {}).get("content") or ""
    if not content.strip():
        raise BusinessException("生成结果为空，请稍后重试")

    return {"content": content}
