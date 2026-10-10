"""Screen-aware browser agent: PydanticAI + gpt-5.6-luna via Portkey.

run_agent(user_text) -> {"text": str, "tool_events": [...], "last_shot": {...} | None}

The conversation, including screenshots, is kept here between turns so later
questions can refer back to earlier images. app.py only sends the new message.
"""

from __future__ import annotations

import os
import sys
import threading
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from dotenv import load_dotenv  # noqa: E402
from openai import AsyncOpenAI  # noqa: E402
from pydantic_ai import Agent, BinaryContent, RunContext, ToolReturn  # noqa: E402
from pydantic_ai.messages import (  # noqa: E402
    ModelMessage,
    ModelRequest,
    RetryPromptPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.openai import OpenAIChatModel  # noqa: E402
from pydantic_ai.providers.openai import OpenAIProvider  # noqa: E402

import audit_log  # noqa: E402
import screen_tools  # noqa: E402

HERE = Path(__file__).resolve().parent
CLASS_ROOT = HERE.parent  # labs/: the folder that contains this project
load_dotenv(CLASS_ROOT / ".env")
load_dotenv(HERE / ".env", override=True)

MODEL_NAME = os.environ.get("LLM_MODEL", "gpt-5.6-luna")
PORTKEY_BASE_URL = os.environ.get("PORTKEY_BASE_URL", "https://api.portkey.ai/v1")
PROMPT_PATH = HERE / "prompts" / "prompt.md"

# Screenshots cost many tokens on every later call; older ones become a text stub.
MAX_IMAGES_IN_HISTORY = 4
MAX_TURNS_IN_HISTORY = 20
DROPPED_IMAGE_NOTE = "[older screenshot removed to save context; take a new one if needed]"


@dataclass
class TurnState:
    shots: list[screen_tools.Screenshot] = field(default_factory=list)


def _build_model() -> OpenAIChatModel:
    key = os.environ.get("PORTKEY_API_KEY")
    if not key:
        raise RuntimeError(
            "PORTKEY_API_KEY is not set. Add it to labs/.env (the folder that contains this project)."
        )
    client = AsyncOpenAI(
        base_url=PORTKEY_BASE_URL,
        api_key=key,
        default_headers={"x-portkey-api-key": key},
    )
    return OpenAIChatModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))


def _build_agent() -> Agent[TurnState, str]:
    agent: Agent[TurnState, str] = Agent(
        _build_model(),
        deps_type=TurnState,
        instructions=PROMPT_PATH.read_text(encoding="utf-8"),
        retries=2,
    )

    @agent.instructions
    def _context(_: RunContext[TurnState]) -> str:
        return f"Local time: {datetime.now().astimezone().isoformat(timespec='minutes')}."

    @agent.tool
    def look_at_screen(ctx: RunContext[TurnState]) -> ToolReturn | dict[str, str]:
        """Screenshot the Browser agent window and look at the page on the left.

        Use when the answer depends on what is visible right now.
        """
        try:
            shot = screen_tools.capture_screen()
        except Exception as exc:
            return {"error": f"Screenshot failed: {exc}"}
        ctx.deps.shots.append(shot)
        print(
            f"  screenshot -> {shot.region} {shot.width}x{shot.height} {shot.captured_at}",
            flush=True,
        )
        return ToolReturn(
            return_value=shot.summary(),
            content=[
                f"Screenshot ({shot.region}) taken at {shot.captured_at}:",
                BinaryContent(shot.png, media_type="image/png"),
            ],
        )

    return agent


_AGENT: Agent[TurnState, str] | None = None
_HISTORY: list[ModelMessage] = []
_LOCK = threading.Lock()


def _get_agent() -> Agent[TurnState, str]:
    global _AGENT
    if _AGENT is None:
        _AGENT = _build_agent()
    return _AGENT


def _is_user_turn(msg: ModelMessage) -> bool:
    if not isinstance(msg, ModelRequest):
        return False
    kinds = {type(p) for p in msg.parts}
    return UserPromptPart in kinds and not kinds & {ToolReturnPart, RetryPromptPart}


def _is_image(item: Any) -> bool:
    return isinstance(item, BinaryContent) and item.media_type.startswith("image/")


def _trim(messages: list[ModelMessage]) -> list[ModelMessage]:
    starts = [i for i, m in enumerate(messages) if _is_user_turn(m)]
    if len(starts) > MAX_TURNS_IN_HISTORY:
        messages = messages[starts[-MAX_TURNS_IN_HISTORY]:]

    kept = 0
    out: list[ModelMessage] = []
    for msg in reversed(messages):
        if isinstance(msg, ModelRequest):
            parts = []
            for part in msg.parts:
                if isinstance(part, UserPromptPart) and not isinstance(part.content, str):
                    items = []
                    for item in part.content:
                        if _is_image(item):
                            kept += 1
                            if kept > MAX_IMAGES_IN_HISTORY:
                                item = DROPPED_IMAGE_NOTE
                        items.append(item)
                    part = replace(part, content=items)
                parts.append(part)
            msg = replace(msg, parts=parts)
        out.append(msg)
    return list(reversed(out))


def _tool_events(messages: list[ModelMessage]) -> list[dict[str, str]]:
    calls: dict[str, dict[str, str]] = {}
    for msg in messages:
        for part in msg.parts:
            if isinstance(part, ToolCallPart):
                label = "Look at screen" if part.tool_name == "look_at_screen" else part.tool_name
                calls[part.tool_call_id] = {"name": label, "status": "completed"}
            elif isinstance(part, ToolReturnPart) and part.tool_call_id in calls:
                if isinstance(part.content, dict) and "error" in part.content:
                    calls[part.tool_call_id]["status"] = "error"
    return list(calls.values())


def run_agent(user_text: str) -> dict[str, Any]:
    agent = _get_agent()
    state = TurnState()
    with _LOCK:
        history = list(_HISTORY)
        print(f"  model -> {MODEL_NAME} via Portkey ({len(history)} messages of history)", flush=True)
        result = agent.run_sync(user_text, deps=state, message_history=history)
        _HISTORY[:] = _trim(result.all_messages())

    last = state.shots[-1] if state.shots else None
    payload = {
        "text": str(result.output).strip() or "(empty reply)",
        "tool_events": _tool_events(result.new_messages()),
        "last_shot": {"captured_at": last.captured_at, "region": last.region} if last else None,
    }
    try:
        audit_log.log_turn(user_text, payload, MODEL_NAME)
    except Exception as exc:
        print(f"  audit log skipped: {exc}", flush=True)
    return payload


def reset_history() -> None:
    with _LOCK:
        _HISTORY.clear()


def main() -> None:
    question = " ".join(sys.argv[1:]) or "Take a look at my screen and tell me what's on it."
    out = run_agent(question)
    print(out["text"])
    print("\ntools:", [t["name"] for t in out["tool_events"]])


if __name__ == "__main__":
    main()
