"""Stock research chatbot: GPT-5.6-luna via Portkey + tools (Yahoo Finance, web news).

get_reply(user_text, conversation_history) -> {"text": str, "tool_events": [...]}

Rules baked into the system prompt: never invent prices or metrics; every number
must come from a tool call, and the reply should say when the data was fetched.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
# override=True: the project .env is the source of truth, even if the shell
# already exports a (possibly stale) PORTKEY_API_KEY.
load_dotenv(HERE / ".env", override=True)

MODEL = os.environ.get("LLM_MODEL", "gpt-5.6-luna")
MAX_TOOL_ROUNDS = 6
HISTORY_TURNS = 12

SYSTEM_PROMPT = """You are a concise stock research assistant for a finance class.

Hard rules:
- NEVER invent or estimate prices, market caps, ratios, or any financial figure. Only report
  numbers returned by your tools, and mention the as-of timestamp the tool gave you.
- If a tool fails or returns nothing, say so plainly and do not fill the gap with guesses.
- When the user mentions a company, resolve it to a ticker (e.g. Apple -> AAPL) and call the tools.
- For news or recent events, use search_news and cite the source name and date for each item.
- Use Markdown: short paragraphs, small tables for numbers, bullet lists for news.
- This is research help, not personalized investment advice; keep disclaimers to one short line
  and only when the user asks whether to buy or sell.
