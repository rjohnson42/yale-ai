"""Tools for the Campus Customs agent.

Product identification never opens catalogue photos one at a time, and never
puts more than MAX_IMAGES_PER_REQUEST images into a single model call.
"""

from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.messages import BinaryImage
from pydantic_ai.models.openai import OpenAIChatModel

from build_catalogue import EMBEDDING_MODEL
from models import (
    AdEffectiveness,
    Catalogue,
    CatalogueEntry,
    CustomerProfile,
    ProductIdentification,
    RankedProduct,
)

ROOT = Path(__file__).resolve().parent
CATALOGUE_PATH = ROOT / "output" / "catalogue.json"

MAX_IMAGES_PER_REQUEST = 10
# Evenly spaced frames from an ad. Under the 10-image cap, enough to see the spot.
MAX_AD_FRAMES = 8
# gpt-5.6 reasons at medium effort unless told otherwise. A shirt read does not
# need that, and medium reasoning is what made each photo take minutes.
FAST_MODEL_SETTINGS = {"timeout": 90, "openai_reasoning_effort": "none"}
# Leave one slot for the photo under review.
MAX_CANDIDATE_IMAGES = MAX_IMAGES_PER_REQUEST - 1
TOP_CLIP_AGREE = 3
CLIP_AGREE_SIMILARITY = 0.70

STOPWORDS = {
    "yale",
    "university",
    "the",
    "of",
    "and",
    "for",
    "with",
    "shirt",
    "college",
    "school",
}

GARMENT_ALIASES: list[tuple[str, tuple[str, ...]]] = [
    ("quarter-zip", ("quarter-zip", "quarter zip", "1/4 zip", "1/4-zip")),
    ("full-zip hoodie", ("full-zip", "full zip")),
    ("fleece jacket", ("fleece jacket",)),
    ("bomber jacket", ("bomber",)),
    ("fleece sweater", ("fleece sweater",)),
    ("mockneck", ("mockneck", "mock neck", "mock-neck")),
    ("hoodie", ("hoodie", "hooded")),
    ("crewneck", ("crewneck", "crew neck", "crew-neck", "sweatshirt")),
    ("long sleeve", ("long sleeve", "long-sleeve", "longsleeve")),
    ("t-shirt", ("t-shirt", "tshirt", "t shirt", "tee")),
]


class GarmentObservation(BaseModel):
    """What a vision model can read off the clothing, before any catalogue guess."""

    yale_or_college_mark_visible: bool = Field(
        description="True only if the garment itself shows a Yale, college, school, sport, or family design."
    )
    readable_text: str = Field(description="Text printed on the clothing, quoted. Empty string if none is readable.")
    garment_type: str = Field(description="Cut of the worn garment, such as t-shirt, hoodie, or long sleeve.")
    color: str = Field(description="Rough color of that garment.")
    notes: str = Field(description="One sentence. Do not invent a catalogue product id.")


class VisionPick(BaseModel):
    """The model's choice among a handful of catalogue photos already retrieved."""

    product_found: bool
    product_id: str | None = None
    confidence: float = Field(description="From 0 to 1.")
    reason: str


@dataclass
class ScoredProduct:
    entry: CatalogueEntry
    similarity: float
    rank: int


@dataclass
class CatalogueIndex:
    entries: list[CatalogueEntry]
    matrix: np.ndarray


_index: CatalogueIndex | None = None
_clip_model: object | None = None


def load_catalogue_index() -> CatalogueIndex:
    """Load catalogue vectors once. Later searches are a single matrix multiply."""
    global _index
    if _index is not None:
        return _index
    if not CATALOGUE_PATH.is_file():
        raise SystemExit(
            f"Missing {CATALOGUE_PATH}. Run build_catalogue.py before identifying products."
        )
    catalogue = Catalogue.model_validate_json(CATALOGUE_PATH.read_text(encoding="utf-8"))
    if catalogue.embedding_model != EMBEDDING_MODEL:
        raise SystemExit(
            f"Catalogue was built with {catalogue.embedding_model}, "
            f"but identification expects {EMBEDDING_MODEL}."
        )
    matrix = np.asarray([entry.embedding for entry in catalogue.entries], dtype=np.float32)
    _index = CatalogueIndex(entries=list(catalogue.entries), matrix=matrix)
    return _index


