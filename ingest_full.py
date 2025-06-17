#!/usr/bin/env python3
"""
CSV → Weaviate loader (atomic *tasteNotes* tokens).

Key change (Option A)
---------------------
* `taste_list` is now **exploded** into individual flavour words so that
  `ContainsAny ['peat']` matches the Ardmore example and similar rows.
  Newlines and commas are treated as separators; tokens are stored *lower‑case*
  to make case‑sensitive filters simpler.

Prerequisite: the `Whisky` class already exists with a vectoriser (see schema.py).

Usage
-----
    python ingest_full.py <csv_path>
"""

import ast
import math
import os
import re
import sys
import uuid
from typing import Any, Dict, Optional, List

import pandas as pd
import weaviate
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Environment ----------------------------------------------------------------
# ---------------------------------------------------------------------------

load_dotenv()

URL = os.getenv("WEAVIATE_URL")
KEY = os.getenv("WEAVIATE_API_KEY")
if not URL or not KEY or KEY.startswith("xxxx"):
    sys.exit("WEAVIATE_URL or WEAVIATE_API_KEY missing; aborting.")

if len(sys.argv) != 2:
    sys.exit("Usage: python ingest_full.py <csv_path>")

CSV = sys.argv[1]
if not os.path.exists(CSV):
    sys.exit(f"CSV not found: {CSV}")

# ---------------------------------------------------------------------------
# Weaviate client ------------------------------------------------------------
# ---------------------------------------------------------------------------

extra_headers = {"X-Weaviate-Cluster-Url": URL.replace("https://", "")}
client = weaviate.Client(
    URL,
    auth_client_secret=weaviate.AuthApiKey(KEY),
    additional_headers=extra_headers,
)

# ---------------------------------------------------------------------------
# Verify Whisky class --------------------------------------------------------
# ---------------------------------------------------------------------------

try:
    whisky_cls = client.schema.get("Whisky")
except weaviate.exceptions.UnexpectedStatusCodeException:
    sys.exit(
        "Whisky class not found. Run schema.py first to create it with an "
        "embedding vectoriser."
    )

if whisky_cls.get("vectorizer", "none").lower() in {"", "none"}:
    sys.exit("Whisky class has no vectoriser. Re‑create it with schema.py.")

# ---------------------------------------------------------------------------
# Load data ------------------------------------------------------------------
# ---------------------------------------------------------------------------

df = pd.read_csv(CSV)
cols_lower = {c.lower(): c for c in df.columns}

# ---------------------------------------------------------------------------
# Helper functions -----------------------------------------------------------
# ---------------------------------------------------------------------------


def lookup(*alts: str) -> Optional[str]:
    for alt in alts:
        c = alt.lower()
        if c in cols_lower:
            return cols_lower[c]
    return None


def ensure_list(val: Any) -> List[str]:
    """Return *val* as a list (best‑effort parsing)."""
    if isinstance(val, list):
        return val
    if isinstance(val, str) and val.strip().startswith("["):
        try:
            return ast.literal_eval(val)
        except Exception:
            pass
    return [t.strip() for t in str(val).split("\n") if t.strip()]


TOKEN_SPLIT_RE = re.compile(r"[\s,;]+")

def explode_tokens(lst: List[str]) -> List[str]:
    """Split list elements on newline/comma and lowercase them."""
    out: List[str] = []
    for item in lst:
        parts = TOKEN_SPLIT_RE.split(item)
        out.extend(p.strip().lower() for p in parts if p.strip())
    return out


def safe(v: Any):
    if v is None or pd.isna(v):
        return None
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


def parse_int(v: Any):
    v = safe(v)
    if v is None:
        return None
    try:
        return int(float(v))
    except Exception:
        return None


def parse_bool(v: Any):
    if v is None or pd.isna(v):
        return None
    s = str(v).strip().lower()
    if s in {"yes", "y", "true", "t", "1"}:
        return True
    if s in {"no", "n", "false", "f", "0"}:
        return False
    return None


