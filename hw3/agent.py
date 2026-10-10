#!/usr/bin/env python3
"""Campus Customs agent.

    python agent.py --image "data/test_images/example.jpg"
    python agent.py --video "data/videos/ad_humble.mp4" --profile "profiles/profile_student.json"

Run from hw3/ with the project venv. The system prompt is loaded from
prompts/prompt.md. Tools live in tools.py.
"""

from __future__ import annotations

import os

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext, UsageLimits, capture_run_messages
from pydantic_ai.messages import ModelResponse, TextPart, ThinkingPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from models import AdEffectiveness, AuditEntry, AuditedToolCall, ProductIdentification
from tools import FAST_MODEL_SETTINGS, identify_product
from tools import judge_ad_effectiveness as score_ad

ROOT = Path(__file__).resolve().parent
PROMPT_PATH = ROOT / "prompts" / "prompt.md"
OUTPUT_PATH = ROOT / "output" / "identify_product.json"
AD_OUTPUT_PATH = ROOT / "output" / "ad_effectiveness.json"
AUDIT_PATH = ROOT / "output" / "audit_trail.json"
SAFETY_HEADING = "## Safety"


@dataclass
class AgentDeps:
    model: OpenAIChatModel
    model_name: str
    image_path: Path | None = None
    video_path: Path | None = None
    profile_path: Path | None = None
    identification: ProductIdentification | None = None
    ad_effectiveness: AdEffectiveness | None = None


campus_agent = Agent(
    deps_type=AgentDeps,
    output_type=ProductIdentification | AdEffectiveness,
    name="campus_customs",
    retries=1,
)


@campus_agent.tool
async def identify_campus_product(ctx: RunContext[AgentDeps]) -> str:
    """Decide if the given photo shows a Campus Customs product, and which one.

    The image path comes from the command line, not from the model.
    """
    if ctx.deps.image_path is None:
        raise RuntimeError("No photo was passed on the command line.")
    found = await identify_product(ctx.deps.image_path, ctx.deps.model, ctx.deps.model_name)
    ctx.deps.identification = found
    return found.model_dump_json()


@campus_agent.tool
async def judge_ad_effectiveness(ctx: RunContext[AgentDeps]) -> str:
    """Judge whether the given ad would bring this customer in to shop.

    The video path and profile path come from the command line, not from the model.
    """
    if ctx.deps.video_path is None or ctx.deps.profile_path is None:
        raise RuntimeError("Ad effectiveness needs --video and --profile.")
    verdict = await score_ad(
        ctx.deps.video_path,
        ctx.deps.profile_path,
        ctx.deps.model,
        ctx.deps.model_name,
    )
    ctx.deps.ad_effectiveness = verdict
    return verdict.model_dump_json()


def load_env() -> None:
    load_dotenv(ROOT / ".env", override=True)


def build_model() -> tuple[OpenAIChatModel, str]:
    portkey_key = os.environ.get("PORTKEY_API_KEY")
    if not portkey_key:
        sys.exit(
            "No Portkey key found. Set PORTKEY_API_KEY in hw3/.env (see .env.example)."
        )
    model_name = os.environ.get("LLM_MODEL", "gpt-5.6-luna")
    try:
        from portkey_ai import PORTKEY_GATEWAY_URL
    except ImportError:
        sys.exit("Missing dependency portkey-ai. Install with: pip install portkey-ai")
    base_url = os.environ.get("PORTKEY_BASE_URL", PORTKEY_GATEWAY_URL)
    provider = OpenAIProvider(base_url=base_url, api_key=portkey_key)
    return OpenAIChatModel(model_name, provider=provider), model_name


