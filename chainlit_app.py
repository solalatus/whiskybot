import os
import json
import httpx
import chainlit as cl

API_ROOT = os.getenv("LANGSERVE_URL", "http://localhost:8080/chat")
INVOKE_EP = f"{API_ROOT}/invoke"


def _unwrap(o):
    """
    Recursively unwrap {"output": ...} layers produced by LangServe
    until the payload is no longer a dict with a single 'output' key.
    """
    while isinstance(o, dict) and set(o) == {"output"}:
        o = o["output"]
    return o


async def call_langserve(msg: str) -> str:
    async with httpx.AsyncClient(timeout=60) as client:
        for payload in ({"input": msg}, {"input": {"input": msg}}):
            r = await client.post(INVOKE_EP, json=payload)
            if r.status_code == 200:
                try:
                    data = r.json()
                    out = _unwrap(data.get("output", data))
                except ValueError:
                    out = r.text  # plain-text fallback

                # Ensure the GUI always receives a string
                if not isinstance(out, str):
                    out = json.dumps(out, ensure_ascii=False, indent=2)
                return out
        r.raise_for_status()  # surface the last error


@cl.on_chat_start
async def start():
    await cl.Message("👋 Ask me anything about whisky!").send()


@cl.on_message
async def handle(message: cl.Message):
    try:
        answer = await call_langserve(message.content)
        await cl.Message(answer).send()
    except httpx.HTTPStatusError as e:
        await cl.Message(
            f"❌ LangServe returned {e.response.status_code}\n{e.response.text}"
        ).send()
    except Exception as e:
        await cl.Message(f"❌ Unexpected error: {e}").send()
