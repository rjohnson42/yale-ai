"""Portfolio Chat: a PydanticAI financial analyst agent (gpt-5.6-luna via Portkey).

Tools: Yahoo Finance quotes / history, portfolio file + live valuation, web news.
Hard rule: never invent a number. Every figure comes from a tool call.

run_agent(user_text, portfolio_path, conversation_history=None)
    -> {"text": str, "tool_events": [{"name": str, "status": "completed"|"error"}, ...]}
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from dotenv import load_dotenv  # noqa: E402
from openai import AsyncOpenAI  # noqa: E402
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env", override=True)

MODEL_NAME = os.environ.get("LLM_MODEL", "gpt-5.6-luna")
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"
HISTORY_TURNS = 12

INSTRUCTIONS = """You are Portfolio Chat, a concise financial analyst assistant for a finance class.

Hard rules:
- NEVER invent or estimate prices, market caps, ratios, or any figure. Report only numbers
  returned by your tools, and include the as-of timestamp the tool gave you.
- If a tool fails or returns nothing, say so plainly; do not fill the gap with a guess.
- Questions about "my portfolio", "my holdings", "my exposure", etc. refer to the user's
  portfolio file: call get_portfolio or value_portfolio first.
- Resolve company names to tickers (Apple -> AAPL) and call tools; do not ask the user for the ticker
  if it is obvious.
- For news, use search_news and cite source and date for each item.
- Format with Markdown: short paragraphs, small tables for numbers, bullets for news.
- This is research help, not personalized investment advice. Add one short disclaimer line only when
  the user asks whether to buy, sell, or rebalance.