def parse_volume_ml(v: Any):
    v = safe(v)
    if v is None:
        return None
    m = re.search(r"[\d.]+", str(v))
    if not m:
        return None
    num = float(m.group())
    s = str(v).lower()
    if "cl" in s and num <= 100:
        return int(num * 10)
    if "l" in s and "cl" not in s and num <= 10:
        return int(num * 1000)
    return int(num)


def row_val(row: pd.Series, col: Optional[str]):
    if col is None or col not in row:
        return None
    return row[col]

# ---------------------------------------------------------------------------
# Column detection -----------------------------------------------------------
# ---------------------------------------------------------------------------

name_c = lookup("name")
reg_c = lookup("region")
alc_c = lookup("alcohol_content_percent")
price_c = lookup("action_price")
score_c = lookup("average_score")

list_col = lookup("taste_list")
profile_col = lookup("taste_profile", "taste profile")
if not list_col and not profile_col:
    sys.exit("No Taste_list or Taste_profile column found")

origin_url_c = lookup("origin url")
num_reviews_c = lookup("number_of_reviewers", "number of reviewers")
variety_c = lookup("variety")
aroma_c = lookup("aroma")
palate_c = lookup("taste")
finish_c = lookup("finish")
maturation_c = lookup("maturation")
volume_c = lookup("volume")
colour_c = lookup("contains_colouring", "contains colouring")
desc_c = lookup("product description", "product_description")
distillery_c = lookup("distillery")
dist_status_c = lookup("distillery_status", "distillery status")
found_year_c = lookup("distillery_founding_year", "distillery founding year")
country_c = lookup("country")

# ---------------------------------------------------------------------------
# Derived columns ------------------------------------------------------------
# ---------------------------------------------------------------------------

if list_col:
    raw_notes = df[list_col].apply(ensure_list)
else:
    raw_notes = (
        df[profile_col]
        .astype(str)
        .str.split(r"\s*\n\s*")
        .apply(lambda lst: [t.strip() for t in lst if t.strip()])
    )

# Explode into atomic tokens (lower‑case)
df["taste_list"] = raw_notes.apply(explode_tokens)

df["taste_sentence"] = df["taste_list"].apply(", ".join)

# ---------------------------------------------------------------------------
# Batch ingest ---------------------------------------------------------------
# ---------------------------------------------------------------------------

client.batch.configure(batch_size=200)

with client.batch as batch:
    for _, row in df.iterrows():
        obj: Dict[str, Any] = {
            "name": safe(row_val(row, name_c)) if name_c else f"Whisky-{uuid.uuid4()}",
            "tasteNotes": row["taste_list"],
            "tasteText": row["taste_sentence"],
            "region": safe(row_val(row, reg_c)),
            "alcohol_pct": safe(row_val(row, alc_c)),
            "price_eur": safe(row_val(row, price_c)),
            "score": safe(row_val(row, score_c)),

            # Optional extras ----------------------------------------------
            "origin_url": safe(row_val(row, origin_url_c)),
            "num_reviewers": parse_int(row_val(row, num_reviews_c)),
            "variety": safe(row_val(row, variety_c)),
            "aroma": safe(row_val(row, aroma_c)),
            "palate": safe(row_val(row, palate_c)),
            "finish": safe(row_val(row, finish_c)),
            "maturation": safe(row_val(row, maturation_c)),
            "volume_ml": parse_volume_ml(row_val(row, volume_c)),
            "contains_colouring": parse_bool(row_val(row, colour_c)),
            "description": safe(row_val(row, desc_c)),
            "distillery": safe(row_val(row, distillery_c)),
            "distillery_status": safe(row_val(row, dist_status_c)),
            "founding_year": parse_int(row_val(row, found_year_c)),
            "country": safe(row_val(row, country_c)),
        }

        batch.add_data_object(obj, "Whisky", uuid.uuid4())

print(f"Ingested {len(df)} whiskies from {CSV}")
