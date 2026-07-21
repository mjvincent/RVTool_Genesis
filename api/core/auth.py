"""Optional API bearer-token authentication.

When API_TOKEN is not set (or is empty), ``require_token`` is a no-op and
every endpoint is open — this is the correct behaviour for home-network / local
development use where adding authentication friction serves no purpose.

When API_TOKEN is set, every request to a protected endpoint must supply:
    Authorization: Bearer <token>

A missing or wrong token returns HTTP 401.  The comparison uses
``hmac.compare_digest`` to prevent timing attacks.

Usage (in any router):
    from fastapi import Depends
    from core.auth import require_token

    @router.get("/something")
    async def my_endpoint(token: None = Depends(require_token)):
        ...
"""
from __future__ import annotations

import hmac

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.config import settings

_bearer_scheme = HTTPBearer(auto_error=False)


async def require_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    """FastAPI dependency: enforce bearer token when API_TOKEN is configured.

    - If ``settings.api_token`` is empty: no-op — request proceeds unconditionally.
    - If ``settings.api_token`` is set and credentials are missing: HTTP 401.
    - If ``settings.api_token`` is set and the token is wrong: HTTP 401.
    """
    configured_token = settings.api_token
    if not configured_token:
        # Token enforcement is disabled — open access (home-network default).
        return

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Supply: Authorization: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not hmac.compare_digest(credentials.credentials, configured_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
