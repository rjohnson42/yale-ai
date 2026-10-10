"""PydanticAI sports judge: sample frames, describe the clip, then score or call.

run_agent(video_path, on_tool=None) -> {"verdict": ..., "tool_events": [...]}
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from dotenv import load_dotenv  # noqa: E402
from pydantic_ai import Agent, ModelRetry, RunContext  # noqa: E402
from pydantic_ai.exceptions import UsageLimitExceeded  # noqa: E402
from pydantic_ai.usage import UsageLimits  # noqa: E402

import video_tools  # noqa: E402
from models import DunkVerdict, FoulVerdict  # noqa: E402

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
load_dotenv(PARENT / ".env")
load_dotenv(HERE / ".env", override=True)

Verdict = DunkVerdict | FoulVerdict
OnTool = Callable[[str], None]


@dataclass
class JudgeDeps:
    on_tool: OnTool | None = None
    tool_events: list[dict[str, str]] = field(default_factory=list)
    verdict: Verdict | None = None

    def note(self, name: str) -> None:
        self.tool_events.append({"name": name})
        print(f"  tool -> {name}", flush=True)
        if self.on_tool is not None:
            self.on_tool(name)


def _already_done(ctx: RunContext[JudgeDeps]) -> dict[str, str] | None:
    """One scoring tool ends the run. Later tool calls must not start another pass."""
    if ctx.deps.verdict is None:
        return None
    return {
        "status": "complete",
        "message": "Verdict already recorded. Submit it as the final result now. Do not call tools again.",
    }


def _build_agent() -> Agent[JudgeDeps, Verdict]:
    instructions = (HERE / "prompts" / "prompt.md").read_text(encoding="utf-8")
    agent: Agent[JudgeDeps, Verdict] = Agent(
        video_tools.get_model(),
        output_type=Verdict,  # type: ignore[arg-type]
        deps_type=JudgeDeps,
        instructions=instructions,
        model_settings=video_tools.VISION_SETTINGS,
        retries=0,
    )

    @agent.tool
    def sample_frames(
        ctx: RunContext[JudgeDeps],
        video_path: str,
        every_n_sec: float = 0.5,
        max_frames: int = 16,
    ) -> dict[str, Any]:
        """Grab still frames from the clip. Call this first.

        video_path is the file path you were given. Returns frame_paths and clip_label.
        """
        if done := _already_done(ctx):
            return done
        ctx.deps.note("sample_frames")
        return video_tools.sample_frames(video_path, every_n_sec=every_n_sec, max_frames=max_frames)

    @agent.tool
    async def describe_video(
        ctx: RunContext[JudgeDeps],
        frame_paths: list[str],
        clip_label: str,
    ) -> dict[str, Any]:
        """Watch the frames and describe the clip. Call this after sample_frames.

        Returns play_by_play, sport_guess (dunk, soccer, or unclear), key_moments, and notes.
        """
        if done := _already_done(ctx):
            return done
        ctx.deps.note("describe_video")
        return await video_tools.describe_video(frame_paths, clip_label)

    @agent.tool
    async def score_dunk(
        ctx: RunContext[JudgeDeps],
        frame_paths: list[str],
        description: str,
        clip_label: str,
    ) -> dict[str, Any]:
        """Score a basketball dunk. Requires the frames and the text description.

        Call this only when the clip is a dunk. Returns a DunkVerdict.
        """
        if done := _already_done(ctx):
            return done
        ctx.deps.note("score_dunk")
        verdict = await video_tools.score_dunk(frame_paths, description, clip_label)
        ctx.deps.verdict = verdict
        return {
            "status": "recorded",
            "message": "Stop. Submit this verdict as the final result. Do not call any tool again.",
            "verdict": verdict.model_dump(),
        }

    @agent.tool
    async def call_foul(
        ctx: RunContext[JudgeDeps],
        frame_paths: list[str],
        description: str,
        clip_label: str,
    ) -> dict[str, Any]:
        """Call a soccer foul, flop, or no-call. Requires the frames and the text description.

        Call this only when the clip is soccer contact. Returns a FoulVerdict.
        """
        if done := _already_done(ctx):
            return done
        ctx.deps.note("call_foul")
        verdict = await video_tools.call_foul(frame_paths, description, clip_label)
        ctx.deps.verdict = verdict
        return {
            "status": "recorded",
            "message": "Stop. Submit this verdict as the final result. Do not call any tool again.",
            "verdict": verdict.model_dump(),
        }

    @agent.output_validator
    def _use_tool_verdict(ctx: RunContext[JudgeDeps], data: Verdict) -> Verdict:
        names = [event["name"] for event in ctx.deps.tool_events]
        if "sample_frames" not in names or "describe_video" not in names:
            raise ModelRetry("Call sample_frames, then describe_video, then score_dunk or call_foul.")
        if "score_dunk" not in names and "call_foul" not in names:
            raise ModelRetry("Call exactly one of score_dunk or call_foul after describe_video.")
        if ctx.deps.verdict is not None:
            return ctx.deps.verdict
        return data

    return agent


_AGENT: Agent[JudgeDeps, Verdict] | None = None


def _get_agent() -> Agent[JudgeDeps, Verdict]:
    global _AGENT
    if _AGENT is None:
        _AGENT = _build_agent()
    return _AGENT


def run_agent(video_path: str, on_tool: OnTool | None = None) -> dict[str, Any]:
    """Judge one clip. on_tool(name) runs as each tool starts."""
    deps = JudgeDeps(on_tool=on_tool)
    print(f"  model -> {video_tools.MODEL_NAME} via Portkey (judge)", flush=True)
    try:
        result = _get_agent().run_sync(
            f"Judge this clip. Video path: {video_path}",
            deps=deps,
            usage_limits=UsageLimits(request_limit=8),
        )
    except UsageLimitExceeded:
        if deps.verdict is None:
            raise
        result = None
    verdict = deps.verdict if deps.verdict is not None else result.output
    return {
        "verdict": verdict,
        "tool_events": list(deps.tool_events),
    }


def main() -> None:
    video_path = " ".join(sys.argv[1:]).strip()
    if not video_path:
        raise SystemExit("Usage: python agent.py videos/dunks/howard_1.mp4")
    payload = run_agent(video_path)
    verdict = payload["verdict"]
    dumped = verdict.model_dump() if hasattr(verdict, "model_dump") else verdict
    print(dumped)
    print("tools:", [event["name"] for event in payload["tool_events"]])


if __name__ == "__main__":
    main()
