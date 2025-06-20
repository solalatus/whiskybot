from fastapi import FastAPI
from langserve import add_routes
from app.agent import agent

app = FastAPI(title="Whisky RAG Service")

@app.get("/healthz")
async def healthz():
    """
    Health check endpoint for ALB:
    Returns HTTP 200 with a simple JSON payload.
    """
    return {"status": "ok"}

# RAG chat endpoint
add_routes(app, agent, path="/chat")
