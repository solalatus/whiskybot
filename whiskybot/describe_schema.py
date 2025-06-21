#!/usr/bin/env python3
"""
describe_whisky_schema.py

Connects to your Weaviate instance, inspects the Whisky class schema,
and emits a single prompt-string listing every field and its data type
(and description, if defined).
"""

import os
from dotenv import load_dotenv
import weaviate

def main():
    load_dotenv()

    # load connection info
    url = os.getenv("WEAVIATE_URL")
    key = os.getenv("WEAVIATE_API_KEY")
    if not url or not key:
        print("ERROR: WEAVIATE_URL and WEAVIATE_API_KEY must be set in your environment.")
        return

    # connect
    client = weaviate.Client(
        url,
        auth_client_secret=weaviate.AuthApiKey(key),
        additional_headers={
            "X-Weaviate-Cluster-Url": url.replace("https://", "")
        },
    )

    # fetch schema for class Whisky
    try:
        schema = client.schema.get(class_name="Whisky")
    except weaviate.exceptions.UnexpectedStatusCodeException:
        print("ERROR: Whisky class not found in schema.")
        return

    props = schema.get("properties", [])
    if not props:
        print("No properties found on Whisky class.")
        return

    # build prompt string
    lines = []
    for p in props:
        name = p["name"]
        dtypes = p.get("dataType", [])
        dtype_str = ", ".join(dtypes) if dtypes else "unknown"
        desc = None#p.get("description", "").strip()
        if desc:
            lines.append(f"- {name} ({dtype_str}): {desc}")
        else:
            lines.append(f"- {name} ({dtype_str})")

    prompt = (
        "\"\"\"Whisky class schema — available fields and their types:\n"
        + "\n".join(lines)
    ) +"\"\"\""

    # output single prompt string
    print(prompt)


if __name__ == "__main__":
    main()
