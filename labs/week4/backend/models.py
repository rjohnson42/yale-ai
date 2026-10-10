"""Types for the Yale SOM course catalog agent."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Course(BaseModel):
    """One row of data/yale_som_classes.json."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    bid_or_permission: str = Field(default="", alias="Bid Or Permission")
    category: str = Field(default="", alias="Course Category")
    description: str = Field(default="", alias="Course Description")
    course_id: str = Field(default="", alias="Course ID")
    number: str = Field(default="", alias="Course Number")
    session: str = Field(default="", alias="Course Session")
    session_end: str = Field(default="", alias="Course Session End Date")
    session_start: str = Field(default="", alias="Course Session Start date")
    title: str = Field(default="", alias="Course Title")
    course_type: str = Field(default="", alias="Course Type")
    daytimes: str = Field(default="", alias="Daytimes")
    faculty: str = Field(default="", alias="Faculty 1")
    faculty_email: str = Field(default="", alias="Faculty 1 Email")
    old_syllabus: str = Field(default="", alias="Old Syllabus")
    room: str = Field(default="", alias="Room")
    section: str = Field(default="", alias="Section")
    syllabus: str = Field(default="", alias="Syllabus")
    term_code: str = Field(default="", alias="TermCode")
    units: str = Field(default="", alias="Units")
    visible: str = Field(default="", alias="Visible")
    start_time: str = Field(default="", alias="Timings StartTime")
    end_time: str = Field(default="", alias="Timings EndTime")
    day: str = Field(default="", alias="Timings Day")
    faculty_bio: str = Field(default="", alias="faculty_bio")

    @field_validator("*", mode="before")
    @classmethod
    def _strip(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class CourseMatch(BaseModel):
    """A catalog row trimmed for the model. The full row stays on Course."""

    number: str
    section: str
    title: str
    faculty: str
    faculty_email: str
    category: str
    course_type: str
    daytimes: str
    room: str
    session: str
    units: str
    description: str
    faculty_bio: str


class SearchCoursesResult(BaseModel):
    query: str
    total_matches: int
    returned: int
    courses: list[CourseMatch]
    note: str = ""


class WebSearchHit(BaseModel):
    title: str
    url: str
    snippet: str


class WebSearchResult(BaseModel):
    query: str
    results: list[WebSearchHit]
    note: str = ""


class AgentResult(BaseModel):
    reply: str
    tools_used: list[str] = Field(default_factory=list)


class UserPublic(BaseModel):
    id: int
    email: str
    name: str


class AuthResponse(BaseModel):
    token: str
    user: UserPublic


class SavedMessage(BaseModel):
    id: int
    role: str
    text: str
    tools: list[str] = Field(default_factory=list)
    created_at: str


class AuditedToolCall(BaseModel):
    tool_name: str
    args: dict[str, str]
    short_result: str


class AuditEntry(BaseModel):
    time: datetime
    user_message: str
    thoughts: str
    tool_calls: list[AuditedToolCall]
    stop_reason: str
    model: str
