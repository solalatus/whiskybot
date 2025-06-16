
"""Create or update the `Whisky` class to use Snowflake m‑v1.5 embeddings.

Usage:
    python schema.py
Requires:
    - WEAVIATE_URL
    - WEAVIATE_API_KEY
"""
import os, weaviate, json, sys
from dotenv import load_dotenv

load_dotenv()

client = weaviate.Client(
    os.getenv("WEAVIATE_URL"),
    auth_client_secret=weaviate.AuthApiKey(os.getenv("WEAVIATE_API_KEY")),
)

CLASS = {
    "class": "Whisky",
    "description": "Whisky product catalogue",
    "vectorizer": "text2vec-weaviate",
    "moduleConfig": {
        "text2vec-weaviate": {
            "model": "Snowflake/snowflake-arctic-embed-m-v1.5",
            # Uncomment below if you want 256‑dim truncation instead of 768
            # "dimensions": 256
        }
    },
    "properties": [
        {"name": "name",        "dataType": ["text"]},
        {"name": "tasteNotes",  "dataType": ["text[]"], "tokenization": "field"},
        {"name": "tasteText",   "dataType": ["text"]},
        {"name": "region",      "dataType": ["text"]},
        {"name": "alcohol_pct", "dataType": ["number"], "moduleConfig": {"skip": True}},
        {"name": "price_eur",   "dataType": ["number"], "moduleConfig": {"skip": True}},
        {"name": "score",       "dataType": ["number"], "moduleConfig": {"skip": True}},
    ],
}

# Replace existing or create new
if client.schema.contains(CLASS):
    client.schema.delete_class("Whisky")
    print("ℹ️  Replaced existing Whisky class")

client.schema.create_class(CLASS)
print("✅ Whisky class created with Snowflake m‑v1.5 embeddings")
