"""HTTP error helpers matching shared ErrorCode where possible."""

from fastapi import HTTPException
from ru_tat_call_shared.contracts.common import ErrorCode


def api_error(status: int, code: ErrorCode, message: str) -> HTTPException:
    """Build an HTTPException with a JSON body `{code, message}`.

    Args:
        status: HTTP status.
        code: Stable error code from the API spec.
        message: Human-readable explanation (not logged as a secret).
    """
    return HTTPException(status_code=status, detail={"code": code.value, "message": message})
