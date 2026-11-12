"""Cross-cutting API contract models (ADR-0004)."""

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    field: str | None = Field(description="Dotted path of the offending input, if any.")
    code: str = Field(description="Stable, language-neutral error code.")
    message: str = Field(description="Developer-facing English description.")


class ErrorBody(BaseModel):
    code: str = Field(description="Stable, language-neutral error code; clients localize it.")
    message: str = Field(description="Developer-facing English description; not for display.")
    request_id: str | None = None
    details: list[ErrorDetail] = []


class ErrorResponse(BaseModel):
    error: ErrorBody
