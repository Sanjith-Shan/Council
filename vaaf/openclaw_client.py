import asyncio
import json
import os


class OpenClawClient:
    def __init__(self, gateway_token=None, gateway_url=None, agent_id="main"):
        self.gateway_token = gateway_token or os.getenv("OPENCLAW_GATEWAY_TOKEN", "")
        self.gateway_url = gateway_url or os.getenv("OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18789")
        self.agent_id = agent_id

    @property
    def is_configured(self):
        return bool(self.gateway_token)

    async def send_message(self, message, history=None):
        try:
            process = await asyncio.create_subprocess_exec(
                "openclaw", "agent",
                "--agent", self.agent_id,
                "--message", message,
                "--json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "OPENCLAW_GATEWAY_TOKEN": self.gateway_token},
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)
            output = stdout.decode("utf-8", errors="replace").strip()
            if not output:
                return {"text": "", "error": "No output from OpenClaw"}
            try:
                data = json.loads(output)
            except json.JSONDecodeError:
                idx = output.find("{")
                if idx >= 0:
                    try:
                        data = json.loads(output[idx:])
                    except json.JSONDecodeError:
                        return {"text": output[:500], "error": None}
                else:
                    return {"text": output[:2000], "error": None}
            payloads = data.get("payloads") or data.get("result", {}).get("payloads") or []
            text = ""
            for p in payloads:
                if p.get("text"):
                    text += p["text"] + chr(10)
            text = text.strip()
            if not text:
                text = data.get("text", json.dumps(data, indent=2)[:2000])
            return {"text": text, "error": None}
        except asyncio.TimeoutError:
            return {"text": "", "error": "Timed out after 5 minutes"}
        except FileNotFoundError:
            return {"text": "", "error": "openclaw command not found"}
        except Exception as e:
            return {"text": "", "error": str(e)[:200]}

    async def send_message_stream(self, message, history=None):
        result = await self.send_message(message, history)
        if result.get("error"):
            yield "[Error: " + result["error"] + "]"
        elif result.get("text"):
            yield result["text"]

    async def check_health(self):
        try:
            process = await asyncio.create_subprocess_exec(
                "openclaw", "gateway", "status",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=10)
            output = stdout.decode("utf-8", errors="replace")
            running = "running" in output.lower()
            return {"connected": running, "gateway_url": self.gateway_url, "error": None if running else "Not running"}
        except Exception as e:
            return {"connected": False, "gateway_url": self.gateway_url, "error": str(e)[:100]}

    async def close(self):
        pass
