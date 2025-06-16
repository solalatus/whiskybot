# Search tool – hybrid when unsorted, BM25 when sort is requested
# Compatible with Weaviate Python client v3 *and* v4.

from __future__ import annotations

import os
from typing import List, Optional, Union, Any

import weaviate
from dotenv import load_dotenv
from langchain.tools import StructuredTool
from pydantic import BaseModel, Field, field_validator

load_dotenv()

# ---------------------------------------------------------------------------
# Weaviate client (needs the extra header on free sandbox clusters)
# ---------------------------------------------------------------------------

extra_headers = {
    "X-Weaviate-Cluster-Url": os.getenv("WEAVIATE_URL", "").replace("https://", "")
}
client = weaviate.Client(
    os.getenv("WEAVIATE_URL"),
    auth_client_secret=weaviate.AuthApiKey(os.getenv("WEAVIATE_API_KEY")),
    additional_headers=extra_headers,
)

# ---------------------------------------------------------------------------
# Discover schema once so we know which properties are text / numeric
# ---------------------------------------------------------------------------

schema = client.schema.get(class_name="Whisky")
ALL_TEXT: List[str] = [
    p["name"] for p in schema["properties"] if p["dataType"][0].startswith("text")
]
NUM_PROPS = [p["name"] for p in schema["properties"] if p["dataType"][0] in {"number"}]

# ---------------------------------------------------------------------------
# Argument schema for the tool
# ---------------------------------------------------------------------------

class SortDirective(BaseModel):
    """e.g. {"path": ["score"], "order": "desc"}"""

    path: List[str] = Field(..., min_length=1)
    order: str = Field("desc", pattern="^(asc|desc)$")

class SearchArgs(BaseModel):
    query: str = Field("", description="User text query (can be empty when purely sorting)")
    limit: int = Field(12, ge=1, le=100)
    alpha: float = Field(0.35, ge=0.0, le=1.0)
    properties: Optional[List[str]] = None
    where: Optional[dict[str, Any]] = None
    sort: Optional[Union[str, List[SortDirective]]] = None

    @field_validator("properties", mode="before")
    def _default_props(cls, v):  # noqa: N805
        return v or ALL_TEXT

    @field_validator("sort", mode="before")
    def _normalise_sort(cls, v):  # noqa: N805
        if v is None:
            return None
        if isinstance(v, str):
            return [SortDirective(path=[v], order="desc")]
        return v

# ---------------------------------------------------------------------------
# Core implementation
# ---------------------------------------------------------------------------

def search_whisky(
    *,
    query: str = "",
    limit: int = 12,
    alpha: float = 0.35,
    properties: Optional[List[str]] = None,
    where: Optional[dict[str, Any]] = None,
    sort: Optional[Union[str, List[dict], List[SortDirective]]] = None,
):
    """Search Whisky collection with hybrid/BM25 and optional client‑side sort."""

    args = SearchArgs(
        query=query,
        limit=limit,
        alpha=alpha,
        properties=properties,
        where=where,
        sort=sort,
    )

    # ---------------------------------------
    # Build base query (server‑side)
    # ---------------------------------------
    q = client.query.get("Whisky", ALL_TEXT + NUM_PROPS).with_limit(args.limit * 4)

    if args.where:
        q = q.with_where(args.where)

    if args.sort:
        # Weaviate forbids any sort together with bm25/hybrid.
        # Work‑around: issue plain bm25 (no sort) to get large candidate set.
        q = q.with_bm25(query=args.query, properties=args.properties)
    else:
        # Fast recall hybrid when no explicit sort
        q = q.with_hybrid(query=args.query, alpha=args.alpha, properties=args.properties)

    q = q.with_additional(["distance", "explainScore"])
    res = q.do()
    if "errors" in res:
        raise RuntimeError(res["errors"])
    hits: List[dict] = res["data"]["Get"].get("Whisky", [])

    # ---------------------------------------
    # Client‑side sort if requested
    # ---------------------------------------
    if args.sort and hits:
        def sort_key(doc: dict):
            keys = []
            for directive in args.sort:  # type: ignore[attr-defined]
                path = directive["path"][0] if isinstance(directive, dict) else directive.path[0]
                keys.append(doc.get(path))
            return tuple(keys)

        for directive in reversed(args.sort):  # apply last key first for stable sort
            ascending = (
                directive["order"] == "asc" if isinstance(directive, dict) else directive.order == "asc"
            )
            hits.sort(key=sort_key, reverse=not ascending)
        hits = hits[: args.limit]

    # Trim to requested limit if not already
    return hits[: args.limit]


hybrid_product_search = StructuredTool.from_function(
    func=search_whisky,
    name="hybrid_product_search",
    description=(
        "Whisky search. Supports Weaviate filter JSON via 'where'. If 'sort' is provided,"
        " results are ordered client‑side because Weaviate forbids sort + search."
    ),
)
