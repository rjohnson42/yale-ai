"""Campus Customs API.

Run from hw4/backend:

    uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from agent import run_agent
from db import (
    add_message,
    authenticate,
    close_session,
    create_user,
    ensure_sessions,
    list_messages,
    open_session,
    user_for_token,
)
from models import ChatResponse, ProductCard, ProductSearchResult, SavedMessage, ShopperDeps
from tools import get_catalogue_product, search_catalogue

app = FastAPI(title="Campus Customs API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5174",
        "http://localhost:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    email: str
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)

    @field_validator("first_name", "last_name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Enter a name.")
        return cleaned

    @field_validator("email")
    @classmethod
    def _clean_email(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not _EMAIL.fullmatch(cleaned):
            raise ValueError("That email doesn't look right.")
        return cleaned


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _clean_email(cls, value: str) -> str:
        return value.strip().lower()


class UserPublic(BaseModel):
    id: int
    email: str
    name: str
    first_name: str
    last_name: str


class AuthResponse(BaseModel):
    token: str
    user: UserPublic


class HistoryTurn(BaseModel):
    role: str
    content: str = Field(default="", max_length=1000)

    @field_validator("role")
    @classmethod
    def _role(cls, value: str) -> str:
        if value not in {"user", "assistant"}:
            raise ValueError("role must be user or assistant")
        return value


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    page_path: str = Field(default="", max_length=200)
    product_id: str = Field(default="", max_length=80)
    history: list[HistoryTurn] = Field(default_factory=list, max_length=12)


_PRODUCT_PATH = re.compile(r"^/products/([a-z0-9-]{1,80})$")
_OTHER_PATH = re.compile(r"^/(products|about|login|create-account)?$")


def _bearer(authorization: Optional[str]) -> str:
    if not authorization:
        return ""
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return ""
    return token.strip()


def current_user(authorization: Optional[str] = Header(default=None)) -> dict[str, object]:
    user = user_for_token(_bearer(authorization))
    if user is None:
        raise HTTPException(status_code=401, detail="Log in to continue.")
    return user


def optional_user(authorization: Optional[str] = Header(default=None)) -> Optional[dict[str, object]]:
    return user_for_token(_bearer(authorization))


def shopper_from_request(body: ChatRequest, user: Optional[dict[str, object]]) -> ShopperDeps:
    """Name and email come from the session. The page comes from the browser path."""
    path = body.page_path.strip()
    product_id = ""
    product_match = _PRODUCT_PATH.fullmatch(path)
    if product_match:
        product_id = product_match.group(1)
        claimed = body.product_id.strip().lower()
        if claimed and claimed != product_id:
            product_id = ""
    elif not _OTHER_PATH.fullmatch(path):
        path = ""
    card = get_catalogue_product(product_id) if product_id else None
    if card is None:
        product_id = ""
        product_name = ""
    else:
        product_id = card.product_id
        product_name = card.name
    if user is None:
        return ShopperDeps(page_path=path, viewing_product_id=product_id, viewing_product_name=product_name)
    return ShopperDeps(
        signed_in=True,
        name=str(user.get("name") or ""),
        first_name=str(user.get("first_name") or ""),
        email=str(user.get("email") or ""),
        page_path=path,
        viewing_product_id=product_id,
        viewing_product_name=product_name,
    )


@app.on_event("startup")
def _startup() -> None:
    ensure_sessions()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/register", response_model=AuthResponse)
def register(body: RegisterRequest) -> AuthResponse:
    if body.password != body.confirm_password:
        raise HTTPException(status_code=400, detail="Those passwords don't match.")
    try:
        user = create_user(body.first_name, body.last_name, body.email, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    token = open_session(int(user["id"]))
    return AuthResponse(token=token, user=UserPublic.model_validate(user))


@app.post("/api/login", response_model=AuthResponse)
def login(body: LoginRequest) -> AuthResponse:
    user = authenticate(body.email, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="That email and password don't match.")
    token = open_session(int(user["id"]))
    return AuthResponse(token=token, user=UserPublic.model_validate(user))


@app.get("/api/me", response_model=UserPublic)
def me(user: dict[str, object] = Depends(current_user)) -> UserPublic:
    return UserPublic.model_validate(user)


@app.post("/api/logout")
def logout(authorization: Optional[str] = Header(default=None)) -> dict[str, str]:
    close_session(_bearer(authorization))
    return {"status": "ok"}


@app.get("/api/products", response_model=ProductSearchResult)
def products(
    q: str = "",
    garment_type: str = "",
    color: str = "",
    max_price: Optional[float] = None,
    size: str = "",
) -> ProductSearchResult:
    return search_catalogue(
        query=q,
        garment_type=garment_type,
        color=color,
        max_price=max_price,
        size=size,
    )


@app.get("/api/products/{product_id}", response_model=ProductCard)
def product(product_id: str) -> ProductCard:
    found = get_catalogue_product(product_id)
    if found is None:
        raise HTTPException(status_code=404, detail="We don't carry that one.")
    return found


@app.get("/api/messages", response_model=list[SavedMessage])
def messages(user: dict[str, object] = Depends(current_user)) -> list[SavedMessage]:
    return [SavedMessage.model_validate(row) for row in list_messages(int(user["id"]))]


@app.post("/api/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    user: Optional[dict[str, object]] = Depends(optional_user),
) -> ChatResponse:
    shopper = shopper_from_request(body, user)
    if user is None:
        history = [
            {"role": turn.role, "content": turn.content.strip()}
            for turn in body.history
            if turn.content.strip()
        ]
    else:
        history = [
            {"role": str(row["role"]), "content": str(row["content"])}
            for row in list_messages(int(user["id"]))
        ]
    reply, cards = run_agent(body.message.strip(), history, shopper)
    cards_json = [card.model_dump() for card in cards]
    if user is None:
        saved = {
            "id": -int(datetime.now(timezone.utc).timestamp() * 1000),
            "role": "assistant",
            "content": reply,
            "products": cards_json,
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        }
    else:
        user_id = int(user["id"])
        add_message(user_id, "user", body.message.strip(), [])
        saved = add_message(user_id, "assistant", reply, cards_json)
    return ChatResponse(reply=reply, products=cards, message=SavedMessage.model_validate(saved))
