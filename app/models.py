
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, validator

class WhereOperand(BaseModel):
    path: List[str] = Field(..., description="e.g. ['price_eur']")
    operator: str   = Field(..., description="Equal | LessThan | GreaterThan | ContainsAny | ContainsAll")
    valueText: Optional[str] = None
    valueNumber: Optional[float] = None

    @validator("operator")
    def _check_op(cls, v):
        allowed = {"Equal", "NotEqual", "LessThan", "LessThanEqual", "GreaterThan",
                   "GreaterThanEqual", "ContainsAny", "ContainsAll"}
        if v not in allowed:
            raise ValueError(f"Operator {v} not supported")
        return v

class WhereFilter(BaseModel):
    operator: Optional[str] = None      # And | Or | Not
    operands: Optional[List["WhereFilter"]] = None
    leaf: Optional[WhereOperand] = None

WhereFilter.update_forward_refs()

class ProductSearchArgs(BaseModel):
    query: str
    properties: List[str]
    where: Optional[WhereFilter] = None
    sort: Optional[List[Dict[str, Any]]] = None
    alpha: float = 0.5
    limit: int = 10