"""


# ----------------------------------------------------------------------------
# Deps + model
# ----------------------------------------------------------------------------

@dataclass
class Deps:
    portfolio_path: Path


def _build_model() -> OpenAIChatModel:
    key = os.environ.get("PORTKEY_API_KEY")
    if not key:
        raise RuntimeError("PORTKEY_API_KEY is not set. Add it to labs/week2/agent/.env (see .env.example).")
    client = AsyncOpenAI(
        base_url=PORTKEY_BASE_URL,
        api_key=key,
        default_headers={"x-portkey-api-key": key},
    )
    return OpenAIChatModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))


agent: Agent[Deps, str] = Agent(
    _build_model(),
    deps_type=Deps,
    instructions=INSTRUCTIONS,
    retries=2,
)


@agent.instructions
def _current_time(_: RunContext[Deps]) -> str:
    return f"Current time: {_now_iso()}."


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _num(value: Any) -> float | None:
    try:
        if value is None:
            return None
        f = float(value)
        return None if f != f else round(f, 4)
    except (TypeError, ValueError):
        return None


def _quote(ticker: str) -> dict[str, Any]:
    import yfinance as yf

    ticker = ticker.strip().upper()
    t = yf.Ticker(ticker)
    fast = getattr(t, "fast_info", None) or {}

    def fi(*keys: str) -> float | None:
        for k in keys:
            try:
                v = _num(fast[k])
                if v is not None:
                    return v
            except Exception:
                continue
        return None

    q: dict[str, Any] = {
        "ticker": ticker,
        "as_of": _now_iso(),
        "price": fi("last_price", "lastPrice"),
        "previous_close": fi("previous_close", "previousClose"),
        "currency": fast.get("currency") if hasattr(fast, "get") else None,
        "market_cap": fi("market_cap", "marketCap"),
        "fifty_two_week_high": fi("year_high", "yearHigh"),
        "fifty_two_week_low": fi("year_low", "yearLow"),
    }
    if q["price"] is None:
        hist = t.history(period="5d")
        if hist.empty:
            return {"error": f"No Yahoo Finance data for '{ticker}'. Check the symbol."}
        q["price"] = _num(hist["Close"].iloc[-1])
        q["price_note"] = f"last close {hist.index[-1].date()}"
    if q["price"] is not None and q["previous_close"]:
        chg = q["price"] - q["previous_close"]
        q["day_change"] = round(chg, 4)
        q["day_change_pct"] = round(100 * chg / q["previous_close"], 2)
    return q


def _load_portfolio(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Portfolio file not found: {path}")
    return json.loads(path.read_text())


# ----------------------------------------------------------------------------
# Tools
# ----------------------------------------------------------------------------

@agent.tool_plain
def get_stock_quote(ticker: str) -> dict[str, Any]:
    """Latest price, day change, market cap and 52-week range for a ticker (Yahoo Finance)."""
    return _quote(ticker)


@agent.tool_plain
def get_stock_fundamentals(ticker: str) -> dict[str, Any]:
    """Valuation and profile metrics for a ticker: P/E, forward P/E, EPS, dividend yield, beta, margins, sector."""
    import yfinance as yf

    ticker = ticker.strip().upper()
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception as exc:
        return {"error": f"Fundamentals unavailable for {ticker}: {exc}"}
    fields = {
        "name": "shortName", "sector": "sector", "industry": "industry",
        "trailing_pe": "trailingPE", "forward_pe": "forwardPE", "eps_trailing": "trailingEps",
        "dividend_yield": "dividendYield", "beta": "beta", "revenue_ttm": "totalRevenue",
        "profit_margin": "profitMargins", "market_cap": "marketCap",
    }
    out = {"ticker": ticker, "as_of": _now_iso()}
    for k, src in fields.items():
        v = info.get(src)
        if v is not None:
            out[k] = v if isinstance(v, str) else _num(v)
    if len(out) == 2:
        return {"error": f"No fundamentals returned for {ticker}."}
    return out


@agent.tool_plain
def get_price_history(ticker: str, period: str = "6mo") -> dict[str, Any]:
    """Price performance over a period (5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, ytd, max): start/end close, % change, high, low."""
    import yfinance as yf

    ticker = ticker.strip().upper()
    if period not in {"5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "ytd", "max"}:
        period = "6mo"
    hist = yf.Ticker(ticker).history(period=period)
    if hist.empty:
        return {"error": f"No price history for '{ticker}' over {period}."}
    closes = hist["Close"]
    first, last = float(closes.iloc[0]), float(closes.iloc[-1])
    return {
        "ticker": ticker, "period": period, "as_of": _now_iso(),
        "start_date": str(hist.index[0].date()), "end_date": str(hist.index[-1].date()),
        "start_close": round(first, 4), "end_close": round(last, 4),
        "pct_change": round(100 * (last - first) / first, 2) if first else None,
        "period_high": round(float(closes.max()), 4), "period_low": round(float(closes.min()), 4),
        "trading_days": int(len(closes)),
    }


@agent.tool
def get_portfolio(ctx: RunContext[Deps]) -> dict[str, Any]:
    """The user's portfolio file as stored: holdings (ticker, shares), cash, currency, as-of date. No prices."""
    return _load_portfolio(ctx.deps.portfolio_path)


@agent.tool
def value_portfolio(ctx: RunContext[Deps]) -> dict[str, Any]:
    """Mark the user's portfolio to market with live Yahoo Finance prices: value per holding, weights, day P&L, total."""
    pf = _load_portfolio(ctx.deps.portfolio_path)
    cash = float(pf.get("cash", 0) or 0)
    rows, errors = [], []
    for h in pf.get("holdings", []):
        q = _quote(h["ticker"])
        if "error" in q:
            errors.append(q["error"])
            continue
        shares = float(h["shares"])
        value = shares * q["price"]
        day_pnl = shares * q["day_change"] if q.get("day_change") is not None else None
        rows.append({
            "ticker": q["ticker"], "shares": shares, "price": q["price"],
            "value": round(value, 2),
            "day_change_pct": q.get("day_change_pct"),
            "day_pnl": round(day_pnl, 2) if day_pnl is not None else None,
        })
    equity = sum(r["value"] for r in rows)
    total = equity + cash
    for r in rows:
        r["weight_pct"] = round(100 * r["value"] / total, 2) if total else None
    rows.sort(key=lambda r: r["value"], reverse=True)
    return {
        "as_of": _now_iso(), "portfolio_as_of": pf.get("as_of"), "currency": pf.get("currency", "USD"),
        "holdings": rows, "equity_value": round(equity, 2), "cash": round(cash, 2),
        "cash_weight_pct": round(100 * cash / total, 2) if total else None,
        "total_value": round(total, 2),
        "day_pnl_total": round(sum(r["day_pnl"] for r in rows if r["day_pnl"] is not None), 2),
        "errors": errors,
    }


