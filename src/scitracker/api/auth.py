from typing import Self

from fastapi import APIRouter
from pydantic import BaseModel, Field

from scitracker.api.deps import Hasher, Repositories, Tokens
from scitracker.api.problems import ProblemDetails
from scitracker.domain.user import User
from scitracker.services.accounts import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    authenticate,
    register_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class UserOut(BaseModel):
    id: int
    email: str
    role: str

    @classmethod
    def from_domain(cls, user: User) -> Self:
        if user.id is None:  # pragma: no cover - stored users always have an id
            raise ValueError("only stored users can be returned by the API")
        return cls(id=user.id, email=user.email, role=user.role.value)


class RegisterIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)


class LoginIn(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - the OAuth2 token type, not a secret
    expires_in: int = Field(description="Seconds until the token expires")


@router.post(
    "/register",
    status_code=201,
    response_model=UserOut,
    summary="Create an account",
    responses={409: {"model": ProblemDetails}, 422: {"model": ProblemDetails}},
)
def register(body: RegisterIn, repositories: Repositories, hasher: Hasher) -> UserOut:
    user = register_user(repositories.users, hasher, email=body.email, password=body.password)
    repositories.commit()
    return UserOut.from_domain(user)


@router.post(
    "/login",
    response_model=TokenOut,
    summary="Get an access token",
    responses={401: {"model": ProblemDetails}, 422: {"model": ProblemDetails}},
)
def login(body: LoginIn, repositories: Repositories, hasher: Hasher, tokens: Tokens) -> TokenOut:
    user = authenticate(repositories.users, hasher, email=body.email, password=body.password)
    if user.id is None:  # pragma: no cover - stored users always have an id
        raise ValueError("only stored users can log in")
    return TokenOut(access_token=tokens.issue(user.id), expires_in=tokens.ttl_seconds)
