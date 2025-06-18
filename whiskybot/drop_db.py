#!/usr/bin/env python3
"""
Drop *all* data and schema from a Weaviate instance.

Running the ingest script a second time appends data, which leads to duplicates.
Use this helper to clear the database before a fresh import.

Usage
-----
    python drop_db.py

Environment variables
---------------------
- ``WEAVIATE_URL``   – e.g. ``https://example.weaviate.network``
- ``WEAVIATE_API_KEY`` – API key for the target cluster
"""

import os
import sys
import textwrap

import weaviate
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Environment ---------------------------------------------------------------
# ---------------------------------------------------------------------------

load_dotenv()

URL = os.getenv("WEAVIATE_URL")
KEY = os.getenv("WEAVIATE_API_KEY")
if not URL or not KEY or KEY.startswith("xxxx"):
    sys.exit("WEAVIATE_URL or WEAVIATE_API_KEY missing; aborting.")

# ---------------------------------------------------------------------------
# Confirmation --------------------------------------------------------------
# ---------------------------------------------------------------------------

WARNING = textwrap.dedent(
    f"""
    You are about to delete ALL data (both schema and objects) from:

        {URL}

    This action cannot be undone. Type DELETE (in capitals) to proceed: """
)

try:
    proceed = input(WARNING).strip()
except EOFError:
    # In non‑interactive environments the script exits unless --yes is provided
    sys.exit("No confirmation received; aborting.")

if proceed != "DELETE":
    sys.exit("Confirmation failed; aborting.")

# ---------------------------------------------------------------------------
# Client setup --------------------------------------------------------------
# ---------------------------------------------------------------------------

extra_headers = {"X-Weaviate-Cluster-Url": URL.replace("https://", "")}
client = weaviate.Client(
    URL,
    auth_client_secret=weaviate.AuthApiKey(KEY),
    additional_headers=extra_headers,
)

# ---------------------------------------------------------------------------
# Drop schema ---------------------------------------------------------------
# ---------------------------------------------------------------------------

print("Deleting schema …", end="", flush=True)
try:
    client.schema.delete_all()
except AttributeError:
    # Older weaviate-client versions: delete class by class
    schema = client.schema.get()
    for cls in schema.get("classes", []):
        client.schema.delete_class(cls["class"])
print(" done.")

print("Database emptied. You may now re‑ingest fresh data.")
