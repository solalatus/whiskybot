import os
import json
import uuid
import httpx
import chainlit as cl

API_ROOT = os.getenv("LANGSERVE_URL", "http://localhost:8080/chat")
INVOKE_EP = f"{API_ROOT}/invoke"


def _unwrap(o):
    """Peel off nested 'output' keys until the payload is not a dict."""
    while isinstance(o, dict) and "output" in o:
        o = o["output"]
    return o


async def call_langserve(msg: str, session_id: str) -> str:
    """
    Send the user message to LangServe, first with session info, then the
    legacy shapes for backward-compat. Always return a string for Chainlit.
    """
    async with httpx.AsyncClient(timeout=60) as client:
        payloads = [
            {  # session-aware
                "input": {"input": msg},
                "config": {"configurable": {"session_id": session_id}},
            },
            {"input": msg},                # legacy 1
            {"input": {"input": msg}},     # legacy 2
        ]
        for p in payloads:
            r = await client.post(INVOKE_EP, json=p)
            if r.status_code == 200:
                try:
                    out = _unwrap(r.json())
                except ValueError:
                    out = r.text
                if not isinstance(out, str):
                    out = json.dumps(out, ensure_ascii=False, indent=2)
                return out
        r.raise_for_status()  # surface last error


# ----------------------------------------------------------------
# Chainlit hooks

@cl.on_chat_start
async def start():
    cl.user_session.set("session_id", str(uuid.uuid4()))
    await cl.Message("Ask me anything about whisky!").send()


@cl.on_message
async def handle(message: cl.Message):
    try:
        session_id = cl.user_session.get("session_id")
        answer = await call_langserve(message.content, session_id)
        await cl.Message(answer).send()
    except httpx.HTTPStatusError as e:
        await cl.Message(
            f"LangServe returned {e.response.status_code}\n{e.response.text}"
        ).send()
    except Exception as e:
        await cl.Message(f"Unexpected error: {e}").send()
