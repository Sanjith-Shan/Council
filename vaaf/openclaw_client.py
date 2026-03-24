"""OpenClaw gateway client for Council."""

import json
import os
from typing import AsyncGenerator

import httpx


class OpenClawClient:
    def __init__(self, gateway_url: str = None, gateway_token: str = None):
        self.gateway_url = gateway_url or os.getenv("OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18789")
        self.gateway_token = gateway_token or os.getenv("OPENCLAW_GATEWAY_TOKEN", "")
        self.api_url = f"{self.gateway_url}/v1/chat/completions"
        self._client = httpx.AsyncClient(timeout=120.0)

    @property
    def is_configured(self) -> bool:
        return bool(self.gateway_token)

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.gateway_token:
            headers["Authorization"] = f"Bearer {self.gateway_token}"
        return headers

    async def send_message(self, message: str, history: list[dict]) -> dict:
        messages = [*(history or []), {"role": "user", "content": message}]
        payload = {
            "model": "openclaw:main",
            "messages": messages,
            "stream": False,
        }

        try:
            response = await self._client.post(self.api_url, headers=self._headers(), json=payload)
            response.raise_for_status()
            data = response.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return {"text": text, "error": None}
        except httpx.ConnectError:
            return {"text": "", "error": "Cannot connect to OpenClaw gateway"}
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:300] if exc.response is not None else "HTTP error"
            return {"text": "", "error": f"Gateway HTTP {exc.response.status_code}: {detail}"}
        except Exception as exc:
            return {"text": "", "error": f"Unexpected error: {str(exc)[:300]}"}

    async def send_message_stream(self, message: str, history: list[dict] = None) -> AsyncGenerator[str, None]:
        """Streaming helper for later tasks."""
        messages = [*((history or [])), {"role": "user", "content": message}]
        payload = {
            "model": "openclaw:main",
            "messages": messages,
            "stream": True,
        }
        try:
            async with self._client.stream("POST", self.api_url, headers=self._headers(), json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        delta = data["choices"][0].get("delta", {})
                        text = delta.get("content", "")
                        if text:
                            yield text
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
        except Exception as exc:
            yield f"\n\n[stream error: {str(exc)[:100]}]"

    async def check_health(self) -> dict:
        try:
            response = await self._client.get(f"{self.gateway_url}/health", headers=self._headers(), timeout=5.0)
            if response.is_success:
                return {"connected": True, "error": None}
            return {"connected": False, "error": f"Health check failed: HTTP {response.status_code}"}
        except Exception as exc:
            return {"connected": False, "error": str(exc)[:300]}

    async def close(self):
        await self._client.aclose()
