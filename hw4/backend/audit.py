"""Append-only log of one agent run. Existing rows are kept."""

from __future__ import annotations

import fcntl
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from pydantic_ai.messages import ToolCallPart, ToolReturnPart

ROOT = Path(__file__).resolve().parent.parent
TRAIL_PATH = ROOT / "output" / "audit_trail.json"
_SECRET = re.compile(r"pbkdf2[^\s]*|[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
_ARG_KEYS = ("query", "garment_type", "product_id", "size", "limit")
_RESULT_KEYS = (
    "found",
    "name",
    "query",
    "total_matches",
    "returned",
    "price_text",
    "asked_size",
    "asked_quantity",
    "out_of_stock_sizes",
    "colors",
    "signed_in",
    "first_name",
    "page_path",
    "viewing_product_id",
    "note",
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _short(value: object, limit: int = 160) -> str:
    text = _SECRET.sub("[redacted]", str(value))
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _as_dict(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return parsed
    return None


def _short_args(raw: object) -> str:
    payload = _as_dict(raw)
    if payload is None:
        return _short(raw, 120)
    kept = {key: payload[key] for key in _ARG_KEYS if payload.get(key) not in (None, "")}
    return _short(json.dumps(kept or payload, default=str), 160)


def _short_result(raw: object) -> str:
    payload = _as_dict(raw)
    if payload is None:
        return _short(raw)
    kept = {key: payload[key] for key in _RESULT_KEYS if key in payload and payload[key] not in (None, "", [])}
    if "products" in payload and isinstance(payload["products"], list):
        kept["products"] = len(payload["products"])
    return _short(json.dumps(kept or payload, default=str))


def events_from_messages(messages: list[object], stop_reason: str) -> list[dict[str, str]]:
    """One row per tool return in this run. The last row carries the stop reason."""
    pending: dict[str, ToolCallPart] = {}
    order: list[str] = []
    events: list[dict[str, str]] = []
    for message in messages:
        for part in getattr(message, "parts", ()):
            if isinstance(part, ToolCallPart):
                call_id = part.tool_call_id or part.tool_name
                pending[call_id] = part
                order.append(call_id)
            elif isinstance(part, ToolReturnPart):
                call_id = part.tool_call_id or part.tool_name
                call = pending.get(call_id)
                stamp = getattr(part, "timestamp", None)
                if hasattr(stamp, "astimezone"):
                    stamp = stamp.astimezone(timezone.utc)
                events.append(
                    {
                        "time": stamp.strftime("%Y-%m-%dT%H:%M:%SZ") if hasattr(stamp, "strftime") else _now(),
                        "tool": part.tool_name,
                        "args": _short_args(call.args if call else ""),
                        "result": _short_result(part.content),
                        "stop_reason": "",
                    }
                )
    if not events and order:
        for call_id in order:
            call = pending[call_id]
            events.append(
                {
                    "time": _now(),
                    "tool": call.tool_name,
                    "args": _short_args(call.args),
                    "result": "",
                    "stop_reason": "",
                }
            )
    if not events:
        events.append(
            {
                "time": _now(),
                "tool": "none",
                "args": "",
                "result": "",
                "stop_reason": "",
            }
        )
    events[-1]["stop_reason"] = stop_reason
    return events


def append_events(events: list[dict[str, str]]) -> None:
    """Add rows to output/audit_trail.json. A bad file is left untouched."""
    if not events:
        return
    TRAIL_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock_path = TRAIL_PATH.with_suffix(".lock")
    with lock_path.open("a", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            existing: list[object] = []
            if TRAIL_PATH.is_file() and TRAIL_PATH.stat().st_size > 0:
                parsed = json.loads(TRAIL_PATH.read_text(encoding="utf-8"))
                if not isinstance(parsed, list):
                    raise RuntimeError(f"{TRAIL_PATH.name} is not a list. It was not overwritten.")
                existing = parsed
            existing.extend(events)
            temporary = TRAIL_PATH.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
            temporary.replace(TRAIL_PATH)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def record_loop(messages: list[object], stop_reason: str) -> None:
    append_events(events_from_messages(messages, stop_reason))
