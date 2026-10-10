"""Structured outputs for the sports video judge."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DunkScores(BaseModel):
    """Each category is an integer from 0 (poor) to 10 (elite)."""

    height: int = Field(ge=0, le=10)
    creativity: int = Field(ge=0, le=10)
    difficulty: int = Field(ge=0, le=10)
    landing: int = Field(ge=0, le=10)


class DunkVerdict(BaseModel):
    kind: Literal["dunk"] = "dunk"
    clip_label: str
    scores: DunkScores
    total: int = Field(ge=0, le=40)
    play_by_play: str
    rationale: str
    frame_paths: list[str]


class FoulVerdict(BaseModel):
    kind: Literal["foul"] = "foul"
    clip_label: str
    call: Literal["foul", "flop", "no_call"]
    confidence: float = Field(ge=0, le=1)
    play_by_play: str
    rationale: str
    frame_paths: list[str]


class ClipDescription(BaseModel):
    play_by_play: str
    sport_guess: Literal["dunk", "soccer", "unclear"]
    key_moments: list[str]
    notes: str


class DunkScoreDraft(BaseModel):
    """What the model fills in. kind, label, frames, and total are set in code."""

    scores: DunkScores
    play_by_play: str
    rationale: str


class FoulCallDraft(BaseModel):
    """What the model fills in. kind, label, and frames are set in code."""

    call: Literal["foul", "flop", "no_call"]
    confidence: float = Field(ge=0, le=1)
    play_by_play: str
    rationale: str
