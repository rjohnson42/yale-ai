"""Append each agent turn to output/audit_log.json."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

LOG_PATH = Path(__file__).resolve().parent / "output" / "audit_log.json"


def log_turn(user_text: str, result: dict[str, Any], model: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    turns: list[dict[str, Any]] = []
    if LOG_PATH.exists():
        try:
            loaded = json.loads(LOG_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                turns = loaded
        except json.JSONDecodeError:
            turns = []
    shot = result.get("last_shot") or {}
    turns.append(
        {
            "at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "model": model,
            "user": user_text,
            "reply": result.get("text", ""),
            "tools": [event.get("name") for event in result.get("tool_events") or []],
            "captured_at": shot.get("captured_at"),
            "region": shot.get("region"),
        }
    )
    LOG_PATH.write_text(json.dumps(turns, indent=2), encoding="utf-8")