"""


# ----------------------------------------------------------------------------
# Tools
# ----------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _clean(value: Any) -> Any:
    """Make yfinance values JSON-friendly."""
    try:
        if value is None:
            return None
        if isinstance(value, (int, str, bool)):
            return value
        f = float(value)
        return None if f != f else round(f, 4)  # drop NaN
    except (TypeError, ValueError):
        return str(value)


def get_stock_quote(ticker: str) -> dict[str, Any]:
    """Latest price and key metrics for one ticker from Yahoo Finance."""
    import yfinance as yf

    ticker = ticker.strip().upper()
    t = yf.Ticker(ticker)
    fast = getattr(t, "fast_info", None) or {}

    def fi(key: str) -> Any:
        try:
            return _clean(fast[key])
        except Exception:
            return None

    quote: dict[str, Any] = {
        "ticker": ticker,
        "as_of": _now_iso(),
        "price": fi("last_price") or fi("lastPrice"),
        "previous_close": fi("previous_close") or fi("previousClose"),
        "currency": fi("currency"),
        "market_cap": fi("market_cap") or fi("marketCap"),
        "day_high": fi("day_high") or fi("dayHigh"),
        "day_low": fi("day_low") or fi("dayLow"),
        "fifty_two_week_high": fi("year_high") or fi("yearHigh"),
        "fifty_two_week_low": fi("year_low") or fi("yearLow"),
    }

    # Slower but richer fields; tolerate failure.
    try:
        info = t.info or {}
    except Exception:
        info = {}
    for out_key, in_key in [
        ("name", "shortName"),
        ("sector", "sector"),
        ("industry", "industry"),
        ("trailing_pe", "trailingPE"),
        ("forward_pe", "forwardPE"),
        ("dividend_yield", "dividendYield"),
        ("beta", "beta"),
        ("eps_trailing", "trailingEps"),
        ("revenue_ttm", "totalRevenue"),
        ("profit_margin", "profitMargins"),
    ]:
        if info.get(in_key) is not None:
            quote[out_key] = _clean(info[in_key])

    if quote["price"] is None:
        # Fall back to most recent close from history.
        hist = t.history(period="5d")
        if not hist.empty:
            quote["price"] = _clean(hist["Close"].iloc[-1])
            quote["price_note"] = f"last close {hist.index[-1].date()}"
        else:
            return {"error": f"No Yahoo Finance data found for '{ticker}'. Check the symbol."}

    if quote["price"] is not None and quote["previous_close"]:
        chg = quote["price"] - quote["previous_close"]
        quote["day_change"] = round(chg, 4)
        quote["day_change_pct"] = round(100 * chg / quote["previous_close"], 2)
    return quote


def get_price_history(ticker: str, period: str = "6mo") -> dict[str, Any]:
    """Summary of historical closes (start/end/high/low/% change) for a period."""
    import yfinance as yf

    ticker = ticker.strip().upper()
    allowed = {"5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "ytd", "max"}
    if period not in allowed:
        period = "6mo"
    hist = yf.Ticker(ticker).history(period=period)
    if hist.empty:
        return {"error": f"No price history for '{ticker}' over {period}."}
    closes = hist["Close"]
    first, last = float(closes.iloc[0]), float(closes.iloc[-1])
    return {
        "ticker": ticker,
        "period": period,
        "as_of": _now_iso(),
        "start_date": str(hist.index[0].date()),
        "end_date": str(hist.index[-1].date()),
        "start_close": round(first, 4),
        "end_close": round(last, 4),
        "pct_change": round(100 * (last - first) / first, 2) if first else None,
        "period_high": round(float(closes.max()), 4),
        "period_low": round(float(closes.min()), 4),
        "trading_days": int(len(closes)),
    }


def search_news(query: str, max_results: int = 5) -> dict[str, Any]:
    """Recent news headlines via DuckDuckGo news search (no API key needed)."""
    from ddgs import DDGS

    max_results = max(1, min(int(max_results), 10))
    try:
        raw = DDGS().news(query, max_results=max_results) or []
    except Exception as exc:  # network / rate limit
        return {"error": f"News search failed: {exc}"}
    items = [
        {
            "title": r.get("title"),
            "source": r.get("source"),
            "date": r.get("date"),
            "url": r.get("url"),
            "snippet": (r.get("body") or "")[:300],
        }
        for r in raw
    ]
    return {"query": query, "as_of": _now_iso(), "results": items}


TOOL_FUNCTIONS = {
    "get_stock_quote": get_stock_quote,
    "get_price_history": get_price_history,
    "search_news": search_news,
}

TOOL_LABELS = {
    "get_stock_quote": "Yahoo Finance quote",
    "get_price_history": "Yahoo Finance history",
    "search_news": "Web news search",
}

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_stock_quote",
            "description": "Get the latest price, day change, market cap, P/E, 52-week range and other key metrics for a stock ticker from Yahoo Finance.",
            "parameters": {
                "type": "object",
                "properties": {"ticker": {"type": "string", "description": "Ticker symbol, e.g. AAPL, MSFT, TSLA"}},
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_price_history",
            "description": "Summarize a stock's price performance over a period: start/end close, percent change, period high and low.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "period": {
                        "type": "string",
                        "enum": ["5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "ytd", "max"],
                        "description": "Lookback window. Default 6mo.",
                    },
                },
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_news",
            "description": "Search the web for recent news about a company, ticker, or market topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query, e.g. 'NVIDIA earnings'"},
                    "max_results": {"type": "integer", "minimum": 1, "maximum": 10},
                },
                "required": ["query"],
            },
        },
    },
]


# ----------------------------------------------------------------------------
# LLM loop
# ----------------------------------------------------------------------------

def _client():
    key = os.environ.get("PORTKEY_API_KEY")
    if not key:
        raise RuntimeError("PORTKEY_API_KEY is not set. Add it to labs/week2/.env (see .env.example).")
    from portkey_ai import Portkey

    return Portkey(api_key=key)


def _history_to_messages(history: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    msgs = []
    for m in (history or [])[-HISTORY_TURNS:]:
        role = m.get("role")
        content = m.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            msgs.append({"role": role, "content": content})
    return msgs


def _run_tool(name: str, raw_args: str) -> str:
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool '{name}'"})
    try:
        args = json.loads(raw_args or "{}")
    except json.JSONDecodeError:
        return json.dumps({"error": f"Bad tool arguments: {raw_args!r}"})
    try:
        return json.dumps(fn(**args), default=str)
    except Exception as exc:
        return json.dumps({"error": f"{name} failed: {exc}"})


def get_reply(user_text: str, conversation_history: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    client = _client()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT + f"\nCurrent time: {_now_iso()}."},
        *_history_to_messages(conversation_history),
        {"role": "user", "content": user_text},
    ]
    tool_events: list[dict[str, str]] = []

    for _ in range(MAX_TOOL_ROUNDS):
        resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS_SCHEMA,
            tool_choice="auto",
        )
        msg = resp.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None) or []

        if not tool_calls:
            return {"text": (msg.content or "").strip() or "(empty reply)", "tool_events": tool_events}

        # Echo the assistant's tool request back, then each tool result.
        messages.append(
            {
                "role": "assistant",
                "content": msg.content or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in tool_calls
                ],
            }
        )
        for tc in tool_calls:
            name = tc.function.name
            args = tc.function.arguments or "{}"
            print(f"  tool -> {name}({args})", flush=True)
            result = _run_tool(name, args)
            ok = '"error"' not in result[:20]
            try:
                arg_hint = json.loads(args)
                hint = arg_hint.get("ticker") or arg_hint.get("query") or ""
            except Exception:
                hint = ""
            label = TOOL_LABELS.get(name, name) + (f": {hint}" if hint else "")
            tool_events.append({"name": label, "status": "completed" if ok else "error"})
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    # Ran out of rounds: ask for a final answer with no more tools.
    resp = client.chat.completions.create(model=MODEL, messages=messages)
    return {"text": (resp.choices[0].message.content or "").strip(), "tool_events": tool_events}


if __name__ == "__main__":
    import sys

    q = " ".join(sys.argv[1:]) or "What is Apple trading at and any news today?"
    out = get_reply(q)
    print(out["text"])
    print("\ntools:", [t["name"] for t in out["tool_events"]])
