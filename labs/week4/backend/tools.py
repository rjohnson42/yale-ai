"""Catalog search and public web search for the Yale SOM agent."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from db import fetch_courses
from models import Course, CourseMatch, SearchCoursesResult, WebSearchHit, WebSearchResult
RESULT_CAP = 15
WEB_CAP = 5
DESCRIPTION_LIMIT = 420
BIO_LIMIT = 320

_DAY_NAMES = {
    "monday": "M",
    "mon": "M",
    "m": "M",
    "tuesday": "T",
    "tue": "T",
    "tues": "T",
    "t": "T",
    "wednesday": "W",
    "wed": "W",
    "w": "W",
    "thursday": "Th",
    "thu": "Th",
    "thur": "Th",
    "thurs": "Th",
    "th": "Th",
    "friday": "F",
    "fri": "F",
    "f": "F",
}


def load_courses() -> list[Course]:
    """Load catalog rows from the courses table in data/yale_som.db."""
    return fetch_courses()


def _clip(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


def _day_code(day: str) -> str | None:
    return _DAY_NAMES.get(day.strip().lower())


def _meeting_days(course: Course) -> set[str]:
    head = re.split(r"\d", course.daytimes, maxsplit=1)[0]
    return set(re.findall(r"Th|[MTWF]", head))


def _number_matches(course_number: str, needle: str) -> bool:
    wanted = re.sub(r"\s+", "", needle).lower()
    if not wanted:
        return True
    compact = re.sub(r"\s+", "", course_number).lower()
    if wanted.isdigit():
        return wanted in re.findall(r"\d+", course_number)
    return wanted in compact


def _contains(haystack: str, needle: str) -> bool:
    return needle.strip().lower() in haystack.lower()


def _token_in(haystack: str, word: str) -> bool:
    """Match a whole word so 'AI' does not hit 'email' or 'available'."""
    text = haystack.lower()
    needle = word.strip().lower()
    if not needle:
        return True
    if re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", text):
        return True
    return needle == "ai" and "artificial intelligence" in text


def _matches(course: Course, **filters: str) -> bool:
    query = filters.get("query", "").strip()
    if query:
        blob = " ".join(
            [
                course.number,
                course.title,
                course.faculty,
                course.faculty_email,
                course.category,
                course.course_type,
                course.daytimes,
                course.day,
                course.room,
                course.session,
                course.description,
            ]
        )
        if not all(_token_in(blob, word) for word in query.split()):
            return False
    if filters.get("title") and not _contains(course.title, filters["title"]):
        return False
    if filters.get("number") and not _number_matches(course.number, filters["number"]):
        return False
    if filters.get("faculty") and not (
        _contains(course.faculty, filters["faculty"])
        or _contains(course.faculty_email, filters["faculty"])
    ):
        return False
    if filters.get("category") and not _contains(course.category, filters["category"]):
        return False
    if filters.get("course_type") and not _contains(course.course_type, filters["course_type"]):
        return False
    day = filters.get("day", "").strip()
    if day:
        code = _day_code(day) or day
        if code not in _meeting_days(course) and not _contains(course.daytimes, day):
            return False
    return True


def _match_row(course: Course) -> CourseMatch:
    return CourseMatch(
        number=course.number,
        section=course.section,
        title=course.title,
        faculty=course.faculty,
        faculty_email=course.faculty_email,
        category=course.category,
        course_type=course.course_type,
        daytimes=course.daytimes,
        room=course.room,
        session=course.session,
        units=course.units,
        description=_clip(course.description, DESCRIPTION_LIMIT),
        faculty_bio=_clip(course.faculty_bio, BIO_LIMIT),
    )


def search_courses(
    query: str = "",
    title: str = "",
    number: str = "",
    faculty: str = "",
    category: str = "",
    day: str = "",
    course_type: str = "",
    limit: int = RESULT_CAP,
) -> SearchCoursesResult:
    """Query the courses table. total_matches is the full count; courses is capped."""
    filters = {
        "query": query,
        "title": title,
        "number": number,
        "faculty": faculty,
        "category": category,
        "day": day,
        "course_type": course_type,
    }
    if not any(value.strip() for value in filters.values()):
        return SearchCoursesResult(
            query="",
            total_matches=0,
            returned=0,
            courses=[],
            note="Pass a query or a field such as number, faculty, category, or day.",
        )
    matched = [course for course in load_courses() if _matches(course, **filters)]
    cap = max(1, min(int(limit), RESULT_CAP))
    shown = matched[:cap]
    note = ""
    if len(matched) > len(shown):
        note = (
            f"Showing {len(shown)} of {len(matched)}. "
            "Use total_matches for counts; do not count only the returned rows."
        )
    label = " ".join(f"{key}={value.strip()}" for key, value in filters.items() if value.strip())
    return SearchCoursesResult(
        query=label,
        total_matches=len(matched),
        returned=len(shown),
        courses=[_match_row(course) for course in shown],
        note=note,
    )


def _unwrap_ddg_url(href: str) -> str:
    parsed = urlparse(href)
    uddg = parse_qs(parsed.query).get("uddg", [])
    if uddg:
        return unquote(uddg[0])
    if href.startswith("//"):
        return "https:" + href
    return href


class _DuckDuckGoParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._mode: str | None = None
        self._href = ""
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: value or "" for key, value in attrs}
        classes = attr.get("class", "")
        if tag == "a" and "result__a" in classes:
            self._mode = "title"
            self._href = attr.get("href", "")
            self._buf = []
        elif "result__snippet" in classes:
            self._mode = "snippet"
            self._buf = []

    def handle_endtag(self, tag: str) -> None:
        if self._mode is None:
            return
        if self._mode == "title" and tag == "a":
            title = " ".join("".join(self._buf).split())
            if title:
                self.results.append(
                    {"title": title, "url": _unwrap_ddg_url(self._href), "snippet": ""}
                )
            self._mode = None
        elif self._mode == "snippet" and tag in {"a", "td", "div"}:
            snippet = " ".join("".join(self._buf).split())
            if snippet and self.results and not self.results[-1]["snippet"]:
                self.results[-1]["snippet"] = snippet
            self._mode = None

    def handle_data(self, data: str) -> None:
        if self._mode:
            self._buf.append(data)


def web_search(query: str, max_results: int = WEB_CAP) -> WebSearchResult:
    """Search the public web. Use when the courses table is not enough."""
    cleaned = query.strip()
    if not cleaned:
        return WebSearchResult(query="", results=[], note="Pass a non-empty query.")
    cap = max(1, min(int(max_results), WEB_CAP))
    try:
        response = httpx.post(
            "https://html.duckduckgo.com/html/",
            data={"q": cleaned},
            headers={"User-Agent": "Mozilla/5.0 (compatible; YaleSOMCourseExplorer/0.1)"},
            timeout=20.0,
            follow_redirects=True,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        return WebSearchResult(query=cleaned, results=[], note=f"Web search failed: {exc}")
    parser = _DuckDuckGoParser()
    parser.feed(response.text)
    hits = [
        WebSearchHit(title=row["title"], url=row["url"], snippet=_clip(row["snippet"], 280))
        for row in parser.results
        if row["title"] and row["url"].startswith("http")
    ][:cap]
    note = "" if hits else "No public web results came back for that query."
    return WebSearchResult(query=cleaned, results=hits, note=note)
