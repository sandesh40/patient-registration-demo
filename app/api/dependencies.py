import secrets
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import session_scope

bearer = HTTPBearer(auto_error=False)


def require_api_token(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    expected = request.app.state.settings.api_auth_token.get_secret_value()
    if not expected:
        return
    if credentials is None or not secrets.compare_digest(
        credentials.credentials.encode(), expected.encode()
    ):
        raise HTTPException(
            401, "A valid API token is required", headers={"WWW-Authenticate": "Bearer"}
        )


def get_session(request: Request) -> Iterator[Session]:
    yield from session_scope(request.app.state.engine)


DatabaseSession = Annotated[Session, Depends(get_session)]