@agent.tool_plain
def search_news(query: str, max_results: int = 5) -> dict[str, Any]:
    """Recent news headlines for a company, ticker or topic (DuckDuckGo news; returns title, source, date, url)."""
    from ddgs import DDGS

    max_results = max(1, min(int(max_results), 10))
    try:
        raw = DDGS().news(query, max_results=max_results) or []
    except Exception as exc:
        return {"error": f"News search failed: {exc}"}
    return {
        "query": query, "as_of": _now_iso(),
        "results": [
            {"title": r.get("title"), "source": r.get("source"), "date": r.get("date"),
             "url": r.get("url"), "snippet": (r.get("body") or "")[:300]}
            for r in raw
        ],
    }


# ----------------------------------------------------------------------------
# Entry point used by app.py
# ----------------------------------------------------------------------------

TOOL_LABELS = {
    "get_stock_quote": "Yahoo Finance quote",
    "get_stock_fundamentals": "Yahoo Finance fundamentals",
    "get_price_history": "Yahoo Finance history",
    "get_portfolio": "Portfolio file",
    "value_portfolio": "Portfolio valuation",
    "search_news": "Web news search",
}


def _history_to_messages(history: list[dict[str, Any]] | None) -> list[ModelMessage]:
    msgs: list[ModelMessage] = []
    for m in (history or [])[-HISTORY_TURNS:]:
        content = m.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        if m.get("role") == "user":
            msgs.append(ModelRequest(parts=[UserPromptPart(content=content)]))
        elif m.get("role") == "assistant":
            msgs.append(ModelResponse(parts=[TextPart(content=content)]))
    return msgs


def _tool_events(messages: list[ModelMessage]) -> list[dict[str, str]]:
    calls: dict[str, dict[str, str]] = {}
    for msg in messages:
        for part in msg.parts:
            if isinstance(part, ToolCallPart):
                args = part.args_as_dict() if part.args else {}
                hint = args.get("ticker") or args.get("query") or args.get("period") or ""
                label = TOOL_LABELS.get(part.tool_name, part.tool_name) + (f": {hint}" if hint else "")
                calls[part.tool_call_id] = {"name": label, "status": "completed"}
            elif isinstance(part, ToolReturnPart) and part.tool_call_id in calls:
                content = part.content
                if isinstance(content, dict) and "error" in content:
                    calls[part.tool_call_id]["status"] = "error"
    return list(calls.values())


def run_agent(
    user_text: str,
    portfolio_path: str | Path,
    conversation_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    deps = Deps(portfolio_path=Path(portfolio_path))
    result = agent.run_sync(
        user_text,
        deps=deps,
        message_history=_history_to_messages(conversation_history),
    )
    events = _tool_events(result.new_messages())
    for e in events:
        print(f"  tool -> {e['name']} [{e['status']}]", flush=True)
    return {"text": str(result.output).strip() or "(empty reply)", "tool_events": events}


if __name__ == "__main__":
    import sys

    q = " ".join(sys.argv[1:]) or "What is my portfolio worth right now and what is my biggest position?"
    out = run_agent(q, HERE / "portfolio.json")
    print(out["text"])
    print("\ntools:", [t["name"] for t in out["tool_events"]])
