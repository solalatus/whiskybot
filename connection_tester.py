# Simple Weaviate connection tester that works with client v3.

import os, sys, weaviate
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("WEAVIATE_URL")
key = os.getenv("WEAVIATE_API_KEY")

if not url or not key:
    sys.exit("❌ WEAVIATE_URL or WEAVIATE_API_KEY missing. Source your .env")

try:
    client = weaviate.Client(url, auth_client_secret=weaviate.AuthApiKey(key))

    # meta handling that works across API variants
    try:
        meta = client.get_meta()
        if isinstance(meta, dict):
            version = meta.get("version", {}).get("weaviateVersion", "unknown")
        else:
            version = str(meta)
    except Exception:
        version = "unknown"

    ready = client.is_ready()  # simple health check
    print("✅ Connected to Weaviate", version, "| ready:" , ready)
    classes = [c["class"] for c in client.schema.get()["classes"]]
    print("Classes:", classes or "none")
except Exception as e:
    print("❌ Connection failed:", e)
