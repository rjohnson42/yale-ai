#!/usr/bin/env python3
"""PydanticAI sales agent: profile a site, or find customer targets and draft emails.

Run from hw2/ (use the project venv; Playwright needs Python 3.12):

    .venv/bin/python sales_agent.py "Build a profile of this company." --url https://sierra.ai
    .venv/bin/python sales_agent.py "Find 3 good customer targets for this company and draft outreach emails." --profile assets/company_profile.json
"""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import os
import re
import socket
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin, urlparse

from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError
from pydantic_ai import (
    Agent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelRetry,
    PartDeltaEvent,
    PartStartEvent,
    RunContext,
    UsageLimitExceeded,
    UsageLimits,
)
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

HW2_ROOT = Path(__file__).resolve().parent
PROMPT_PATH = HW2_ROOT / "prompts" / "sales_agent.md"
SELLER_BRIEF_PATH = HW2_ROOT / "assets" / "seller_brief.md"
DEFAULT_PROFILE_PATH = HW2_ROOT / "assets" / "company_profile.json"
AUDIT_LOG_PATH = HW2_ROOT / "output" / "audit_log.json"
DEFAULT_TARGETS_PATH = HW2_ROOT / "output" / "targets.json"
DEFAULT_EMAILS_PATH = HW2_ROOT / "output" / "emails.json"

MAX_PAGES_PROFILE = 6
MAX_PAGES_TARGETS = 12
MAX_SEARCHES = 3
MAX_ALLOWLIST_HOSTS = 10
MAX_PAGE_CHARS = 8_000
MAX_LINKS_RETURNED = 25
PAGE_TIMEOUT_MS = 25_000
REQUEST_LIMIT_PROFILE = 10
TOOL_CALLS_LIMIT_PROFILE = 8
REQUEST_LIMIT_TARGETS = 18
TOOL_CALLS_LIMIT_TARGETS = 22
RESULT_SUMMARY_CHARS = 700
EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)
URL_RE = re.compile(r"https?://[^\s)\]>'\"<>]+", re.I)

BLOCKED_HOST_SUFFIXES = ("localhost",)
BLOCKED_HOSTS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "metadata.google.internal",
}

# Not usable as a customer-company homepage from web search.
SKIP_RESULT_HOSTS = {
    "linkedin.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "wikipedia.org",
    "youtube.com",
    "reddit.com",
    "crunchbase.com",
    "bloomberg.com",
    "techcrunch.com",
    "google.com",
    "bing.com",
}

COMPETITOR_HOSTS = {
    "decagon.ai",
    "ada.cx",
    "fin.ai",
    "intercom.com",
    "zendesk.com",
    "gorgias.com",
    "kore.ai",
    "cognigy.ai",
    "lorikeet.ai",
    "forethought.ai",
    "sierra.ai",
}

PREFERRED_PATHS = (
    "/about",
    "/product",
    "/products",
    "/platform",
    "/customers",
    "/solutions",
    "/support",
    "/help",
    "/careers",
    "/contact",
    "/security",
    "/trust",
    "/pricing",
)


# ---------------------------------------------------------------------------
# Profile schema (mirrors prompts/sales_agent.md)
# ---------------------------------------------------------------------------


class SourceClaim(BaseModel):
    claim: str
    source_url: str


class SourceEvidence(BaseModel):
    evidence: str
    source_url: str


class ProductItem(BaseModel):
    name: str
    description: str | None = None
    value_proposition: str | None = None
    source_url: str | None = None


class Geography(BaseModel):
    headquarters: str | None = None
    offices: list[str] | str | None = None
    markets_served: list[str] | str | None = None


class RegulatedSignals(BaseModel):
    signals: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)


class Availability(BaseModel):
    hours_or_24_7: str | None = None
    languages: list[str] | str | None = None
    source_urls: list[str] = Field(default_factory=list)


class NamedPerson(BaseModel):
    name: str
    title: str | None = None
    source_url: str | None = None


class CrawlError(BaseModel):
    url: str
    error: str


class IcpEvidence(BaseModel):
    icp_criterion: str
    site_evidence: str
    source_url: str


