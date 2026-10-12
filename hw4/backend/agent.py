"""Campus Customs merch agent. main.py calls run_agent(message)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext, UsageLimits
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from audit import record_loop
from models import ChatReply, ProductCard, ShopperDeps
from tools import cards_for
from tools import get_product_description as fetch_description
from tools import get_product_price as fetch_price
from tools import get_product_stock as fetch_stock
from tools import search_for_agent as fetch_search

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PROMPT_PATH = HERE / "prompts" / "prompt.md"
PORTKEY_URL = "https://api.portkey.ai/v1"

load_dotenv(ROOT / ".env", override=True)

_agent: Agent[ShopperDeps, ChatReply] | None = None
_HISTORY_TURNS = 8
_HISTORY_CHARS = 320
_PRICE = re.compile(r"\$\d+(?:\.\d{2})?")
_EMAIL = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)


def model_name() -> str:
    return os.environ.get("LLM_MODEL", "gpt-5.6-luna")


def load_system_prompt() -> str:
    if not PROMPT_PATH.is_file():
        raise RuntimeError(f"Missing system prompt: {PROMPT_PATH}")
    text = PROMPT_PATH.read_text(encoding="utf-8").strip()
    if not text:
        raise RuntimeError(f"System prompt is empty: {PROMPT_PATH}")
    if "## Safety" not in text:
        raise RuntimeError(f"{PROMPT_PATH} has no Safety section. The agent will not start.")
    return text


def build_model() -> OpenAIChatModel:
    key = os.environ.get("PORTKEY_API_KEY")
    if not key:
        raise RuntimeError(
            "No Portkey key found. Set PORTKEY_API_KEY in hw4/.env (see .env.example)."
        )
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        base_url=os.environ.get("PORTKEY_BASE_URL", PORTKEY_URL),
        api_key=key,
        default_headers={"x-portkey-api-key": key},
    )
    return OpenAIChatModel(model_name(), provider=OpenAIProvider(openai_client=client))


def get_agent() -> Agent[ShopperDeps, ChatReply]:
    global _agent
    if _agent is not None:
        return _agent
    agent: Agent[ShopperDeps, ChatReply] = Agent(
        build_model(),
        output_type=ChatReply,
        instructions=load_system_prompt(),
        deps_type=ShopperDeps,
        name="campus_customs",
        retries=2,
    )

    @agent.instructions
    def shopper_and_page(ctx: RunContext[ShopperDeps]) -> str:
        shopper = ctx.deps
        if shopper.signed_in:
            who = (
                f"Signed-in shopper: {shopper.first_name or shopper.name}. "
                "Call shopper_context only if they ask for their email."
            )
        else:
            who = "Guest shopper. No name or email on this turn."
        if shopper.page_brief:
            page = shopper.page_brief
        elif shopper.page_path:
            page = f"Open page: {shopper.page_path}. Not a single product."
        else:
            page = "No product page is open."
        return f"{who} {page}"

    @agent.tool
    def shopper_context(ctx: RunContext[ShopperDeps]) -> str:
        """Return the shopper's name and email, and the product page they have open.

        viewing_product_id is empty when they are not on a product page.
        A guest has signed_in false and blank name and email.
        Use this id with the fact tools when they say this or it.
        """
        return ctx.deps.model_dump_json(exclude={"page_brief"})

    @agent.tool_plain
    def search_catalogue(
        query: str = "",
        garment_type: str = "",
        color: str = "",
        max_price: float | None = None,
        size: str = "",
    ) -> str:
        """Find which catalogue products match. Does not return description, price, or stock.

        query matches name, garment, description, colors, and tags.
        garment_type is a substring such as hoodie, crewneck, t-shirt, quarter-zip, or jacket.
        size is XS, S, M, L, XL, or XXL and keeps only rows with quantity above 0.
        garment_type for a type question is hoodie, crewneck, t-shirt, quarter-zip, or jacket.
        Every returned product_id is shown on the page as a card that opens that product.
        total_matches is the full count. For a description, price, or quantity, call the fact tool.
        """
        found = fetch_search(
            query=query,
            garment_type=garment_type,
            color=color,
            max_price=max_price,
            size=size,
        )
        return found.model_dump_json()

    @agent.tool_plain
    def get_product_description(product_id: str = "", query: str = "") -> str:
        """Read catalogue.description and colors for one product.

        Pass product_id when you have it, or query with the shopper's product name.
        description is the catalogue sentence. colors is the color list.
        If a requested color is not in colors, say it is not offered.
        If found is false, do not invent one.
        """
        return fetch_description(product_id=product_id, query=query).model_dump_json()

    @agent.tool_plain
    def get_product_price(product_id: str = "", query: str = "") -> str:
        """Read catalogue.price for one product.

        Quote price_text. Pass product_id when you have it, or query with the product name.
        If found is false, do not name a price.
        """
        return fetch_price(product_id=product_id, query=query).model_dump_json()

    @agent.tool_plain
    def get_product_stock(product_id: str = "", query: str = "", size: str = "") -> str:
        """Read inventory.quantity for every size of one product.

        size is optional: XS, S, M, L, XL, XXL, or a word such as large.
        Quantity 0 means that size is out of stock. Say so. Do not drop a zero.
        If found is false, do not guess a count.
        """
        return fetch_stock(product_id=product_id, query=query, size=size).model_dump_json()

    _agent = agent
    return agent


def plain_reply(text: str) -> str:
    """Drop markdown the model adds, so the shopper reads sentences."""
    cleaned = text.replace("**", "").replace("__", "")
    lines: list[str] = []
    for line in cleaned.splitlines():
        stripped = line.strip()
        if stripped.startswith(("- ", "* ")):
            stripped = stripped[2:].strip()
        lines.append(stripped)
    compact = "\n".join(lines)
    compact = re.sub(r"\n{3,}", "\n\n", compact)
    return compact.strip()


def clip_history_text(text: str) -> str:
    """Keep a prior turn short. The live question is never clipped."""
    cleaned = plain_reply(text)
    if len(cleaned) <= _HISTORY_CHARS:
        return cleaned
    return cleaned[: _HISTORY_CHARS - 1].rstrip() + "…"


def history_chars(turns: list[dict[str, str]] | None, clipped: bool) -> int:
    """Characters of prior turns that would be sent to the model."""
    if not turns:
        return 0
    chosen = turns[-_HISTORY_TURNS:] if clipped else turns[-12:]
    total = 0
    for turn in chosen:
        text = str(turn.get("content", "")).strip()
        if not text:
            continue
        total += len(clip_history_text(text) if clipped else text)
    return total


def _history(turns: list[dict[str, str]] | None) -> list[ModelRequest | ModelResponse] | None:
    if not turns:
        return None
    history: list[ModelRequest | ModelResponse] = []
    for turn in turns[-_HISTORY_TURNS:]:
        text = clip_history_text(str(turn.get("content", "")))
        if not text:
            continue
        if turn.get("role") == "assistant":
            history.append(ModelResponse(parts=[TextPart(content=text)]))
        else:
            history.append(ModelRequest(parts=[UserPromptPart(content=text)]))
    return history or None


def open_product_brief(product_id: str) -> tuple[str, str]:
    """Catalogue facts for the page the shopper has open. Returns brief text and price_text."""
    description = fetch_description(product_id=product_id)
    price = fetch_price(product_id=product_id)
    stock = fetch_stock(product_id=product_id)
    if not description.found or not price.found:
        return "", ""
    colors = ", ".join(description.colors) if description.colors else "none on file"
    sizes = ", ".join(f"{item.size} {item.quantity}" for item in stock.sizes)
    brief = (
        f"Open product loaded from campus_customs.db this turn: {description.name} "
        f"(product_id {description.product_id}). "
        f"Price {price.price_text}. Colors: {colors}. "
        f"Inventory quantities: {sizes}. A quantity of 0 is out of stock. "
        f"Description: {description.description} "
        "This, it, and the one I'm looking at mean this product. "
        "Answer from these fields. Do not call a tool for this same product. "
        "Call a tool for a different item or for a type of item."
    )
    return brief, price.price_text


def _price_key(raw: str) -> str:
    number = raw.removeprefix("$")
    if "." not in number:
        number = f"{number}.00"
    return f"${number}"


def _prices_in(node: object) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        price_text = node.get("price_text")
        if isinstance(price_text, str) and price_text.startswith("$"):
            found.add(_price_key(price_text))
        price = node.get("price")
        if isinstance(price, (int, float)):
            found.add(f"${float(price):.2f}")
        for child in node.values():
            found.update(_prices_in(child))
    elif isinstance(node, list):
        for child in node:
            found.update(_prices_in(child))
    return found


def align_prices(reply: str, user_message: str, allowed: set[str]) -> str:
    """Replace a dollar amount the tools and the open product did not return."""
    if not allowed:
        return reply
    mentioned = {_price_key(item) for item in _PRICE.findall(user_message)}

    def fix(match: re.Match[str]) -> str:
        key = _price_key(match.group(0))
        if key in allowed or key in mentioned:
            return match.group(0)
        if len(allowed) == 1:
            return next(iter(allowed))
        return "the catalogue price"

    return _PRICE.sub(fix, reply)


def guard_reply(reply: str, shopper: ShopperDeps, user_message: str, allowed_prices: set[str]) -> str:
    cleaned = plain_reply(reply)
    lowered = cleaned.lower()
    if "pbkdf2" in lowered or "password_hash" in lowered or "password hash" in lowered:
        return "I can help with Campus Customs merchandise. I can't share account secrets."
    own_email = shopper.email.lower()
    for address in _EMAIL.findall(cleaned):
        if address.lower() != own_email:
            cleaned = cleaned.replace(address, "that email")
    return align_prices(cleaned, user_message, allowed_prices)


def _ids_in(node: object) -> list[str]:
    found: list[str] = []

    def add(value: object) -> None:
        if isinstance(value, str) and value and value not in found:
            found.append(value)

    def walk(current: object) -> None:
        if isinstance(current, dict):
            product_id = current.get("product_id")
            if isinstance(product_id, str) and current.get("found") is not False:
                add(product_id)
            for child in current.values():
                walk(child)
        elif isinstance(current, list):
            for child in current:
                walk(child)

    walk(node)
    return found


def _payload(part: ToolReturnPart) -> object | None:
    content: object = part.content
    if isinstance(content, str):
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return None
    return content


def _search_ids(messages: list[object]) -> list[str]:
    """Product ids from the latest search that actually returned rows."""
    batches: list[list[str]] = []
    for message in messages:
        for part in getattr(message, "parts", ()):
            if not isinstance(part, ToolReturnPart) or part.tool_name != "search_catalogue":
                continue
            payload = _payload(part)
            if payload is not None:
                batches.append(_ids_in(payload))
    for ids in reversed(batches):
        if ids:
            return ids
    return []


def _ids_from_tools(messages: list[object]) -> list[str]:
    found: list[str] = []
    for message in messages:
        for part in getattr(message, "parts", ()):
            if not isinstance(part, ToolReturnPart):
                continue
            payload = _payload(part)
            if payload is None:
                continue
            for product_id in _ids_in(payload):
                if product_id not in found:
                    found.append(product_id)
    return found


def run_agent(
    message: str,
    history: list[dict[str, str]] | None = None,
    shopper: ShopperDeps | None = None,
) -> tuple[str, list[ProductCard]]:
    """Answer one shop question. Product cards are catalogue rows, not model inventions."""
    deps = shopper or ShopperDeps()
    page_price = ""
    if deps.viewing_product_id:
        brief, page_price = open_product_brief(deps.viewing_product_id)
        deps = deps.model_copy(update={"page_brief": brief, "viewing_product_name": deps.viewing_product_name})
    print(
        f"model={model_name()} via Portkey shopper_signed_in={deps.signed_in} "
        f"product={deps.viewing_product_id or '-'} "
        f"history_chars={history_chars(history, clipped=True)}",
        flush=True,
    )
    try:
        result = get_agent().run_sync(
            message,
            message_history=_history(history),
            deps=deps,
            usage_limits=UsageLimits(request_limit=8, tool_calls_limit=6),
        )
    except UsageLimitExceeded as exc:
        print(f"agent stopped: usage limit: {exc}", flush=True)
        record_loop([], "usage_limit")
        return "I could not finish that question. Please try again.", []
    except Exception as exc:
        print(f"agent failed: {type(exc).__name__}: {exc}", flush=True)
        record_loop([], "error")
        return "I could not finish that question. Please try again.", []

    finish = ""
    for prior in reversed(result.all_messages()):
        reason = getattr(prior, "finish_reason", None)
        if reason:
            finish = str(reason).rsplit(".", 1)[-1]
            if finish != "tool_calls":
                break
    record_loop(result.all_messages(), finish or "stop")

    called = [
        part.tool_name
        for message in result.all_messages()
        for part in getattr(message, "parts", ())
        if type(part).__name__ == "ToolCallPart"
    ]
    print(f"tools={called}", flush=True)
    output = result.output
    reply = output.reply.strip() if isinstance(output, ChatReply) else str(output).strip()
    if not reply:
        reply = "I could not find a clear answer in the Campus Customs catalogue."
    question = message
    messages = result.all_messages()
    allowed = {_price_key(page_price)} if page_price else set()
    saw_search = False
    for prior in messages:
        for part in getattr(prior, "parts", ()):
            if not isinstance(part, ToolReturnPart):
                continue
            if part.tool_name == "search_catalogue":
                saw_search = True
            payload = _payload(part)
            if payload is not None:
                allowed.update(_prices_in(payload))
    reply = guard_reply(reply, deps, question, set() if saw_search else allowed)
    search_ids = _search_ids(messages)
    if search_ids:
        chosen = search_ids
    else:
        tool_ids = _ids_from_tools(messages)
        listed = output.product_ids if isinstance(output, ChatReply) else []
        chosen = [product_id for product_id in listed if product_id in tool_ids]
        if not chosen:
            chosen = tool_ids[:4]
    if not chosen and deps.viewing_product_id and not saw_search:
        chosen = [deps.viewing_product_id]
    return reply, cards_for(chosen)
