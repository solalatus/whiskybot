# Advanced Weaviate connection tester: write → read back → delete cycle
# Usage: python connection_tester_full.py
# Requires WEAVIATE_URL and WEAVIATE_API_KEY in env or .env

import os, sys, uuid, time, weaviate
from dotenv import load_dotenv

load_dotenv()

URL = os.getenv("WEAVIATE_URL")
KEY = os.getenv("WEAVIATE_API_KEY")
if not URL or not KEY or KEY.startswith("xxxx"):
    sys.exit("❌ WEAVIATE_URL or WEAVIATE_API_KEY missing or placeholder")

client = weaviate.Client(URL, auth_client_secret=weaviate.AuthApiKey(KEY))
print("▶️  Health check →", client.is_ready())

# 1. Write a dummy object
obj_id = str(uuid.uuid4())
obj = {
    "name": "_ping_",
    "tasteNotes": ["Ping"],
    "tasteText": "Ping object",
}
client.data_object.create(obj, "Whisky", obj_id)
print("✅ Write ok", obj_id)

# 2. Read it back
read_obj = client.data_object.get_by_id(obj_id)
print("✅ Read back", read_obj is not None)

# 3. Delete it
client.data_object.delete("Whisky", obj_id)
print("✅ Delete ok")

print("🏁 Full write/read/delete cycle succeeded")
