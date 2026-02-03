from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CheckError(BaseModel):
    type: str
    detail: str

    class Config:
        extra = "forbid"


class CheckResult(BaseModel):
    status: Literal["PASS", "FAIL"] = "PASS"
    severity: Literal["BLOCKING", "SOFT"] = "SOFT"
    errors: list[CheckError] = Field(default_factory=list)
    action: Literal["ACCEPT", "RETRY", "DROP_NARRATIVE"] = "ACCEPT"

    class Config:
        extra = "forbid"