class Disqualifier(BaseModel):
    disqualifier: str
    site_evidence: str
    source_url: str


class CompanyProfile(BaseModel):
    company_name: str | None = None
    company_url: str | None = None
    tagline_or_one_liner: str | None = None
    source_urls_crawled: list[str] = Field(default_factory=list)
    crawl_errors: list[CrawlError] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    business_model: str | None = None
    products_and_services: list[ProductItem] = Field(default_factory=list)
    who_they_sell_to: list[str] = Field(default_factory=list)
    geography: Geography | None = None
    founded: str | None = None
    scale_claims: list[SourceClaim] = Field(default_factory=list)
    public_or_private: str | None = None
    regulated_or_brand_sensitive: RegulatedSignals | None = None
    customer_channels: list[str] = Field(default_factory=list)
    support_or_contact_center_evidence: list[SourceEvidence] = Field(default_factory=list)
    helpdesk_or_crm_mentions: list[str] = Field(default_factory=list)
    existing_ai_or_chatbot_mentions: list[SourceEvidence] = Field(default_factory=list)
    complex_journeys: list[str] = Field(default_factory=list)
    systems_of_record_mentions: list[str] = Field(default_factory=list)
    availability_and_language: Availability | None = None
    seasonality_or_peak_load_signals: list[str] = Field(default_factory=list)
    leadership_or_executives_named: list[NamedPerson] = Field(default_factory=list)
    buyer_persona_clues: list[str] = Field(default_factory=list)
    careers_or_hiring_signals: list[dict[str, Any]] = Field(default_factory=list)
    icp_evidence: list[IcpEvidence] = Field(default_factory=list)
    possible_disqualifiers_from_site: list[Disqualifier] = Field(default_factory=list)
    fields_not_found: list[str] = Field(default_factory=list)
    profiled_at: str | None = None


class TargetCompany(BaseModel):
    company_name: str
    company_url: str
    contact_emails: list[str] = Field(default_factory=list)
    mutual_fit_reason: str
    business_context: str
    source_urls: list[str] = Field(default_factory=list)


class TargetsFile(BaseModel):
    seller_name: str | None = None
    seller_url: str | None = None
    created_at: str | None = None
    targets: list[TargetCompany]


class DraftEmail(BaseModel):
    company_name: str
    to_emails: list[str] = Field(default_factory=list)
    subject: str
    body: str
    sent: bool = False


class EmailsFile(BaseModel):
    created_at: str | None = None
    note: str = "Drafts only. Never sent."
    emails: list[DraftEmail]


@dataclass
class AgentDeps:
    seed_url: str | None
    allowed_hosts: set[str]
    blocked_target_hosts: set[str]
    profile_path: Path
    input_profile_path: Path | None
    targets_path: Path
    emails_path: Path
    browser_context: Any
    max_pages: int
    mode: Literal["profile", "targets"]
    pages_fetched: int = 0
    searches_used: int = 0
    fetched_urls: list[str] = field(default_factory=list)
    profile_saved: bool = False
    targets_saved: bool = False
    emails_saved: bool = False


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_env() -> None:
    load_dotenv(HW2_ROOT / ".env", override=True)


def fail_missing_key() -> None:
    sys.exit(
        "No Portkey key found. Set PORTKEY_API_KEY in hw2/.env (see .env.example)."
    )


def canonical_host(netloc: str) -> str:
    host = netloc.lower().split("@")[-1].split(":")[0]
    if host.startswith("www."):
        return host[4:]
    return host


def host_is_blocked(host: str) -> bool:
    host = host.lower().rstrip(".")
    if host in BLOCKED_HOSTS or host.endswith(BLOCKED_HOST_SUFFIXES):
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return True
    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        ):
            return True
    return False


def url_is_allowed(url: str, allowed_hosts: set[str] | None) -> tuple[bool, str]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False, f"blocked scheme: {parsed.scheme or 'missing'}"
    if parsed.username or parsed.password:
        return False, "credentials in URL are not allowed"
    host = canonical_host(parsed.netloc)
    if not host:
        return False, "missing host"
    if host_is_blocked(host):
        return False, f"blocked host {host}"
    if allowed_hosts is not None and host not in allowed_hosts:
        return False, f"off-allowlist host {host}"
    return True, ""


