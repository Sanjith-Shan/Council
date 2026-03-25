"""OpenClaw gateway client for Council."""

import json
import os
from typing import Any, AsyncGenerator, Sequence

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
            raw_body = response.text
            try:
                data = self._load_json_block(raw_body)
            except ValueError as exc:
                snippet = raw_body.strip().splitlines()
                prefix = " ".join(snippet[:1])[:160]
                return {"text": "", "error": f"Gateway response error: {exc}. {prefix}"}

            text = self._extract_agent_text(data)
            return {"text": text, "error": None}
        except httpx.ConnectError:
            return {"text": "", "error": "Cannot connect to OpenClaw gateway"}
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:300] if exc.response is not None else "HTTP error"
            return {"text": "", "error": f"Gateway HTTP {exc.response.status_code}: {detail}"}
        except Exception as exc:
            return {"text": "", "error": f"Unexpected error: {str(exc)[:300]}"}

    def _load_json_block(self, raw_body: str) -> Any:
        if not raw_body:
            raise ValueError("empty response")
        start = raw_body.find("{")
        end = raw_body.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("missing JSON payload")
        snippet = raw_body[start:end + 1]
        return json.loads(snippet)

    def _extract_agent_text(self, data: Any) -> str:
        text = self._extract_payload_text(data)
        if text:
            return text
        text = self._extract_choice_text(data)
        if text:
            return text
        if isinstance(data, dict):
            fallback = data.get("text")
            if isinstance(fallback, str):
                return fallback.strip()
        return ""

    def _extract_payload_text(self, data: Any) -> str:
        payloads = self._find_payloads(data)
        if not payloads:
            return ""
        texts: list[str] = []
        for payload in payloads:
            if isinstance(payload, dict):
                text_value = payload.get("text")
                if isinstance(text_value, str):
                    stripped = text_value.strip()
                    if stripped:
                        texts.append(stripped)
        return "\n\n".join(texts).strip()

    def _find_payloads(self, node: Any) -> Sequence[dict] | None:
        if isinstance(node, dict):
            payloads = node.get("payloads")
            if isinstance(payloads, list):
                return payloads
            for key in ("result", "data"):
                candidate = self._find_payloads(node.get(key))
                if candidate:
                    return candidate
        elif isinstance(node, list):
            for item in node:
                candidate = self._find_payloads(item)
                if candidate:
                    return candidate
        return None

    def _extract_choice_text(self, data: Any) -> str:
        if not isinstance(data, dict):
            return ""
        choices = data.get("choices")
        if not isinstance(choices, list):
            return ""
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip()
        return ""

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
