"""Yale SOM course assistant. main.py calls run_agent(message)."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from dotenv import load_dotenv
from pydantic_ai import Agent, UsageLimits, capture_run_messages
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from models import AgentResult, AuditEntry, AuditedToolCall
from tools import search_courses as search_catalog
from tools import web_search as search_web

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PROMPT_PATH = HERE / "prompts" / "prompt.md"
AUDIT_PATH = ROOT / "output" / "audit_trail.json"
PORTKEY_URL = "https://api.portkey.ai/v1"
_AUDIT_LOCK = threading.Lock()

# The project file wins over a key already exported in the shell.
load_dotenv(ROOT / ".env", override=True)
load_dotenv(ROOT.parent / ".env")


def _clip(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


def _model_name() -> str:
    return os.environ.get("LLM_MODEL", "gpt-5.6-luna")


def _build_model() -> OpenAIChatModel:
    key = os.environ.get("PORTKEY_API_KEY")
    if not key:
        raise RuntimeError(
            "No Portkey key found. Set PORTKEY_API_KEY in labs/week4/.env "
            "or labs/.env (see .env.example)."
        )
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        base_url=os.environ.get("PORTKEY_BASE_URL", PORTKEY_URL),
        api_key=key,
        default_headers={"x-portkey-api-key": key},
    )
    return OpenAIChatModel(_model_name(), provider=OpenAIProvider(openai_client=client))


def _build_agent() -> Agent[None, str]:
    if not PROMPT_PATH.is_file():
        raise RuntimeError(f"Missing system prompt: {PROMPT_PATH}")
    instructions = PROMPT_PATH.read_text(encoding="utf-8").strip()
    if not instructions:
        raise RuntimeError(f"System prompt is empty: {PROMPT_PATH}")
    agent: Agent[None, str] = Agent(
        _build_model(),
        output_type=str,
        instructions=instructions,
        name="yale_som_courses",
        retries=2,
    )

    @agent.tool_plain
    def search_courses(
        query: str = "",
        title: str = "",
        number: str = "",
        faculty: str = "",
        category: str = "",
        day: str = "",
        course_type: str = "",
    ) -> str:
        """Query the courses table by title, number, faculty, category, day, or free text.

        Returns matching rows, capped at 15. total_matches is the full count.
        Use this for anything the catalog can answer.
        """
        found = search_catalog(
            query=query,
            title=title,
            number=number,
            faculty=faculty,
            category=category,
            day=day,
            course_type=course_type,
        )
        return found.model_dump_json()

    @agent.tool_plain
    def web_search(query: str) -> str:
        """Search the public web when the courses table is not enough.

        Use for faculty news, public background, or syllabus context.
        Do not use this to override catalog times or instructors.
        """
        found = search_web(query)
        return found.model_dump_json()

    return agent


def _tool_args(raw: object) -> dict[str, str]:
    parsed: object = raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {"raw": _clip(raw, 180)}
    if not isinstance(parsed, dict):
        return {}
    return {
        str(key): _clip(value if isinstance(value, str) else json.dumps(value), 180)
        for key, value in parsed.items()
        if value not in ("", None, {}, [])
    }


def _short_result(content: object) -> str:
    data: object = content
    if isinstance(content, str):
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return _clip(content, 240)
    if isinstance(data, dict) and "total_matches" in data:
        return (
            f"total_matches={data.get('total_matches')} "
            f"returned={data.get('returned')} query={data.get('query')}"
        )
    if isinstance(data, dict) and "results" in data:
        hits = data.get("results") or []
        titles = ", ".join(str(hit.get("title", "")) for hit in hits[:3] if isinstance(hit, dict))
        return _clip(f"{len(hits)} web results: {titles}", 240)
    if isinstance(data, str):
        return _clip(data, 240)
    return _clip(json.dumps(data), 240)


def _audit_from_messages(
    messages: list[object],
    user_message: str,
    stop_reason: str,
    when: datetime,
    model_name: str,
) -> AuditEntry:
    thoughts: list[str] = []
    calls: dict[str, AuditedToolCall] = {}
    order: list[str] = []
    finish_reason: str | None = None
    for message in messages:
        parts = getattr(message, "parts", ())
        if isinstance(message, ModelResponse) and message.finish_reason:
            finish_reason = message.finish_reason
        for part in parts:
            if isinstance(part, ThinkingPart) and part.content.strip():
                thoughts.append(part.content.strip())
            elif isinstance(part, TextPart) and part.content.strip():
                text = part.content.strip()
                if not text.startswith("{"):
                    thoughts.append(text)
            elif isinstance(part, ToolCallPart):
                order.append(part.tool_call_id)
                calls[part.tool_call_id] = AuditedToolCall(
                    tool_name=part.tool_name,
                    args=_tool_args(part.args),
                    short_result="",
                )
            elif isinstance(part, ToolReturnPart):
                summary = _short_result(part.content)
                existing = calls.get(part.tool_call_id)
                if existing is None:
                    order.append(part.tool_call_id)
                    calls[part.tool_call_id] = AuditedToolCall(
                        tool_name=part.tool_name,
                        args={},
                        short_result=summary,
                    )
                else:
                    existing.short_result = summary
    thought_text = _clip(" ".join(thoughts), 800) if thoughts else "No separate thinking text was returned."
    if stop_reason == "completed":
        stop_reason = finish_reason or "stop"
    return AuditEntry(
        time=when,
        user_message=user_message,
        thoughts=thought_text,
        tool_calls=[calls[tool_id] for tool_id in order],
        stop_reason=_clip(stop_reason, 400),
        model=model_name,
    )


def _append_audit(entry: AuditEntry) -> None:
    """Add one row. Leave earlier rows in place."""
    with _AUDIT_LOCK:
        saved: list[AuditEntry] = []
        if AUDIT_PATH.is_file() and AUDIT_PATH.stat().st_size > 0:
            raw = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
            items = raw if isinstance(raw, list) else [raw]
            saved = [AuditEntry.model_validate(item) for item in items]
        saved.append(entry)
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = [item.model_dump(mode="json") for item in saved]
        AUDIT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _tools_used(entry: AuditEntry) -> list[str]:
    return [call.tool_name for call in entry.tool_calls]


def _message_history(turns: list[dict[str, str]] | None) -> list[ModelRequest | ModelResponse] | None:
    """Replay saved chat text so a returning question can follow the last one."""
    if not turns:
        return None
    history: list[ModelRequest | ModelResponse] = []
    for turn in turns[-16:]:
        text = str(turn.get("text", "")).strip()
        if not text:
            continue
        if turn.get("role") == "assistant":
            history.append(ModelResponse(parts=[TextPart(content=text)]))
        else:
            history.append(ModelRequest(parts=[UserPromptPart(content=text)]))
    return history or None


def run_agent(message: str, history: list[dict[str, str]] | None = None) -> dict:
    """Answer one catalog question. Returns reply and the tools that ran."""
    model_name = _model_name()
    when = datetime.now().astimezone()
    print(f"model={model_name} via Portkey", flush=True)
    messages: list[object] = []
    try:
        agent = _build_agent()
        with capture_run_messages() as messages:
            result = agent.run_sync(
                message,
                message_history=_message_history(history),
                usage_limits=UsageLimits(request_limit=8, tool_calls_limit=6),
            )
    except Exception as exc:
        entry = _audit_from_messages(
            messages,
            message,
            f"{type(exc).__name__}: {exc}",
            when,
            model_name,
        )
        try:
            _append_audit(entry)
        except Exception as audit_exc:
            print(f"audit write failed: {audit_exc}", flush=True)
        return AgentResult(
            reply=f"I could not finish that question. {exc}",
            tools_used=_tools_used(entry),
        ).model_dump()

    entry = _audit_from_messages(result.all_messages(), message, "completed", when, model_name)
    try:
        _append_audit(entry)
    except Exception as audit_exc:
        print(f"audit write failed: {audit_exc}", flush=True)
    reply = result.output if isinstance(result.output, str) else str(result.output)
    return AgentResult(reply=reply, tools_used=_tools_used(entry)).model_dump()