def extract_emails(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for match in EMAIL_RE.findall(text or ""):
        email = match.strip(".,;:()<>").lower()
        host = email.rsplit("@", 1)[-1]
        if host in {"example.com", "email.com", "domain.com", "sentry.io", "wixpress.com"}:
            continue
        if email.startswith(("noreply@", "no-reply@", "donotreply@")):
            continue
        if email not in seen:
            seen.add(email)
            found.append(email)
    return found


def hosts_from_text(text: str, blocked: set[str]) -> list[str]:
    hosts: list[str] = []
    seen: set[str] = set()
    for raw in URL_RE.findall(text or ""):
        cleaned = raw.rstrip(".,;:)")
        parsed = urlparse(cleaned)
        host = canonical_host(parsed.netloc)
        if not host or host in seen or host in blocked or host in SKIP_RESULT_HOSTS:
            continue
        if any(host == skip or host.endswith("." + skip) for skip in SKIP_RESULT_HOSTS):
            continue
        ok, _ = url_is_allowed(cleaned if parsed.scheme else f"https://{host}", None)
        if not ok:
            continue
        seen.add(host)
        hosts.append(host)
    return hosts


def summarize(value: Any, limit: int = RESULT_SUMMARY_CHARS) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    text = text.replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def load_system_prompt() -> str:
    if not PROMPT_PATH.is_file():
        sys.exit(f"Missing system prompt: {PROMPT_PATH}")
    prompt = PROMPT_PATH.read_text(encoding="utf-8").strip()
    brief = ""
    if SELLER_BRIEF_PATH.is_file():
        brief = SELLER_BRIEF_PATH.read_text(encoding="utf-8").strip()
    guardrails = f"""

## Runtime guardrails

You are running inside `sales_agent.py`. Be safe and cheap:

- Read the human query first and pick Task A (profile) or Task B (targets + draft emails).
- Profile mode: crawl only with `fetch_page` on the seed host. At most {MAX_PAGES_PROFILE} pages. Do not call `web_search`. Then `save_company_profile` once.
- Target mode: `read_company_profile` first, then at most {MAX_SEARCHES} `web_search` calls (prefer one good query), then `fetch_page` only on allowlisted candidate homepages (max {MAX_PAGES_TARGETS} pages total). Then `save_targets` and `save_emails` once each.
- Never invent facts or email addresses. Never send email.
- Do not click, log in, fill forms, or download files.
- Keep tool args small. Do not paste entire pages back in later tool calls.

## Seller brief (ICP labels only; do not copy Sierra metrics into a prospect profile as if they were that prospect's facts)

{brief}
"""
    return prompt + guardrails


def build_user_prompt(
    query: str,
    url: str | None,
    profile_out: Path,
    input_profile: Path | None,
    targets_path: Path,
    emails_path: Path,
    mode: str,
) -> str:
    lines = [
        f"Human query:\n{query.strip()}",
        "",
        "Keyword args:",
    ]
    if url:
        lines.append(f"- urls: [{url}]")
        lines.append(f"- seed_url: {url}")
    lines.append(f"- out_path: {profile_out}")
    if input_profile:
        lines.append(f"- profile: {input_profile}")
    lines.append(f"- targets_path: {targets_path}")
    lines.append(f"- emails_path: {emails_path}")
    lines.append("")
    if mode == "targets":
        lines.append(
            "This is a customer-target request. Read the profile, search the web, "
            "keep only mutual-fit companies, crawl their sites for context and contact "
            "email, draft unsent outreach, then save targets.json and emails.json."
        )
    else:
        lines.append(
            "This is a company-profile request. "
            f"Fetch the seed URL first, then same-origin pages such as {', '.join(PREFERRED_PATHS[:8])}, "
            "then save the profile JSON."
        )
    return "\n".join(lines)


def infer_mode(query: str, has_url: bool, has_profile: bool) -> str:
    q = query.lower()
    target_hints = (
        "target",
        "outreach",
        "email",
        "leads",
        "customers for",
        "customer targets",
        "prospect",
    )
    if any(h in q for h in target_hints):
        return "targets"
    if "profile" in q or has_url and not has_profile:
        return "profile"
    if has_profile and not has_url:
        return "targets"
    return "profile"


def build_model() -> tuple[OpenAIChatModel, str]:
    portkey_key = os.environ.get("PORTKEY_API_KEY")
    if not portkey_key:
        fail_missing_key()
    model_name = os.environ.get("LLM_MODEL", "gpt-5.6-luna")
    try:
        from portkey_ai import PORTKEY_GATEWAY_URL
    except ImportError:
        sys.exit("Missing dependency portkey-ai. Install with: pip install portkey-ai")
    base_url = os.environ.get("PORTKEY_BASE_URL", PORTKEY_GATEWAY_URL)
    provider = OpenAIProvider(base_url=base_url, api_key=portkey_key)
    return OpenAIChatModel(model_name, provider=provider), model_name


def empty_fields(profile: CompanyProfile) -> list[str]:
    empty: list[str] = []
    data = profile.model_dump()
    skip = {"fields_not_found", "profiled_at", "source_urls_crawled", "crawl_errors"}
    for key, value in data.items():
        if key in skip:
            continue
        if value is None or value == [] or value == {}:
            empty.append(key)
    return empty


sales_agent = Agent(
    deps_type=AgentDeps,
    output_type=str,
    name="sales_agent",
)


@sales_agent.tool
async def fetch_page(ctx: RunContext[AgentDeps], url: str) -> str:
    """Fetch one allowlisted page with Playwright and return visible text, links, and emails."""
    ok, reason = url_is_allowed(url, ctx.deps.allowed_hosts)
    if not ok:
        raise ModelRetry(
            f"Refusing to fetch URL ({reason}). Search first or stay on an allowlisted host."
        )
    if ctx.deps.pages_fetched >= ctx.deps.max_pages:
        return (
            f"Page budget exhausted ({ctx.deps.max_pages} pages). Do not fetch more. "
            "Save results from pages already retrieved."
        )

    from playwright.async_api import Error as PlaywrightError

    page = await ctx.deps.browser_context.new_page()
    try:
        response = await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
        await asyncio.sleep(1.5)
        final_url = page.url
        ok_final, reason_final = url_is_allowed(final_url, ctx.deps.allowed_hosts)
        if not ok_final:
            ctx.deps.pages_fetched += 1
            ctx.deps.fetched_urls.append(url)
            return json.dumps(
                {
                    "url": url,
                    "error": f"redirected off-allowlist: {reason_final}",
                    "final_url": final_url,
                }
            )
        status = response.status if response is not None else None
        title = await page.title()
        extracted = await page.evaluate(
            """() => {
              const root = document.body ? document.body.cloneNode(true) : document.documentElement;
              root.querySelectorAll("script,style,noscript,svg,iframe").forEach((n) => n.remove());
              const text = (root.innerText || "").replace(/\\s+\\n/g, "\\n").trim();
              const links = [...document.querySelectorAll("a[href]")]
                .map((a) => a.href)
                .filter(Boolean);
              const mailtos = [...document.querySelectorAll('a[href^="mailto:"]')]
                .map((a) => a.getAttribute("href") || "");
              return { text, links, mailtos };
            }"""
        )
        text = (extracted.get("text") or "")[:MAX_PAGE_CHARS]
        raw_links = extracted.get("links") or []
        mailtos = " ".join(extracted.get("mailtos") or [])
        emails = extract_emails(text + " " + mailtos)
        same_origin: list[str] = []
        seen: set[str] = set()
        page_host = canonical_host(urlparse(final_url).netloc)
        for href in raw_links:
            absolute = urljoin(final_url, href)
            allowed, _ = url_is_allowed(absolute, {page_host})
            if not allowed:
                continue
            cleaned = urlparse(absolute)._replace(fragment="").geturl()
            if cleaned in seen:
                continue
            seen.add(cleaned)
            same_origin.append(cleaned)
            if len(same_origin) >= MAX_LINKS_RETURNED:
                break
        ctx.deps.pages_fetched += 1
        ctx.deps.fetched_urls.append(final_url)
        payload = {
            "requested_url": url,
            "final_url": final_url,
            "http_status": status,
            "title": title,
            "chars": len(text),
            "pages_used": f"{ctx.deps.pages_fetched}/{ctx.deps.max_pages}",
            "emails_found": emails,
            "same_origin_links": same_origin,
            "text": text,
        }
        return json.dumps(payload, ensure_ascii=False)
    except PlaywrightError as exc:
        ctx.deps.pages_fetched += 1
        ctx.deps.fetched_urls.append(url)
        return json.dumps({"url": url, "error": str(exc)})
    finally:
        await page.close()


@sales_agent.tool
async def save_company_profile(ctx: RunContext[AgentDeps], profile: CompanyProfile) -> str:
    """Validate the company profile and write assets/company_profile.json."""
    if ctx.deps.profile_saved:
        return f"Profile already saved to {ctx.deps.profile_path}"
    data = profile.model_copy(deep=True)
    if not data.profiled_at:
        data.profiled_at = now_iso()
    if not data.source_urls_crawled:
        data.source_urls_crawled = list(ctx.deps.fetched_urls)
    missing = empty_fields(data)
    merged = list(dict.fromkeys([*(data.fields_not_found or []), *missing]))
    data.fields_not_found = merged
    path = ctx.deps.profile_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data.model_dump_json(indent=2), encoding="utf-8")
    ctx.deps.profile_saved = True
    return f"Wrote profile to {path} ({len(merged)} fields_not_found)."


