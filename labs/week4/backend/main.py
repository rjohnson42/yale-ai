"""Yale SOM course explorer API desk.

Run from backend/:  uvicorn main:app --port 8000
Open API docs:      http://127.0.0.1:8000/docs
Frontend (Vite):    http://127.0.0.1:5173
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from agent import run_agent
from db import (
    CATALOG_PATH,
    add_message,
    authenticate,
    close_session,
    create_user,
    list_messages,
    open_session,
    user_for_token,
)
from models import AuthResponse, SavedMessage, UserPublic
from tools import load_courses

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / ".env")

app = FastAPI(title="Yale SOM Courses", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


class ChatResponse(BaseModel):
    reply: str
    tools_used: list[str] = Field(default_factory=list)


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
    name: str = ""

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not _EMAIL.fullmatch(cleaned):
            raise ValueError("Enter a valid email address.")
        return cleaned

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return " ".join(value.split())


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return value.strip().lower()


def _bearer(authorization: str | None) -> str:
    if not authorization:
        return ""
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        return ""
    return token.strip()


def require_user(authorization: Annotated[str | None, Header()] = None) -> dict:
    user = user_for_token(_bearer(authorization))
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    return user


def _public(user: dict) -> UserPublic:
    return UserPublic(id=int(user["id"]), email=str(user["email"]), name=str(user["name"]))


@app.get("/api/health")
def health():
    return {"ok": True, "courses_db": CATALOG_PATH.name}


@app.post("/api/register", response_model=AuthResponse)
def register(body: RegisterRequest):
    try:
        user = create_user(body.email, body.password, body.name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    token = open_session(int(user["id"]))
    return AuthResponse(token=token, user=_public(user))


@app.post("/api/login", response_model=AuthResponse)
def login(body: LoginRequest):
    user = authenticate(body.email, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Email or password is not right.")
    token = open_session(int(user["id"]))
    return AuthResponse(token=token, user=_public(user))


@app.get("/api/me", response_model=UserPublic)
def me(user: dict = Depends(require_user)):
    return _public(user)


@app.post("/api/logout")
def logout(authorization: Annotated[str | None, Header()] = None):
    close_session(_bearer(authorization))
    return {"ok": True}


@app.get("/api/courses")
def list_courses(q: str | None = Query(default=None), user: dict = Depends(require_user)):
    """Return courses from the courses table for the React catalog."""
    del user
    courses = [course.model_dump(by_alias=True) for course in load_courses()]
    if not q:
        return {"count": len(courses), "courses": courses}
    needle = q.lower().strip()
    matched = [course for course in courses if needle in json.dumps(course, ensure_ascii=False).lower()]
    return {"count": len(matched), "courses": matched}


@app.get("/api/messages", response_model=list[SavedMessage])
def messages(user: dict = Depends(require_user)):
    return [SavedMessage.model_validate(row) for row in list_messages(int(user["id"]))]


@app.post("/api/chat", response_model=ChatResponse)
def chat(body: ChatRequest, user: dict = Depends(require_user)):
    user_id = int(user["id"])
    prior = [
        {"role": str(row["role"]), "text": str(row["text"])}
        for row in list_messages(user_id)
    ]
    result = run_agent(body.message, history=prior)
    reply = str(result.get("reply", ""))
    tools = [str(name) for name in (result.get("tools_used") or [])]
    add_message(user_id, "user", body.message, [])
    add_message(user_id, "assistant", reply, tools)
    return ChatResponse(reply=reply, tools_used=tools)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
