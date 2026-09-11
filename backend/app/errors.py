"""The single error envelope for every non-2xx response (API.md §Conventions).

{ "error": { "code": "VALIDATION_ERROR", "message": "...", "field": "..." } }

Codes: VALIDATION_ERROR (400) · NOT_FOUND (404) · RATE_LIMITED (429) ·
UPSTREAM_UNAVAILABLE (503, /assist/* only) · INTERNAL (500).
"""
from typing import Any


class ApiError(Exception):
    def __init__(self, code: str, message: str, field: str | None = None, status_code: int = 400):
        self.code = code
        self.message = message
        self.field = field
        self.status_code = status_code
        super().__init__(message)


def error_envelope(code: str, message: str, field: str | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "field": field}}
