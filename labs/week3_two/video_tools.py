"""Frame sampling and the vision steps the judge agent calls."""

from __future__ import annotations

import asyncio
import io
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from openai import AsyncOpenAI  # noqa: E402
from PIL import Image  # noqa: E402
from pydantic_ai import Agent, BinaryContent  # noqa: E402
from pydantic_ai.models.openai import OpenAIChatModel  # noqa: E402
from pydantic_ai.providers.openai import OpenAIProvider  # noqa: E402

import imageio.v3 as iio  # noqa: E402

from models import ClipDescription, DunkScoreDraft, DunkVerdict, FoulCallDraft, FoulVerdict  # noqa: E402

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
FRAMES = HERE / "frames"
PROMPTS = HERE / "prompts"

load_dotenv(PARENT / ".env")
load_dotenv(HERE / ".env", override=True)

MODEL_NAME = os.environ.get("LLM_MODEL", "gpt-5.6-luna")
PORTKEY_BASE_URL = os.environ.get("PORTKEY_BASE_URL", "https://api.portkey.ai/v1")
MAX_SIDE = 768
MAX_FRAMES_CAP = 16
# Luna rejects reasoning_effort other than "none" when a request uses tools,
# and the default effort is what left score_dunk sitting on the socket.
VISION_TIMEOUT_SEC = 75
VISION_SETTINGS = {"openai_reasoning_effort": "none", "timeout": VISION_TIMEOUT_SEC}
_MODEL: OpenAIChatModel | None = None


def _require_key() -> str:
    key = os.environ.get("PORTKEY_API_KEY")
    if not key:
        raise RuntimeError(
            "PORTKEY_API_KEY is not set. Add it to "
            f"{HERE / '.env'} or {PARENT / '.env'}."
        )
    return key


def get_model() -> OpenAIChatModel:
    global _MODEL
    if _MODEL is None:
        key = _require_key()
        client = AsyncOpenAI(
            base_url=PORTKEY_BASE_URL,
            api_key=key,
            timeout=VISION_TIMEOUT_SEC,
            default_headers={"x-portkey-api-key": key},
        )
        _MODEL = OpenAIChatModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))
    return _MODEL


def _prompt(name: str) -> str:
    path = PROMPTS / name
    if not path.is_file():
        raise RuntimeError(f"Missing prompt file: {path}")
    return path.read_text(encoding="utf-8")


def _resolve_frame(raw: str) -> Path:
    path = Path(raw)
    if path.is_file():
        return path
    candidate = HERE / raw
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(f"Missing frame file: {raw}")


def _contact_sheet(frame_paths: list[str]) -> bytes:
    """Pack every still into one JPEG so the model gets one image, not a dozen."""
    if not frame_paths:
        raise ValueError("frame_paths is required and cannot be empty.")
    thumbs: list[Image.Image] = []
    for raw in frame_paths:
        image = Image.open(_resolve_frame(raw)).convert("RGB")
        image.thumbnail((240, 240))
        thumbs.append(image)
    cols = min(4, len(thumbs))
    rows = (len(thumbs) + cols - 1) // cols
    cell_w = max(image.width for image in thumbs)
    cell_h = max(image.height for image in thumbs)
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), (12, 12, 16))
    for index, image in enumerate(thumbs):
        row, col = divmod(index, cols)
        x = col * cell_w + (cell_w - image.width) // 2
        y = row * cell_h + (cell_h - image.height) // 2
        sheet.paste(image, (x, y))
    buffer = io.BytesIO()
    sheet.save(buffer, format="JPEG", quality=70)
    return buffer.getvalue()


def _frame_parts(frame_paths: list[str]) -> list[str | BinaryContent]:
    sheet = _contact_sheet(frame_paths)
    print(
        f"  frames -> {len(frame_paths)} stills as one {len(sheet) // 1024}KB sheet",
        flush=True,
    )
    return [
        (
            f"Contact sheet of {len(frame_paths)} frames in time order, "
            "left to right, then top to bottom."
        ),
        BinaryContent(sheet, media_type="image/jpeg"),
    ]


async def _ask(agent: Agent[None, Any], parts: list[str | BinaryContent], label: str) -> Any:
    print(f"  model -> {MODEL_NAME} via Portkey ({label})", flush=True)
    try:
        result = await asyncio.wait_for(agent.run(parts), timeout=VISION_TIMEOUT_SEC + 15)
    except TimeoutError as exc:
        raise RuntimeError(
            f"{label} did not finish within {VISION_TIMEOUT_SEC} seconds. Press Judge to try again."
        ) from exc
    print(f"  model -> {label} done", flush=True)
    return result.output