@sales_agent.tool
async def read_company_profile(ctx: RunContext[AgentDeps]) -> str:
    """Read the seller company profile JSON passed via --profile."""
    path = ctx.deps.input_profile_path
    if path is None or not path.is_file():
        raise ModelRetry("No company profile file. Pass --profile path/to/company_profile.json")
    raw = path.read_text(encoding="utf-8")
    if len(raw) > 24_000:
        raw = raw[:24_000] + "\n… [truncated]"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        seller_url = data.get("company_url") or ""
        host = canonical_host(urlparse(seller_url).netloc) if seller_url else ""
        if host:
            ctx.deps.blocked_target_hosts.add(host)
    except json.JSONDecodeError:
        pass
    return raw


def _web_search_sync(query: str, model_name: str) -> str:
    from portkey_ai import Portkey

    key = os.environ.get("PORTKEY_API_KEY")
    if not key:
        return json.dumps({"error": "PORTKEY_API_KEY missing"})
    client = Portkey(api_key=key)
    prompt = (
        "Search the public web. Return candidate companies that could BUY this seller's "
        "product (not competitors, not the seller, not random famous brands without fit). "
        "For each, give name, official homepage URL, and a one-line why-they-might-buy. "
        f"Query: {query[:400]}"
    )
    last_error = None
    for tool in (
        {"type": "web_search", "search_context_size": "low"},
        {"type": "web_search_preview", "search_context_size": "low"},
        {"type": "web_search"},
    ):
        try:
            response = client.responses.create(
                model=model_name,
                tools=[tool],
                input=prompt,
            )
            text = getattr(response, "output_text", None) or str(response)
            return text
        except Exception as exc:
            last_error = exc
            continue
    return json.dumps({"error": f"web_search failed: {last_error}"})