def _clip():
    global _clip_model
    if _clip_model is None:
        import torch
        from sentence_transformers import SentenceTransformer

        if torch.backends.mps.is_available():
            device = "mps"
        elif torch.cuda.is_available():
            device = "cuda"
        else:
            device = "cpu"
        print(f"model={EMBEDDING_MODEL} device={device} task=embed_query", flush=True)
        _clip_model = SentenceTransformer(EMBEDDING_MODEL, device=device)
    return _clip_model


def query_crops(image: Image.Image) -> list[Image.Image]:
    """Full frame plus a few overlapping windows, so a shirt is not lost in the background."""
    width, height = image.size
    windows = [image]
    for fraction in (0.45, 0.70):
        win_w = max(int(width * fraction), 64)
        win_h = max(int(height * fraction), 64)
        step_x = max(win_w // 2, 1)
        step_y = max(win_h // 2, 1)
        for top in range(0, max(height - win_h, 0) + 1, step_y):
            for left in range(0, max(width - win_w, 0) + 1, step_x):
                windows.append(image.crop((left, top, left + win_w, top + win_h)))
    return windows


def rank_catalogue(image_path: Path) -> list[ScoredProduct]:
    """Score every product at once. Does not send any image to the language model."""
    index = load_catalogue_index()
    with Image.open(image_path) as image:
        windows = query_crops(image.convert("RGB"))
    vectors = _clip().encode(
        windows,
        batch_size=32,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    crop_vectors = np.asarray(vectors, dtype=np.float32)
    # (crops, dim) @ (dim, products) -> best score per product, in one shot.
    best = (crop_vectors @ index.matrix.T).max(axis=0)
    order = np.argsort(-best)
    ranked: list[ScoredProduct] = []
    for rank, index_pos in enumerate(order, start=1):
        ranked.append(
            ScoredProduct(
                entry=index.entries[int(index_pos)],
                similarity=float(best[int(index_pos)]),
                rank=rank,
            )
        )
    return ranked


def binary_image(path: Path) -> BinaryImage:
    media = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(path.suffix.lower())
    if media is None:
        raise SystemExit(f"Unsupported image type for {path.name}.")
    return BinaryImage(data=path.read_bytes(), media_type=media)


def image_safety_instructions() -> str:
    """Load the explicit Safety section. Vision calls see pixels, so they load it too."""
    path = ROOT / "prompts" / "prompt.md"
    text = path.read_text(encoding="utf-8")
    marker = "## Safety"
    if marker not in text:
        raise RuntimeError(
            "prompts/prompt.md has no ## Safety section. Refusing to send a photo to the model."
        )
    return text[text.index(marker) :].strip()


async def _vision(
    model: OpenAIChatModel,
    model_name: str,
    call_name: str,
    output_type: type[BaseModel],
    parts: list[str | BinaryImage],
) -> BaseModel:
    images = [part for part in parts if isinstance(part, BinaryImage)]
    if len(images) > MAX_IMAGES_PER_REQUEST:
        raise RuntimeError(
            f"Refusing to send {len(images)} images in one request. "
            f"The cap is {MAX_IMAGES_PER_REQUEST}."
        )
    print(f"model={model_name} call={call_name} images={len(images)}", flush=True)
    agent = Agent(model, output_type=output_type, retries=1, name=call_name)
    agent.instructions = image_safety_instructions()
    result = await agent.run(parts, model_settings=FAST_MODEL_SETTINGS)
    return result.output


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 2 and token not in STOPWORDS
    }


def canonicalize_garment(text: str) -> str | None:
    lowered = text.lower()
    for name, aliases in GARMENT_ALIASES:
        if any(alias in lowered for alias in aliases):
            return name
    return None


def match_by_text(
    ranked: list[ScoredProduct], readable_text: str, garment_hint: str
) -> list[ScoredProduct]:
    """Narrow the catalogue with words and cut. This does not look at pixels."""
    wanted = _tokens(readable_text)
    if not wanted:
        return []
    hits = [
        item
        for item in ranked
        if wanted & _tokens(f"{item.entry.theme} {item.entry.name}")
    ]
    garment = canonicalize_garment(garment_hint)
    if garment is None:
        return hits
    same_cut = [item for item in hits if item.entry.garment_type == garment]
    return same_cut or hits


def _as_ranked(items: list[ScoredProduct]) -> list[RankedProduct]:
    return [
        RankedProduct(
            product_id=item.entry.product_id,
            name=item.entry.name,
            garment_type=item.entry.garment_type,
            theme=item.entry.theme,
            primary_color=item.entry.primary_color,
            similarity=round(item.similarity, 4),
        )
        for item in items
    ]


def _clamp_confidence(value: float) -> float:
    if value > 1:
        value = value / 100 if value <= 100 else 1.0
    return round(max(0.0, min(1.0, float(value))), 4)


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def _result(
    image_path: Path,
    *,
    found: ScoredProduct | None,
    matched_by: str,
    confidence: float,
    reason: str,
    readable_text: str,
    images_sent: int,
    vision_model: str,
    shortlist: list[ScoredProduct],
    nearest: ScoredProduct | None,
) -> ProductIdentification:
    entry = found.entry if found else None
    similarity = found.similarity if found else (nearest.similarity if nearest else None)
    return ProductIdentification(
        query_image=_relative(image_path),
        product_found=entry is not None,
        product_id=entry.product_id if entry else None,
        product_name=entry.name if entry else None,
        garment_type=entry.garment_type if entry else None,
        theme=entry.theme if entry else None,
        primary_color=entry.primary_color if entry else None,
        confidence=_clamp_confidence(confidence),
        clip_similarity=round(similarity, 4) if similarity is not None else None,
        matched_by=matched_by,
        readable_text=readable_text,
        reason=reason,
        images_sent=images_sent,
        vision_model=vision_model,
        shortlist=_as_ranked(shortlist),
    )


async def _confirm(
    model: OpenAIChatModel,
    model_name: str,
    image_path: Path,
    candidates: list[ScoredProduct],
) -> VisionPick:
    shown = candidates[:MAX_CANDIDATE_IMAGES]
    allowed = {item.entry.product_id for item in shown}
    parts: list[str | BinaryImage] = [
        (
            "Image 1 is the photo under review. Each later image is one Campus Customs "
            "catalogue shot. Choose a product_id only when that catalogue shot is the same "
            "design as the garment being worn: same graphic or wording, and a compatible cut. "
            "A flat studio photo and a person wearing the shirt still count as the same design. "
            "A shared color, or a Yale building in the background, is not enough. "
            "If none match, set product_found to false and product_id to null. "
            f"Allowed product ids: {', '.join(sorted(allowed))}."
        ),
        binary_image(image_path),
    ]
    for item in shown:
        entry = item.entry
        parts.append(
            f"Next image is product_id `{entry.product_id}` ({entry.name}), "
            f"{entry.garment_type}, {entry.primary_color}, theme {entry.theme}."
        )
        parts.append(binary_image(ROOT / entry.image_path))
    pick = await _vision(model, model_name, "confirm_product", VisionPick, parts)
    assert isinstance(pick, VisionPick)
    if pick.product_found and pick.product_id not in allowed:
        pick = VisionPick(
            product_found=False,
            product_id=None,
            confidence=0.0,
            reason=(
                f"The model returned {pick.product_id}, which was not in the shortlist. "
                "Treated as no match."
            ),
        )
    return pick


async def identify_product(
    image_path: Path,
    model: OpenAIChatModel,
    model_name: str,
) -> ProductIdentification:
    """Decide whether a Campus Customs product is in the photo, and which one."""
    if not image_path.is_file():
        raise SystemExit(f"Image not found: {image_path}")

    ranked = rank_catalogue(image_path)
    shortlist = ranked[:MAX_CANDIDATE_IMAGES]
    nearest = ranked[0] if ranked else None
    images_sent = 0

    observation = await _vision(
        model,
        model_name,
        "read_garment",
        GarmentObservation,
        [
            (
                "Look only at clothing worn by people in this photo. "
                "Quote any text printed on the garment. "
                "Set yale_or_college_mark_visible true only when the garment itself shows "
                "Yale, a residential college, a Yale school, a Yale sport, or a Yale family "
                "design such as Mom or Dad. A Yale building or sign in the background does not count. "
                "Do not guess a catalogue product id."
            ),
            binary_image(image_path),
        ],
    )
    assert isinstance(observation, GarmentObservation)
    images_sent = 1

    text_hits = match_by_text(ranked, observation.readable_text, observation.garment_type)
    agree = [
        item
        for item in text_hits
        if item.rank <= TOP_CLIP_AGREE and item.similarity >= CLIP_AGREE_SIMILARITY
    ]
    if len(text_hits) == 1 and agree:
        chosen = text_hits[0]
        return _result(
            image_path,
            found=chosen,
            matched_by="text",
            confidence=max(0.75, chosen.similarity),
            reason=(
                f"Clothing reads “{observation.readable_text}” "
                f"({observation.garment_type}). That matches {chosen.entry.product_id}, "
                f"and the local vector search ranks it {chosen.rank} "
                f"(similarity {chosen.similarity:.2f}). No further catalogue images were sent."
            ),
            readable_text=observation.readable_text,
            images_sent=images_sent,
            vision_model=model_name,
            shortlist=shortlist,
            nearest=nearest,
        )

    if text_hits:
        candidates = text_hits[:MAX_CANDIDATE_IMAGES]
        matched_by = "text"
    elif observation.yale_or_college_mark_visible:
        candidates = shortlist
        matched_by = "clip"
    else:
        neighbor = (
            f" Nearest catalogue neighbor is {nearest.entry.product_id} "
            f"at similarity {nearest.similarity:.2f}."
            if nearest
            else ""
        )
        return _result(
            image_path,
            found=None,
            matched_by="none",
            confidence=0.85,
            reason=(
                "No Campus Customs wording on the clothing, and no Yale mark on the garment."
                + neighbor
            ),
            readable_text=observation.readable_text,
            images_sent=images_sent,
            vision_model=model_name,
            shortlist=shortlist,
            nearest=nearest,
        )

    pick = await _confirm(model, model_name, image_path, candidates)
    images_sent = max(images_sent, 1 + min(len(candidates), MAX_CANDIDATE_IMAGES))
    chosen = next((item for item in candidates if item.entry.product_id == pick.product_id), None)
    if not pick.product_found or chosen is None:
        return _result(
            image_path,
            found=None,
            matched_by="none",
            confidence=_clamp_confidence(pick.confidence),
            reason=pick.reason,
            readable_text=observation.readable_text,
            images_sent=images_sent,
            vision_model=model_name,
            shortlist=shortlist,
            nearest=nearest,
        )
    return _result(
        image_path,
        found=chosen,
        matched_by=matched_by,
        confidence=_clamp_confidence(pick.confidence),
        reason=pick.reason,
        readable_text=observation.readable_text,
        images_sent=images_sent,
        vision_model=model_name,
        shortlist=shortlist,
        nearest=nearest,
    )


class AdJudgment(BaseModel):
    """What the vision model decides from the sampled frames and the profile text."""

    effective: bool
    score: float = Field(description="From 0 to 1.")
    would_visit: bool = Field(description="Would this customer come shop at Campus Customs after the ad?")
    reason: str
    strengths: list[str]
    mismatches: list[str]


def load_customer_profile(path: Path) -> tuple[str, str]:
    """Read and validate a customer profile. Returns the name and the JSON text."""
    if not path.is_file():
        raise SystemExit(f"Customer profile not found: {path}")
    try:
        profile = CustomerProfile.model_validate_json(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Customer profile is not valid JSON: {path} ({exc})") from exc
    except ValueError as exc:
        raise SystemExit(f"Customer profile does not match CustomerProfile: {path} ({exc})") from exc
    text = profile.model_dump_json(indent=2)
    if len(text) > 6_000:
        text = text[:6_000] + "\n…"
    return profile.name, text


def _shrink_frame(image: Image.Image, max_side: int = 640) -> Image.Image:
    image = image.convert("RGB")
    width, height = image.size
    scale = max_side / max(width, height)
    if scale < 1:
        image = image.resize((int(width * scale), int(height * scale)), Image.Resampling.LANCZOS)
    return image


def _ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise SystemExit(
            "Missing imageio-ffmpeg. Install the hw3 requirements before judging an ad."
        ) from exc
    return imageio_ffmpeg.get_ffmpeg_exe()


def _video_duration_sec(path: Path) -> float:
    import subprocess

    proc = subprocess.run(
        [_ffmpeg_exe(), "-i", str(path), "-f", "null", "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", proc.stderr)
    if match is None:
        raise SystemExit(f"Could not read the duration of {path.name}.")
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def sample_ad_frames(path: Path, limit: int = MAX_AD_FRAMES) -> tuple[list[Image.Image], list[float]]:
    """Evenly sample a few frames. Does not send them anywhere yet."""
    import subprocess

    if not path.is_file():
        raise SystemExit(f"Video not found: {path}")
    limit = max(1, min(limit, MAX_IMAGES_PER_REQUEST))
    duration = _video_duration_sec(path)
    if duration <= 0:
        raise SystemExit(f"Video has no duration: {path.name}")
    if limit == 1:
        timestamps = [0.0]
    else:
        last = max(duration - 0.05, 0.0)
        timestamps = [round(last * i / (limit - 1), 2) for i in range(limit)]
    frames: list[Image.Image] = []
    ffmpeg = _ffmpeg_exe()
    for timestamp in timestamps:
        proc = subprocess.run(
            [
                ffmpeg,
                "-ss",
                f"{timestamp:.2f}",
                "-i",
                str(path),
                "-frames:v",
                "1",
                "-f",
                "image2pipe",
                "-vcodec",
                "mjpeg",
                "-q:v",
                "3",
                "pipe:1",
            ],
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0 or not proc.stdout:
            raise SystemExit(f"Could not read a frame at {timestamp:.2f}s from {path.name}.")
        with Image.open(io.BytesIO(proc.stdout)) as image:
            frames.append(_shrink_frame(image))
    return frames, timestamps


def match_ad_to_catalogue(frames: list[Image.Image], k: int = 5) -> list[ScoredProduct]:
    """Score the whole catalogue against the sampled frames in one multiply."""
    if not frames:
        return []
    index = load_catalogue_index()
    vectors = _clip().encode(
        frames,
        batch_size=MAX_AD_FRAMES,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    frame_vectors = np.asarray(vectors, dtype=np.float32)
    best = (frame_vectors @ index.matrix.T).max(axis=0)
    order = np.argsort(-best)
    matched: list[ScoredProduct] = []
    for rank, index_pos in enumerate(order, start=1):
        if len(matched) >= k:
            break
        similarity = float(best[int(index_pos)])
        if similarity < 0.22:
            break
        matched.append(
            ScoredProduct(
                entry=index.entries[int(index_pos)],
                similarity=similarity,
                rank=rank,
            )
        )
    return matched


def _frame_binary(image: Image.Image) -> BinaryImage:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=80)
    return BinaryImage(data=buffer.getvalue(), media_type="image/jpeg")


async def judge_ad_effectiveness(
    video_path: Path,
    profile_path: Path,
    model: OpenAIChatModel,
    model_name: str,
) -> AdEffectiveness:
    """Judge whether this ad would bring this customer into Campus Customs."""
    label, profile_text = load_customer_profile(profile_path)
    frames, timestamps = sample_ad_frames(video_path)
    if len(frames) > MAX_IMAGES_PER_REQUEST:
        raise RuntimeError(
            f"Refusing to send {len(frames)} frames. The cap is {MAX_IMAGES_PER_REQUEST}."
        )
    matches = match_ad_to_catalogue(frames)
    neighbor_lines = [
        (
            f"- {item.entry.product_id}: {item.entry.name}, {item.entry.garment_type}, "
            f"theme {item.entry.theme}, similarity {item.similarity:.2f}"
        )
        for item in matches
    ] or ["- none above the similarity floor"]
    parts: list[str | BinaryImage] = [
        (
            "The images are evenly spaced frames from one Campus Customs ad, in time order. "
            "Judge whether this ad would make the customer below more likely to come shop at "
            "Campus Customs. Use only the profile and what is visible in the frames. "
            "The catalogue lines are visual neighbors from a local search, not a confirmed product list. "
            "Score from 0 to 1.\n\n"
            f"Customer profile ({label}):\n{profile_text}\n\n"
            "Closest catalogue items:\n" + "\n".join(neighbor_lines)
        )
    ]
    for timestamp, frame in zip(timestamps, frames):
        parts.append(f"Frame at {timestamp:.2f}s.")
        parts.append(_frame_binary(frame))
    judgment = await _vision(model, model_name, "judge_ad", AdJudgment, parts)
    assert isinstance(judgment, AdJudgment)
    return AdEffectiveness(
        video_path=_relative(video_path),
        profile_path=_relative(profile_path),
        customer_summary=label,
        effective=judgment.effective,
        score=_clamp_confidence(judgment.score),
        would_visit=judgment.would_visit,
        reason=judgment.reason,
        strengths=judgment.strengths,
        mismatches=judgment.mismatches,
        catalogue_matches=_as_ranked(matches),
        frame_timestamps_sec=timestamps,
        frames_sent=len(frames),
        vision_model=model_name,
    )