def sample_frames(
    video_path: str,
    every_n_sec: float = 0.5,
    max_frames: int = 16,
) -> dict[str, Any]:
    """Save JPEG stills under frames/<stem>/ and return their relative paths."""
    if every_n_sec <= 0:
        raise ValueError("every_n_sec must be greater than 0.")
    max_frames = max(1, min(int(max_frames), MAX_FRAMES_CAP))

    source = Path(video_path)
    if not source.is_file():
        raise FileNotFoundError(f"Missing clip file: {video_path}")

    meta = iio.immeta(source)
    fps = float(meta.get("fps") or 0)
    duration = float(meta.get("duration") or 0)
    if fps <= 0 or duration <= 0:
        raise RuntimeError(f"Could not read fps/duration for {source.name}.")

    times: list[float] = []
    cursor = 0.0
    while cursor < duration and len(times) < max_frames:
        times.append(cursor)
        cursor += every_n_sec
    if not times:
        times = [0.0]

    last_index = max(0, int(duration * fps) - 1)
    indices: list[int] = []
    for stamp in times:
        index = min(last_index, int(round(stamp * fps)))
        if not indices or index != indices[-1]:
            indices.append(index)

    out_dir = FRAMES / source.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("frame_*.jpg"):
        old.unlink()

    saved: list[str] = []
    for slot, index in enumerate(indices):
        frame = iio.imread(source, index=index)
        image = Image.fromarray(frame[..., :3] if frame.ndim == 3 and frame.shape[-1] == 4 else frame)
        image.thumbnail((MAX_SIDE, MAX_SIDE))
        dest = out_dir / f"frame_{slot:02d}.jpg"
        image.save(dest, format="JPEG", quality=80)
        saved.append(dest.relative_to(HERE).as_posix())

    return {
        "clip_label": source.name,
        "frame_paths": saved,
        "frame_count": len(saved),
        "duration_sec": round(duration, 2),
        "every_n_sec": every_n_sec,
    }


async def describe_video(frame_paths: list[str], clip_label: str) -> dict[str, Any]:
    """Look at the stills and return a play-by-play plus a sport guess."""
    if not str(clip_label).strip():
        raise ValueError("clip_label is required.")
    agent: Agent[None, ClipDescription] = Agent(
        get_model(),
        output_type=ClipDescription,
        instructions=_prompt("describe.md"),
        model_settings=VISION_SETTINGS,
        retries=0,
    )
    parts: list[str | BinaryContent] = [
        f"Clip label (do not treat this as evidence of the sport): {clip_label}",
        *_frame_parts(frame_paths),
    ]
    described = await _ask(agent, parts, "describe_video")
    if not isinstance(described, ClipDescription):
        described = ClipDescription.model_validate(described)
    return described.model_dump()


async def score_dunk(frame_paths: list[str], description: str, clip_label: str) -> DunkVerdict:
    """Score a dunk from the stills and the text description."""
    text = (description or "").strip()
    label = (clip_label or "").strip()
    if not text:
        raise ValueError("description is required.")
    if not label:
        raise ValueError("clip_label is required.")
    agent: Agent[None, DunkScoreDraft] = Agent(
        get_model(),
        output_type=DunkScoreDraft,
        instructions=_prompt("score_dunk.md"),
        model_settings=VISION_SETTINGS,
        retries=0,
    )
    parts: list[str | BinaryContent] = [
        f"Clip label: {label}",
        f"Description:\n{text}",
        *_frame_parts(frame_paths),
    ]
    draft = await _ask(agent, parts, "score_dunk")
    if not isinstance(draft, DunkScoreDraft):
        draft = DunkScoreDraft.model_validate(draft)
    scores = draft.scores
    return DunkVerdict(
        clip_label=label,
        scores=scores,
        total=scores.height + scores.creativity + scores.difficulty + scores.landing,
        play_by_play=draft.play_by_play,
        rationale=draft.rationale,
        frame_paths=list(frame_paths),
    )


async def call_foul(frame_paths: list[str], description: str, clip_label: str) -> FoulVerdict:
    """Call a soccer contact clip from the stills and the text description."""
    text = (description or "").strip()
    label = (clip_label or "").strip()
    if not text:
        raise ValueError("description is required.")
    if not label:
        raise ValueError("clip_label is required.")
    agent: Agent[None, FoulCallDraft] = Agent(
        get_model(),
        output_type=FoulCallDraft,
        instructions=_prompt("call_foul.md"),
        model_settings=VISION_SETTINGS,
        retries=0,
    )
    parts: list[str | BinaryContent] = [
        f"Clip label: {label}",
        f"Description:\n{text}",
        *_frame_parts(frame_paths),
    ]
    draft = await _ask(agent, parts, "call_foul")
    if not isinstance(draft, FoulCallDraft):
        draft = FoulCallDraft.model_validate(draft)
    return FoulVerdict(
        clip_label=label,
        call=draft.call,
        confidence=draft.confidence,
        play_by_play=draft.play_by_play,
        rationale=draft.rationale,
        frame_paths=list(frame_paths),
    )
