# Robust CSV → Weaviate loader that works with Sandbox/Serverless clusters requiring X‑Weaviate‑Cluster‑Url
# Usage: python ingest.py <csv_path>

import os, sys, uuid, math, ast, pandas as pd, weaviate
from dotenv import load_dotenv

load_dotenv()

URL = os.getenv("WEAVIATE_URL")
KEY = os.getenv("WEAVIATE_API_KEY")
if not URL or not KEY or KEY.startswith("xxxx"):
    sys.exit("❌ WEAVIATE_URL or WEAVIATE_API_KEY missing; aborting.")

if len(sys.argv) != 2:
    sys.exit("Usage: python ingest.py <csv_path>")
CSV = sys.argv[1]
if not os.path.exists(CSV):
    sys.exit(f"❌ CSV not found: {CSV}")

df = pd.read_csv(CSV)
cols_lower = {c.lower(): c for c in df.columns}

# detect taste column
list_col = next((cols_lower[c] for c in ("taste_list",) if c in cols_lower), None)
profile_col = next((cols_lower[c] for c in ("taste_profile", "taste profile") if c in cols_lower), None)
if not list_col and not profile_col:
    sys.exit("❌ No Taste_list or Taste_profile column found")

def ensure_list(val):
    if isinstance(val, list):
        return val
    if isinstance(val, str) and val.strip().startswith("["):
        try:
            return ast.literal_eval(val)
        except Exception:
            pass
    return [t.strip() for t in str(val).split("\n") if t.strip()]

if list_col:
    df["taste_list"] = df[list_col].apply(ensure_list)
else:
    df["taste_list"] = (
        df[profile_col].astype(str).str.split(r"\s*\n\s*")
        .apply(lambda lst: [t.strip() for t in lst if t.strip()])
    )

df["taste_sentence"] = df["taste_list"].apply(", ".join)

# helper columns
def lookup(col):
    return cols_lower.get(col)

name_c, reg_c, alc_c, price_c, score_c = map(lookup, [
    "name", "region", "alcohol_content_percent", "action_price", "average_score"])

def safe(v):
    if v is None or pd.isna(v):
        return None
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v

# ---- client with required header -------------------------------------------
extra_headers = {"X-Weaviate-Cluster-Url": URL.replace("https://", "")}
client = weaviate.Client(
    URL,
    auth_client_secret=weaviate.AuthApiKey(KEY),
    additional_headers=extra_headers,
)

# batch callback aborts on first error

def on_error(res):
    if not res:
        return
    if isinstance(res, list):
        for r in res:
            if r.get("result", {}).get("errors"):
                print("❌ Batch failed:", r["result"]["errors"])
                sys.exit(1)
    elif isinstance(res, dict) and res.get("errors"):
        print("❌ Batch failed:", res["errors"])
        sys.exit(1)

client.batch.configure(batch_size=200, callback=on_error)

with client.batch as batch:
    for row in df.itertuples():
        obj = {
            "name": safe(getattr(row, name_c)) if name_c else f"Whisky-{row.Index}",
            "tasteNotes": row.taste_list,
            "tasteText": row.taste_sentence,
            "region": safe(getattr(row, reg_c)) if reg_c else None,
            "alcohol_pct": safe(getattr(row, alc_c)) if alc_c else None,
            "price_eur": safe(getattr(row, price_c)) if price_c else None,
            "score": safe(getattr(row, score_c)) if score_c else None,
        }
        batch.add_data_object(obj, "Whisky", uuid.uuid4())
print(f"✅ Ingested {len(df)} whiskies from {CSV}")
