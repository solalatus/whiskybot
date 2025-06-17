"""Search tool – hybrid when unsorted, BM25 when sort is requested.
Extended with categorical *region* filter automatically discovered at startup.
Fix: allow empty queries when only sorting (skip BM25 call).
Compatible with Weaviate Python client v3 *and* v4.
"""

from __future__ import annotations

import os
from typing import List, Optional, Union, Any, Sequence

import weaviate
from dotenv import load_dotenv
from langchain.tools import StructuredTool
from pydantic import BaseModel, Field, field_validator, model_validator

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

SCHEMA = client.schema.get(class_name="Whisky")
ALL_TEXT: List[str] = [
    p["name"] for p in SCHEMA["properties"] if p["dataType"][0].startswith("text")
]
NUM_PROPS: List[str] = [
    p["name"] for p in SCHEMA["properties"] if p["dataType"][0] in {"number"}
]

# ---------------------------------------------------------------------------
# Discover *all* distinct regions ONCE so the LLM can reason about them
# without having to query Weaviate for every search.
# ---------------------------------------------------------------------------

def _discover_regions() -> List[str]:
    """Return sorted list of distinct region names present in the Whisky class.
    Tries Aggregate groupBy first; falls back to a limited scan if unsupported.
    """

    # fast path – Aggregate groupBy
    try:
        res = (
            client.query.aggregate("Whisky")
            .with_group_by(["region"])
            .with_fields("groupedBy { value }")
            .do()
        )
        groups: Sequence[dict[str, Any]] = res["data"]["Aggregate"]["Whisky"]
        return sorted({g["groupedBy"]["value"] for g in groups if g.get("groupedBy")})
    except Exception:
        pass

    # slow path – scan up to 5000 items
    try:
        seen: set[str] = set()
        res = (
            client.query.get("Whisky", ["region"])
            .with_where({"path": ["region"], "operator": "IsNotNull"})
            .with_limit(5000)
            .do()
        )
        for obj in res["data"]["Get"].get("Whisky", []):
            reg = obj.get("region")
            if reg:
                seen.add(reg)
        return sorted(seen)
    except Exception:
        return []


REGION_VALUES: List[str] = _discover_regions()

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
    region: Optional[Union[str, List[str]]] = Field(
        None,
        description="Categorical region filter; values discovered at startup.",
    )

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

    @model_validator(mode="after")
    def _validate_region(self):  # noqa: N805
        if REGION_VALUES and self.region is not None:
            values = [self.region] if isinstance(self.region, str) else list(self.region)
            unknown = set(values) - set(REGION_VALUES)
            if unknown:
                raise ValueError(f"Unknown region(s): {sorted(unknown)}. Known: {REGION_VALUES}")
        return self


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _merge_where(existing: Optional[dict], extra: dict) -> dict:
    """Combine two Weaviate `where` dicts with AND."""
    if not existing:
        return extra
    return {"operator": "And", "operands": [existing, extra]}


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
    region: Optional[Union[str, List[str]]] = None,
):
    """Search Whisky collection with hybrid/BM25 and optional client‑side sort.
    With an explicit `sort` but *no* text query, we now skip BM25 entirely to avoid
    Weaviate's "keyword search must have query" error.
    """

    args = SearchArgs(
        query=query,
        limit=limit,
        alpha=alpha,
        properties=properties,
        where=where,
        sort=sort,
        region=region,
    )

    # region → where clause
    if args.region is not None:
        regions = [args.region] if isinstance(args.region, str) else list(args.region)
        region_filter = (
            {
                "path": ["region"],
                "operator": "Equal",
                "valueText": regions[0],
            }
            if len(regions) == 1
            else {
                "operator": "Or",
                "operands": [
                    {"path": ["region"], "operator": "Equal", "valueText": r}
                    for r in regions
                ],
            }
        )
        where_combined = _merge_where(args.where, region_filter)
    else:
        where_combined = args.where

    # base query
    q = client.query.get("Whisky", ALL_TEXT + NUM_PROPS).with_limit(args.limit * 4)
    if where_combined:
        q = q.with_where(where_combined)

    if args.sort:
        # Only add BM25 when a query string is present
        if args.query.strip():
            q = q.with_bm25(query=args.query, properties=args.properties)
        # else: rely solely on the where filter (no keyword search)
    else:
        # hybrid path
        q = q.with_hybrid(query=args.query, alpha=args.alpha, properties=args.properties)

    q = q.with_additional(["distance", "explainScore"])
    res = q.do()
    if "errors" in res:
        raise RuntimeError(res["errors"])
    hits: List[dict] = res["data"]["Get"].get("Whisky", [])

    # client‑side sort
    if args.sort and hits:
        def sort_key(doc: dict):
            keys = []
            for directive in args.sort:  # type: ignore[attr-defined]
                p = directive["path"][0] if isinstance(directive, dict) else directive.path[0]
                keys.append(doc.get(p))
            return tuple(keys)

        for directive in reversed(args.sort):
            ascending = (
                directive["order"] == "asc"
                if isinstance(directive, dict)
                else directive.order == "asc"
            )
            hits.sort(key=sort_key, reverse=not ascending)
        hits = hits[: args.limit]

    return hits[: args.limit]


# ---------------------------------------------------------------------------
# Tool wrapper
# ---------------------------------------------------------------------------

hybrid_product_search = StructuredTool.from_function(
    func=search_whisky,
    name="hybrid_product_search",
    description=(
        "Whisky search. Supports `region` filter (values discovered at startup). Accepts "
        "generic Weaviate `where`. If `sort` is given without a query, we return all items "
        "matching filters and sort client‑side. If `sort` and query are given, we fetch a "
        "larger candidate set via BM25 to sort afterwards."
    ),
)

__all__ = ["hybrid_product_search", "REGION_VALUES"]
