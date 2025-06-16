
# Whisky RAG Service

End‑to‑end Retrieval‑Augmented Generation stack for whisky discovery.

* **Weaviate Cloud** – vector + BM25 + rerank
* **LangServe** – FastAPI wrapper exposing `/chat/invoke` + `/chat/stream`
* **OpenAI GPT‑4o** – LLM with automatic prompt‑cache discount

---

## 1. Setup
```bash
cp .env.example .env     # edit keys
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python ingest.py "Whisky.de details - cleaned.csv"   # one‑time load
uvicorn app.main:app --host 0.0.0.0 --port 8080      # dev server
```

## 2. API
| Route | Method | Description |
|-------|--------|-------------|
| `/chat/invoke`  | POST | JSON in → JSON out |
| `/chat/stream`  | POST | Server‑Sent Events stream |

## 3. Deployment
```bash
docker compose up --build -d
```