@sales_agent.tool
async def web_search(ctx: RunContext[AgentDeps], query: str) -> str:
    """Search the public web via OpenAI (Portkey Responses API). Adds result homepages to the crawl allowlist."""
    if ctx.deps.mode == "profile":
        raise ModelRetry("web_search is not allowed while building a site-only company profile.")
    if ctx.deps.searches_used >= MAX_SEARCHES:
        return f"Search budget exhausted ({MAX_SEARCHES}). Use allowlisted URLs you already have."
    ctx.deps.searches_used += 1
    model_name = os.environ.get("LLM_MODEL", "gpt-5.6-luna")
    text = await asyncio.to_thread(_web_search_sync, query, model_name)
    added: list[str] = []
    for host in hosts_from_text(text, ctx.deps.blocked_target_hosts | COMPETITOR_HOSTS):
        if host in ctx.deps.allowed_hosts:
            continue
        if len(ctx.deps.allowed_hosts) >= MAX_ALLOWLIST_HOSTS:
            break
        ctx.deps.allowed_hosts.add(host)
        added.append(host)
    return json.dumps(
        {
            "searches_used": f"{ctx.deps.searches_used}/{MAX_SEARCHES}",
            "allowlisted_hosts_added": added,
            "allowlisted_hosts": sorted(ctx.deps.allowed_hosts),
            "results": text[:12_000],
        },
        ensure_ascii=False,
    )


