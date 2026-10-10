"""Structured types for the Campus Customs agent.

These are Pydantic models, the same kind of schema a PydanticAI agent
validates. Nothing in this module calls a language model.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CatalogueEntry(BaseModel):
    """One Campus Customs product, ready for visual search."""

    product_id: str = Field(description="Stable id, the photo filename without its extension.")
    name: str = Field(description="Human-readable product name derived from the filename.")
    image_path: str = Field(description="Path to the studio photo, relative to the hw3 folder.")
    garment_type: str = Field(
        description="Cut of the garment, such as hoodie, crewneck, or t-shirt."
    )
    collection: str = Field(
        description="Merchandising line: college, school, sport, family, brand, or campus."
    )
    theme: str = Field(
        description="Who or what the graphic is for, such as Morse College, Mom, or Hockey."
    )
    brand: str | None = Field(
        description="Licensed brand when the filename names one. House goods use null."
    )
    primary_color: str = Field(
        description="Coarse garment color from the photo, ignoring the studio background."
    )
    description: str = Field(description="One-sentence summary built only from the fields above.")
    embedding: list[float] = Field(
        description="L2-normalized CLIP image vector. Compare with a dot product."
    )
    embedding_model: str = Field(description="Model that produced the embedding.")
    embedding_dim: int = Field(description="Length of the embedding vector.")


class Catalogue(BaseModel):
    """Every product photo, plus the embedding settings used to build it."""

    embedding_model: str
    embedding_dim: int
    normalized: bool = Field(description="True when every vector has length 1.")
    product_count: int
    entries: list[CatalogueEntry]


class RankedProduct(BaseModel):
    """One catalogue neighbor from the local vector search. No embedding stored."""

    product_id: str
    name: str
    garment_type: str
    theme: str
    primary_color: str
    similarity: float = Field(description="Dot product against the best local crop of the query photo.")


class ProductIdentification(BaseModel):
    """Whether a photo shows a Campus Customs product, and which one if we can tell."""

    query_image: str = Field(description="Photo that was judged, relative to the hw3 folder when possible.")
    product_found: bool = Field(description="True only when a specific catalogue product is worn in the photo.")
    product_id: str | None = Field(description="Catalogue id of that product, or null when none is identified.")
    product_name: str | None = None
    garment_type: str | None = None
    theme: str | None = None
    primary_color: str | None = None
    confidence: float = Field(description="0 to 1. How sure the decision is.")
    clip_similarity: float | None = Field(
        description="Vector similarity of the chosen product, or of the nearest neighbor when nothing is chosen."
    )
    matched_by: str = Field(description="text, clip, or none. How the product id was chosen.")
    readable_text: str = Field(description="Words the vision model read on the clothing. Empty if none.")
    reason: str
    images_sent: int = Field(description="Images in the largest single model request. Never above 10.")
    vision_model: str
    shortlist: list[RankedProduct] = Field(
        description="Top visual neighbors. The model is not shown the rest of the catalogue."
    )


class CustomerProfile(BaseModel):
    """Who an ad is for. Fields line up with the catalogue so a video can be scored against them."""

    name: str = Field(description="Short label, used as the customer summary.")
    segment: Literal["student", "parent"]
    summary: str = Field(description="A few sentences on this typical person.")
    relationship_to_yale: str = Field(description="How they are tied to Yale, not a specific biography.")
    who_they_buy_for: list[str] = Field(description="self, their student, gifts, and so on.")
    occasions: list[str] = Field(description="Moments when they actually shop for Yale gear.")
    preferred_collections: list[str] = Field(
        description="Catalogue collections that fit: college, school, sport, family, brand, campus."
    )
    preferred_themes: list[str] = Field(description="Subjects inside those collections that should resonate.")
    avoid_themes: list[str] = Field(description="Subjects that would make the ad feel aimed at someone else.")
    preferred_garments: list[str] = Field(description="Cuts they would actually wear or give.")
    price_sensitivity: Literal["high", "medium", "low"] = Field(
        description="high means a tight budget. low means price is not the main objection."
    )
    tone_that_resonates: list[str] = Field(description="Mood the ad should have for this person.")
    tone_that_misses: list[str] = Field(description="Mood that would push them away.")


class AdEffectiveness(BaseModel):
    """How well one ad video would move one customer to shop at Campus Customs."""

    video_path: str = Field(description="Ad that was judged, relative to the hw3 folder when possible.")
    profile_path: str = Field(description="Customer profile JSON used for the judgment.")
    customer_summary: str = Field(description="Short label for who the profile describes.")
    effective: bool = Field(description="True when the ad is a good reason for this customer to visit.")
    score: float = Field(description="0 to 1. Higher means more likely to bring this customer in.")
    would_visit: bool = Field(description="True when we would expect this person to come shop after seeing the ad.")
    reason: str
    strengths: list[str] = Field(description="What in the ad fits this customer.")
    mismatches: list[str] = Field(description="What in the ad misses this customer.")
    catalogue_matches: list[RankedProduct] = Field(
        description="Closest catalogue items across the sampled frames. Not a frame-by-frame scan."
    )
    frame_timestamps_sec: list[float] = Field(description="Where the sampled frames sit in the video.")
    frames_sent: int = Field(description="Frames in the single judgment request. Never above 10.")
    vision_model: str


class AuditedToolCall(BaseModel):
    """One tool call inside an audit row. Paths only. Never image bytes."""

    tool_name: str
    args: dict[str, str] = Field(
        description="Arguments the tool ran with, mostly file paths. Long values are cut."
    )
    short_result: str = Field(
        description="A few fields from the tool result, such as product_found or score. Not the full payload."
    )


class AuditEntry(BaseModel):
    """One appended row in output/audit_trail.json. A later run does not remove earlier rows."""

    time: datetime = Field(description="When this run was recorded, UTC.")
    thoughts: str = Field(
        description="What the model said it was doing before the tool. Empty thinking is stated, not invented."
    )
    tool_calls: list[AuditedToolCall] = Field(
        description="Tool name, args, and a short result for each call in this run."
    )
    stop_reason: str = Field(
        description="Why the run ended: the model finish reason, or the error if a limit or failure stopped it."
    )