def load_system_prompt() -> str:
    path = PROMPT_PATH
    if not path.is_file():
        sys.exit(f"Missing system prompt: {PROMPT_PATH}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        sys.exit(f"System prompt is empty: {path}")
    if SAFETY_HEADING not in text:
        sys.exit(
            f"{path.name} has no '{SAFETY_HEADING}' section. "
            "The agent will not run until that section is in the system prompt."
        )
    return text


def resolve_path(raw: str, kind: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    if not path.is_file():
        sys.exit(f"{kind} not found: {path}")
    return path


def relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def clip_text(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


def tool_args_for_run(tool_name: str, raw_args: object, deps: AgentDeps) -> dict[str, str]:
    """Paths the tool actually used. The model is not allowed to pass image bytes."""
    parsed: dict[str, object] = {}
    if isinstance(raw_args, dict):
        parsed = raw_args
    elif isinstance(raw_args, str) and raw_args.strip():
        try:
            loaded = json.loads(raw_args)
        except json.JSONDecodeError:
            loaded = {"raw": raw_args}
        if isinstance(loaded, dict):
            parsed = loaded
        else:
            parsed = {"raw": loaded}
    args = {str(key): clip_text(value if isinstance(value, str) else json.dumps(value), 180) for key, value in parsed.items()}
    if tool_name == "identify_campus_product" and deps.image_path is not None:
        args["image"] = relative_path(deps.image_path)
    if tool_name == "judge_ad_effectiveness":
        if deps.video_path is not None:
            args["video"] = relative_path(deps.video_path)
        if deps.profile_path is not None:
            args["profile"] = relative_path(deps.profile_path)
    return args


def short_tool_result(content: object) -> str:
    """A few decision fields. The audit does not keep the photo or the full JSON."""
    data: object = content
    if isinstance(content, str):
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return clip_text(content, 240)
    if isinstance(data, dict) and "product_found" in data:
        return (
            f"product_found={data.get('product_found')} "
            f"product_id={data.get('product_id')} "
            f"confidence={data.get('confidence')} "
            f"images_sent={data.get('images_sent')}"
        )
    if isinstance(data, dict) and "effective" in data and "score" in data:
        return (
            f"effective={data.get('effective')} score={data.get('score')} "
            f"would_visit={data.get('would_visit')} frames_sent={data.get('frames_sent')}"
        )
    if isinstance(data, str):
        return clip_text(data, 240)
    return clip_text(json.dumps(data), 240)


def audit_from_messages(
    messages: list[object],
    deps: AgentDeps,
    stop_reason: str,
    when: datetime,
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
                    args=tool_args_for_run(part.tool_name, part.args, deps),
                    short_result="",
                )
            elif isinstance(part, ToolReturnPart):
                summary = short_tool_result(part.content)
                existing = calls.get(part.tool_call_id)
                if existing is None:
                    order.append(part.tool_call_id)
                    calls[part.tool_call_id] = AuditedToolCall(
                        tool_name=part.tool_name,
                        args=tool_args_for_run(part.tool_name, None, deps),
                        short_result=summary,
                    )
                else:
                    existing.short_result = summary
    thought_text = clip_text(" ".join(thoughts), 800) if thoughts else (
        "No thinking text was returned. Reasoning is off, so this run has no separate chain of thought."
    )
    if stop_reason == "completed":
        stop_reason = finish_reason or "stop"
    return AuditEntry(
        time=when,
        thoughts=thought_text,
        tool_calls=[calls[tool_id] for tool_id in order],
        stop_reason=clip_text(stop_reason, 400),
    )


def append_audit(entry: AuditEntry) -> None:
    """Add one row. Never replace the file with only the new row."""
    saved: list[AuditEntry] = []
    if AUDIT_PATH.is_file() and AUDIT_PATH.stat().st_size > 0:
        try:
            raw = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            sys.exit(f"Refusing to rewrite {AUDIT_PATH.name}: it is not valid JSON ({exc}).")
        items = raw if isinstance(raw, list) else [raw]
        saved = [AuditEntry.model_validate(item) for item in items]
    saved.append(entry)
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = [item.model_dump(mode="json") for item in saved]
    AUDIT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def run_once(prompt: str, deps: AgentDeps) -> str:
    """Run the agent and append one audit row, including when the final answer errors."""
    when = datetime.now(timezone.utc)
    stop_reason = "completed"
    with capture_run_messages() as messages:
        try:
            campus_agent.run_sync(
                prompt,
                deps=deps,
                usage_limits=UsageLimits(request_limit=4, tool_calls_limit=1),
                model_settings=FAST_MODEL_SETTINGS,
            )
        except Exception as exc:
            stop_reason = f"{type(exc).__name__}: {exc}"
            if deps.identification is None and deps.ad_effectiveness is None:
                append_audit(audit_from_messages(messages, deps, stop_reason, when))
                raise
            print(f"Saved the tool result after the final answer failed: {exc}", flush=True)
    append_audit(audit_from_messages(messages, deps, stop_reason, when))
    return stop_reason


def review_image(
    image_path: Path,
    model: OpenAIChatModel,
    model_name: str,
) -> ProductIdentification:
    """Run the agent once. The tool result is the saved review."""
    deps = AgentDeps(image_path=image_path, model=model, model_name=model_name)
    print(f"model={model_name} task=identify_product image={image_path.name}", flush=True)
    run_once(
        (
            "Decide whether this photo shows a person wearing a Campus Customs product, "
            "and which product if you can tell. Follow the Safety section. "
            "Call identify_campus_product once, then return that result unchanged."
        ),
        deps,
    )
    if deps.identification is None:
        sys.exit(f"The agent finished without calling identify_campus_product for {image_path.name}.")
    found = ProductIdentification.model_validate(deps.identification.model_dump())
    print(
        f"model={model_name} image={image_path.name} product_found={found.product_found} "
        f"product_id={found.product_id} images_sent={found.images_sent}",
        flush=True,
    )
    return found


def write_ad_verdict(verdict: AdEffectiveness) -> None:
    """Keep every profile's verdict in one file. A rerun replaces that profile only."""
    saved: list[AdEffectiveness] = []
    if AD_OUTPUT_PATH.is_file():
        raw = json.loads(AD_OUTPUT_PATH.read_text(encoding="utf-8"))
        items = raw if isinstance(raw, list) else [raw]
        saved = [AdEffectiveness.model_validate(item) for item in items]
    saved = [item for item in saved if item.profile_path != verdict.profile_path]
    saved.append(verdict)
    AD_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps([item.model_dump() for item in saved], indent=2)
    AD_OUTPUT_PATH.write_text(text + "\n", encoding="utf-8")


def write_reviews(reviews: list[ProductIdentification]) -> None:
    """Keep earlier photo reviews. A rerun replaces the same photo and leaves the rest."""
    existing: list[ProductIdentification] = []
    if OUTPUT_PATH.is_file() and OUTPUT_PATH.stat().st_size > 0:
        raw = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        items = raw if isinstance(raw, list) else [raw]
        existing = [ProductIdentification.model_validate(item) for item in items]
    by_image = {item.query_image: item for item in existing}
    for review in reviews:
        by_image[review.query_image] = review
    ordered: list[ProductIdentification] = []
    seen: set[str] = set()
    for item in existing:
        if item.query_image not in seen:
            ordered.append(by_image[item.query_image])
            seen.add(item.query_image)
    for review in reviews:
        if review.query_image not in seen:
            ordered.append(review)
            seen.add(review.query_image)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if len(ordered) == 1:
        text = ordered[0].model_dump_json(indent=2)
    else:
        text = json.dumps([review.model_dump() for review in ordered], indent=2)
    OUTPUT_PATH.write_text(text + "\n", encoding="utf-8")


def review_ad(
    video_path: Path,
    profile_path: Path,
    model: OpenAIChatModel,
    model_name: str,
) -> AdEffectiveness:
    """Run the agent once. The tool result is the saved verdict."""
    deps = AgentDeps(
        model=model,
        model_name=model_name,
        video_path=video_path,
        profile_path=profile_path,
    )
    print(
        f"model={model_name} task=judge_ad video={video_path.name} profile={profile_path.name}",
        flush=True,
    )
    run_once(
        (
            "Judge how effective this ad would be at getting this customer to come shop "
            "at Campus Customs. Follow the Safety section. "
            "Call judge_ad_effectiveness once, then return that result unchanged."
        ),
        deps,
    )
    if deps.ad_effectiveness is None:
        sys.exit("The agent finished without calling judge_ad_effectiveness.")
    verdict = AdEffectiveness.model_validate(deps.ad_effectiveness.model_dump())
    if verdict.frames_sent > 10:
        sys.exit(f"Ad judgment sent {verdict.frames_sent} frames. The cap is 10.")
    print(
        f"model={model_name} effective={verdict.effective} score={verdict.score} "
        f"frames_sent={verdict.frames_sent}",
        flush=True,
    )
    return verdict


def main() -> None:
    parser = argparse.ArgumentParser(description="Campus Customs product and ad agent.")
    parser.add_argument(
        "--image",
        nargs="+",
        help='One or more photo paths, for example "data/test_images/example.jpg".',
    )
    parser.add_argument("--video", help='Ad video path, for example "data/videos/ad_humble.mp4".')
    parser.add_argument(
        "--profile",
        help='Customer profile JSON, for example "profiles/profile_student.json".',
    )
    args = parser.parse_args()
    has_images = bool(args.image)
    has_ad = bool(args.video or args.profile)
    if has_images and has_ad:
        sys.exit("Use either --image or --video with --profile, not both.")
    if has_ad and not (args.video and args.profile):
        sys.exit("Ad effectiveness needs both --video and --profile.")
    if not has_images and not has_ad:
        sys.exit("Pass --image, or --video and --profile.")

    image_paths = [resolve_path(raw, "Image") for raw in args.image] if has_images else []
    video_path = resolve_path(args.video, "Video") if has_ad else None
    profile_path = resolve_path(args.profile, "Profile") if has_ad else None

    load_env()
    model, model_name = build_model()
    campus_agent.model = model
    campus_agent.instructions = load_system_prompt()

    if has_ad:
        assert video_path is not None and profile_path is not None
        verdict = review_ad(video_path, profile_path, model, model_name)
        write_ad_verdict(verdict)
        print(f"Wrote {AD_OUTPUT_PATH.relative_to(ROOT)}", flush=True)
        return

    reviews: list[ProductIdentification] = []
    for image_path in image_paths:
        reviews.append(review_image(image_path, model, model_name))
        write_reviews(reviews)
    print(f"Wrote {len(reviews)} review(s) to {OUTPUT_PATH.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