@sales_agent.tool
async def save_targets(ctx: RunContext[AgentDeps], payload: TargetsFile) -> str:
    """Write output/targets.json. Drafts only; does not contact anyone."""
    if ctx.deps.targets_saved:
        return f"Targets already saved to {ctx.deps.targets_path}"
    data = payload.model_copy(deep=True)
    if not data.created_at:
        data.created_at = now_iso()
    if len(data.targets) > 5:
        raise ModelRetry("Save at most 5 targets (usually 3). Drop extras.")
    path = ctx.deps.targets_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data.model_dump_json(indent=2), encoding="utf-8")
    ctx.deps.targets_saved = True
    return f"Wrote {len(data.targets)} targets to {path}"


@sales_agent.tool
async def save_emails(ctx: RunContext[AgentDeps], payload: EmailsFile) -> str:
    """Write output/emails.json. Never sends mail (sent is forced false)."""
    if ctx.deps.emails_saved:
        return f"Emails already saved to {ctx.deps.emails_path}"
    data = payload.model_copy(deep=True)
    if not data.created_at:
        data.created_at = now_iso()
    data.note = "Drafts only. Never sent."
    for item in data.emails:
        item.sent = False
    path = ctx.deps.emails_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data.model_dump_json(indent=2), encoding="utf-8")
    ctx.deps.emails_saved = True
    return f"Wrote {len(data.emails)} unsent draft emails to {path}"


def append_audit_run(run_record: dict[str, Any]) -> None:
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any]
    if AUDIT_LOG_PATH.is_file():
        try:
            existing = json.loads(AUDIT_LOG_PATH.read_text(encoding="utf-8"))
            if isinstance(existing, dict) and isinstance(existing.get("runs"), list):
                payload = existing
            else:
                payload = {"script": "sales_agent.py", "runs": []}
        except json.JSONDecodeError:
            payload = {"script": "sales_agent.py", "runs": []}
    else:
        payload = {"script": "sales_agent.py", "runs": []}
    payload["script"] = "sales_agent.py"
    payload["runs"].append(run_record)
    AUDIT_LOG_PATH.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PydanticAI agent: profile a site, or find customer targets and draft emails."
    )
    parser.add_argument("query", help="Natural-language request from the human")
    parser.add_argument(
        "--url",
        default=None,
        help="Seed company URL (same-origin crawl for profile mode)",
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=None,
        help="Existing company_profile.json for customer-target mode",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_PROFILE_PATH,
        help="Profile JSON path (default: assets/company_profile.json)",
    )
    return parser.parse_args()


