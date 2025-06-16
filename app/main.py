
from fastapi import FastAPI
from langserve import add_routes
from app.agent import agent

app = FastAPI(title="Whisky RAG Service")
add_routes(app, agent, path="/chat")
