from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from scitracker.api.problems import ProblemDetails
from scitracker.domain.errors import AuthenticationError
from scitracker.domain.user import User
from scitracker.services.ports import PasswordHasher, TokenService, UnitOfWork

Scope = Callable[[], AbstractContextManager[UnitOfWork]]
Ping = Callable[[], None]

PROTECTED: dict[int | str, dict[str, Any]] = {401: {"model": ProblemDetails}}

_bearer = HTTPBearer(auto_error=False, description="Token from POST /api/v1/auth/login")


def get_repositories(request: Request) -> Iterator[UnitOfWork]:
    """One scope (one database session) per request, closed when the response is done."""
    scope: Scope = request.app.state.scope
    with scope() as unit_of_work:
        yield unit_of_work


Repositories = Annotated[UnitOfWork, Depends(get_repositories)]


def get_hasher(request: Request) -> PasswordHasher:
    hasher: PasswordHasher = request.app.state.hasher
    return hasher


def get_tokens(request: Request) -> TokenService:
    tokens: TokenService = request.app.state.tokens
    return tokens


Hasher = Annotated[PasswordHasher, Depends(get_hasher)]
Tokens = Annotated[TokenService, Depends(get_tokens)]


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    repositories: Repositories,
    tokens: Tokens,
) -> User:
    if credentials is None:
        raise AuthenticationError("Authentication required.")
    user = repositories.users.get(tokens.verify(credentials.credentials))
    if user is None:  # a valid token of a user that no longer exists
        raise AuthenticationError("Invalid or expired token.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