async def run_agent(
    query: str,
    seed_url: str | None,
    profile_out: Path,
    input_profile: Path | None,
    mode: str,
) -> str:
    allowed_hosts: set[str] = set()
    blocked_target_hosts: set[str] = set(COMPETITOR_HOSTS)
    if seed_url:
        ok, reason = url_is_allowed(seed_url, None)
        if not ok:
            sys.exit(f"Refusing seed URL: {reason}")
        host = canonical_host(urlparse(seed_url).netloc)
        if host_is_blocked(host):
            sys.exit(f"Refusing seed host {host}")
        allowed_hosts.add(host)
        if mode == "profile":
            blocked_target_hosts.add(host)

    if mode == "targets":
        if input_profile is None or not input_profile.is_file():
            sys.exit(
                "Target mode needs --profile pointing at a company profile JSON "
                f"(looked for {input_profile})."
            )
        max_pages = MAX_PAGES_TARGETS
        request_limit = REQUEST_LIMIT_TARGETS
        tool_limit = TOOL_CALLS_LIMIT_TARGETS
    else:
        if not seed_url:
            sys.exit("Profile mode needs --url.")
        max_pages = MAX_PAGES_PROFILE
        request_limit = REQUEST_LIMIT_PROFILE
        tool_limit = TOOL_CALLS_LIMIT_PROFILE

    model, model_name = build_model()
    sales_agent.model = model
    sales_agent.instructions = load_system_prompt()

    from playwright.async_api import async_playwright

    iterations: list[dict[str, Any]] = []
    stop_reason = "unknown"
    output_text = ""
    started = now_iso()
    deps: AgentDeps | None = None
    targets_path = DEFAULT_TARGETS_PATH
    emails_path = DEFAULT_EMAILS_PATH

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                java_script_enabled=True,
                accept_downloads=False,
            )
            deps = AgentDeps(
                seed_url=seed_url,
                allowed_hosts=allowed_hosts,
                blocked_target_hosts=blocked_target_hosts,
                profile_path=profile_out,
                input_profile_path=input_profile,
                targets_path=targets_path,
                emails_path=emails_path,
                browser_context=context,
                max_pages=max_pages,
                mode="targets" if mode == "targets" else "profile",
            )
            limits = UsageLimits(
                request_limit=request_limit,
                tool_calls_limit=tool_limit,
            )
            user_prompt = build_user_prompt(
                query,
                seed_url,
                profile_out,
                input_profile,
                targets_path,
                emails_path,
                mode,
            )
            try:
                async with sales_agent.iter(
                    user_prompt, deps=deps, usage_limits=limits
                ) as agent_run:
                    async for node in agent_run:
                        entry: dict[str, Any] = {
                            "timestamp": now_iso(),
                            "kind": type(node).__name__,
                        }
                        if Agent.is_user_prompt_node(node):
                            entry["thoughts"] = None
                            entry["user_prompt_summary"] = summarize(node.user_prompt)
                            entry["tool_calls"] = []
                        elif Agent.is_model_request_node(node):
                            thoughts: list[str] = []
                            texts: list[str] = []
                            planned_tools: list[dict[str, Any]] = []
                            async with node.stream(agent_run.ctx) as request_stream:
                                async for event in request_stream:
                                    if isinstance(event, PartStartEvent):
                                        part = event.part
                                        part_kind = type(part).__name__
                                        content = getattr(part, "content", None)
                                        if part_kind == "ThinkingPart" and content:
                                            thoughts.append(str(content))
                                        elif part_kind == "TextPart" and content:
                                            texts.append(str(content))
                                        elif part_kind == "ToolCallPart":
                                            planned_tools.append(
                                                {
                                                    "name": getattr(part, "tool_name", None),
                                                    "args": summarize(
                                                        getattr(part, "args", None), 400
                                                    ),
                                                    "result_summary": None,
                                                }
                                            )
                                    elif isinstance(event, PartDeltaEvent):
                                        delta = event.delta
                                        delta_kind = type(delta).__name__
                                        if delta_kind == "ThinkingPartDelta":
                                            chunk = getattr(delta, "content_delta", None)
                                            if chunk:
                                                thoughts.append(str(chunk))
                                        elif delta_kind == "TextPartDelta":
                                            chunk = getattr(delta, "content_delta", None)
                                            if chunk:
                                                texts.append(str(chunk))
                                        elif delta_kind == "ToolCallPartDelta":
                                            args_delta = getattr(delta, "args_delta", None)
                                            if planned_tools and args_delta is not None:
                                                prev = planned_tools[-1].get("args") or ""
                                                planned_tools[-1]["args"] = summarize(
                                                    f"{prev}{args_delta}", 400
                                                )
                            entry["thoughts"] = "".join(thoughts) or None
                            entry["model_text"] = summarize("".join(texts), 1200) or None
                            entry["tool_calls"] = planned_tools
                        elif Agent.is_call_tools_node(node):
                            calls: list[dict[str, Any]] = []
                            by_id: dict[str, dict[str, Any]] = {}
                            async with node.stream(agent_run.ctx) as handle_stream:
                                async for event in handle_stream:
                                    if isinstance(event, FunctionToolCallEvent):
                                        part = event.part
                                        call_id = getattr(part, "tool_call_id", "") or str(
                                            len(calls)
                                        )
                                        rec = {
                                            "name": getattr(part, "tool_name", None),
                                            "args": summarize(getattr(part, "args", None), 500),
                                            "result_summary": None,
                                            "tool_call_id": call_id,
                                        }
                                        by_id[call_id] = rec
                                        calls.append(rec)
                                    elif isinstance(event, FunctionToolResultEvent):
                                        call_id = getattr(event, "tool_call_id", "") or ""
                                        content = getattr(getattr(event, "part", None), "content", None)
                                        rec = by_id.get(call_id)
                                        if rec is None:
                                            rec = {
                                                "name": None,
                                                "args": None,
                                                "result_summary": summarize(content),
                                                "tool_call_id": call_id,
                                            }
                                            calls.append(rec)
                                        else:
                                            rec["result_summary"] = summarize(content)
                            entry["thoughts"] = None
                            entry["tool_calls"] = calls
                        elif Agent.is_end_node(node):
                            stop_reason = "end"
                            entry["thoughts"] = None
                            entry["tool_calls"] = []
                            if agent_run.result is not None:
                                output_text = str(agent_run.result.output)
                                entry["final_output_summary"] = summarize(output_text)
                        iterations.append(entry)
            except UsageLimitExceeded as exc:
                stop_reason = "usage_limit"
                iterations.append(
                    {
                        "timestamp": now_iso(),
                        "kind": "UsageLimitExceeded",
                        "thoughts": None,
                        "tool_calls": [],
                        "result_summary": str(exc),
                    }
                )
                output_text = f"Stopped for cost/safety limits: {exc}"
            finally:
                await context.close()
                await browser.close()
    except Exception as exc:
        stop_reason = "error"
        iterations.append(
            {
                "timestamp": now_iso(),
                "kind": "Error",
                "thoughts": None,
                "tool_calls": [],
                "result_summary": f"{type(exc).__name__}: {exc}",
            }
        )
        raise
    finally:
        append_audit_run(
            {
                "started_at": started,
                "stopped_at": now_iso(),
                "stop_reason": stop_reason,
                "query": query,
                "url": seed_url,
                "mode": mode,
                "model": os.environ.get("LLM_MODEL", "gpt-5.6-luna"),
                "profile_path": str(profile_out),
                "input_profile": str(input_profile) if input_profile else None,
                "profile_saved": bool(deps.profile_saved) if deps else False,
                "targets_saved": bool(deps.targets_saved) if deps else False,
                "emails_saved": bool(deps.emails_saved) if deps else False,
                "pages_fetched": deps.pages_fetched if deps else 0,
                "searches_used": deps.searches_used if deps else 0,
                "iterations": iterations,
            }
        )
        print(
            f"Model: {os.environ.get('LLM_MODEL', 'gpt-5.6-luna')}",
            file=sys.stderr,
        )
        print(f"Audit log: {AUDIT_LOG_PATH}", file=sys.stderr)

    return output_text


def main() -> None:
    load_env()
    os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
    args = parse_args()
    profile_out = args.out if args.out.is_absolute() else HW2_ROOT / args.out
    input_profile = None
    if args.profile is not None:
        input_profile = args.profile if args.profile.is_absolute() else HW2_ROOT / args.profile
    if args.url is None and input_profile is None:
        sys.exit("Provide --url (profile a site) and/or --profile (find customer targets).")
    mode = infer_mode(args.query, args.url is not None, input_profile is not None)
    if mode == "targets" and input_profile is None:
        default_profile = HW2_ROOT / "assets" / "company_profile.json"
        if default_profile.is_file():
            input_profile = default_profile
    try:
        output = asyncio.run(
            run_agent(args.query, args.url, profile_out, input_profile, mode)
        )
    except ValidationError as exc:
        sys.exit(f"Profile validation failed: {exc}")
    print(output)


if __name__ == "__main__":
    main()
