#!/usr/bin/env python3
"""
Create or replace the `Whisky` class with Snowflake m-v1.5 embeddings.

Usage:
    python schema.py
Requires:
    - WEAVIATE_URL
    - WEAVIATE_API_KEY
"""
import os, weaviate, sys, json
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
            "vectorizeClassName": False,
        }
    },
    # Only a starter set; dynamic schema is still on, so extra props appear
    "properties": [
        {"name": "name",        "dataType": ["text"]},
        {"name": "tasteNotes",  "dataType": ["text[]"], "tokenization": "field"},
        {"name": "tasteText",   "dataType": ["text"]},
        {"name": "region",      "dataType": ["text"]},
    ],
}

if client.schema.contains(CLASS):
    client.schema.delete_class("Whisky")
    print("Replaced existing Whisky class")

client.schema.create_class(CLASS)
print("✅ Whisky class created with Snowflake embeddings")
