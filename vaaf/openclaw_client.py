"""
Council — OpenClaw Gateway Client
----------------------------------
Connects Council's chat interface to the running OpenClaw gateway
via its OpenAI-compatible HTTP API at /v1/chat/completions.

This replaces the standalone GPT-4o-mini agent so that when you
type in Council's chat, you're talking to your actual OpenClaw agent
with all its tools, skills, memory, and connected channels.
"""

import os
import json
import httpx
from typing import AsyncGenerator


class OpenClawClient:
    def __init__(
        self,
        gateway_url: str = None,
        gateway_token: str = None,
        agent_id: str = "main",
    ):
        self.gateway_url = (
            gateway_url
            or os.getenv("OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18789")
        )
        self.gateway_token = (
            gateway_token
            or os.getenv("OPENCLAW_GATEWAY_TOKEN", "")
        )
        self.agent_id = agent_id
        self.api_url = f"{self.gateway_url}/v1/chat/completions"

        self._client = httpx.AsyncClient(timeout=120.0)

    @property
    def is_configured(self) -> bool:
        return bool(self.gateway_token)

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.gateway_token:
            h["Authorization"] = f"Bearer {self.gateway_token}"
        return h

    async def send_message(self, message: str, history: list[dict] = None) -> dict:
        """Send a message to OpenClaw and get the response.

        Returns dict with:
            text: str — the agent's text response
            tool_calls: list — any tool calls the agent made
            raw: dict — the full API response
        """
        messages = []
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": message})

        payload = {
            "model": f"openclaw:{self.agent_id}",
            "messages": messages,
            "stream": False,
        }

        try:
            response = await self._client.post(
                self.api_url,
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            # Extract the response
            choice = data.get("choices", [{}])[0]
            msg = choice.get("message", {})

            return {
                "text": msg.get("content", ""),
                "tool_calls": msg.get("tool_calls", []),
                "raw": data,
                "error": None,
            }

        except httpx.ConnectError:
            return {
                "text": "",
                "tool_calls": [],
                "raw": {},
                "error": "Cannot connect to OpenClaw gateway. Is it running? Check: openclaw gateway status",
            }
        except httpx.HTTPStatusError as e:
            error_body = ""
            try:
                error_body = e.response.json()
            except Exception:
                error_body = e.response.text[:200]
            return {
                "text": "",
                "tool_calls": [],
                "raw": {},
                "error": f"OpenClaw returned {e.response.status_code}: {error_body}",
            }
        except Exception as e:
            return {
                "text": "",
                "tool_calls": [],
                "raw": {},
                "error": f"Unexpected error: {str(e)[:200]}",
            }

    async def send_message_stream(self, message: str, history: list[dict] = None) -> AsyncGenerator[str, None]:
        """Stream a message response from OpenClaw token by token.

        Yields text chunks as they arrive via SSE.
        """
        messages = []
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": message})

        payload = {
            "model": f"openclaw:{self.agent_id}",
            "messages": messages,
            "stream": True,
        }

        try:
            async with self._client.stream(
                "POST",
                self.api_url,
                headers=self._headers(),
                json=payload,
            ) as response:
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
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
        except Exception as e:
            yield f"\n\n[Error streaming from OpenClaw: {str(e)[:100]}]"

    async def check_health(self) -> dict:
        """Check if the OpenClaw gateway is reachable and authenticated."""
        try:
            response = await self._client.get(
                f"{self.gateway_url}/health",
                headers=self._headers(),
                timeout=5.0,
            )
            return {
                "connected": True,
                "status": response.status_code,
                "gateway_url": self.gateway_url,
            }
        except httpx.ConnectError:
            return {
                "connected": False,
                "error": "Cannot connect to gateway",
                "gateway_url": self.gateway_url,
            }
        except Exception as e:
            return {
                "connected": False,
                "error": str(e)[:100],
                "gateway_url": self.gateway_url,
            }

    async def close(self):
        await self._client.aclose()
