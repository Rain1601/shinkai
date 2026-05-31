from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from typing import Any

from pydantic import BaseModel


class DeepSeekError(RuntimeError):
    pass


class DeepSeekUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class DeepSeekResult(BaseModel):
    content: str
    usage: DeepSeekUsage = DeepSeekUsage()


class DeepSeekClient:
    """Small OpenAI-compatible DeepSeek chat client using stdlib HTTP.

    The key must come from runtime environment/config. Do not store it in repo
    files or pass it through command lines that may be logged.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        timeout_seconds: float = 45.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def chat_json(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: int = 1800,
    ) -> dict[str, Any]:
        result = await self.chat(
            system=system,
            user=user,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        try:
            parsed = json.loads(result.content)
        except json.JSONDecodeError as exc:
            preview = result.content[:240]
            raise DeepSeekError(f"DeepSeek returned non-JSON content: {preview}") from exc
        if not isinstance(parsed, dict):
            raise DeepSeekError("DeepSeek JSON response must be an object")
        parsed["_usage"] = result.usage.model_dump()
        return parsed

    async def chat(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: int = 1800,
        response_format: dict[str, str] | None = None,
    ) -> DeepSeekResult:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            payload["response_format"] = response_format

        return await asyncio.to_thread(self._post_chat_completions, payload)

    def _post_chat_completions(self, payload: dict[str, Any]) -> DeepSeekResult:
        url = f"{self.base_url}/chat/completions"
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise DeepSeekError(f"DeepSeek HTTP {exc.code}: {detail[:300]}") from exc
        except urllib.error.URLError as exc:
            raise DeepSeekError(f"DeepSeek request failed: {exc.reason}") from exc

        data = json.loads(raw)
        choices = data.get("choices") or []
        if not choices:
            raise DeepSeekError("DeepSeek response contained no choices")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if not isinstance(content, str):
            raise DeepSeekError("DeepSeek response content missing")
        usage = data.get("usage") or {}
        return DeepSeekResult(
            content=content,
            usage=DeepSeekUsage(
                input_tokens=int(usage.get("prompt_tokens") or 0),
                output_tokens=int(usage.get("completion_tokens") or 0),
            ),
        )
