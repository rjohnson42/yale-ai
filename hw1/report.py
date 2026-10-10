#!/usr/bin/env python3
"""Build a one-page HTML income-statement summary from output JSON files."""

from __future__ import annotations

import argparse
import calendar
import html
import json
import sys
from pathlib import Path

LOG_NAME = "reconciliation_log.json"
STATEMENT_NAME = "income_statement_jan2026.json"
JUDGMENT_NAME = "judgment_calls.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render income_statement.html from JSON")
    parser.add_argument("--json-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser.parse_args()


def load_json(path: Path):
    if not path.is_file():
        sys.exit(f"Missing {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def usd(value) -> str:
    return f"${float(value):,.2f}"


def esc(value) -> str:
    text = str(value).replace("\u2014", "-").replace("\u2013", "-")
    return html.escape(text, quote=True)


def period_label(period: str) -> str:
    year_s, month_s = str(period).split("-")
    return f"{calendar.month_name[int(month_s)]} {year_s}"


def is_excluded(row: dict) -> bool:
    return str(row.get("included_in_income_statement", "")).strip().lower() == "no"


def excluded_bucket(row: dict) -> str:
    blob = " ".join(
        [
            str(row.get("id") or ""),
            str(row.get("resolution") or ""),
            " ".join(str(s) for s in (row.get("sources") or [])),
        ]
    ).lower()
    personal_markers = (
        "personal",
        "owner draw",
        "owner_draw",
        "household",
        "grocery",
        "commute",
    )
    if any(marker in blob for marker in personal_markers):
        return "personal"
    return "business"


def seen_amount(row: dict) -> float:
    used = row.get("amount_used_in_income_statment")
    if used not in (None, 0, 0.0):
        return float(used)
    amounts = row.get("amounts_seen") or {}
    if not amounts:
        return 0.0
    return max(float(v) for v in amounts.values())


def evidence_items(raw) -> list[str]:
    if isinstance(raw, str):
        return [line.lstrip("- ").strip() for line in raw.splitlines() if line.strip()]
    items = []
    for item in raw or []:
        items.append(str(item).lstrip("- ").strip())
    return items


def render_expense_rows(lines: list[dict]) -> str:
    chunks = []
    for line in lines:
        chunks.append(
            "<tr>"
            f"<td>{esc(line.get('label') or '')}</td>"
            f"<td>{esc(line.get('category') or '')}</td>"
            f"<td class='num'>{esc(usd(line.get('amount_usd') or 0))}</td>"
            f"<td class='muted'>{esc(', '.join(line.get('sources') or []))}</td>"
            "</tr>"
        )
    return "\n".join(chunks)


def render_excluded_rows(rows: list[dict]) -> str:
    if not rows:
        return "<tr><td colspan='4' class='muted'>None</td></tr>"
    chunks = []
    for row in rows:
        chunks.append(
            "<tr>"
            f"<td>{esc(row.get('id') or '')}</td>"
            f"<td class='num'>{esc(usd(seen_amount(row)))}</td>"
            f"<td>{esc(', '.join(row.get('sources') or []))}</td>"
            f"<td>{esc(row.get('resolution') or '')}</td>"
            "</tr>"
        )
    return "\n".join(chunks)


def render_judgments(calls: list[dict], log_by_id: dict) -> str:
    cards = []
    for call in calls:
        tid = call.get("transaction_id")
        log_row = log_by_id.get(tid) or {}
        confidence = str(call.get("confidence") or "").lower()
        evidence = evidence_items(call.get("evidence_for"))
        evidence_html = "".join(f"<li>{esc(item)}</li>" for item in evidence)
        resolution = log_row.get("resolution") or ""
        cards.append(
            "<article class='call'>"
            f"<div class='call-top'><h3>{esc(tid)}</h3>"
            f"<span class='badge {esc(confidence)}'>{esc(confidence)}</span></div>"
            "<dl>"
            "<dt>Included</dt>"
            f"<dd>{esc(call.get('included_in_income_statement'))}</dd>"
            "<dt>Amount booked</dt>"
            f"<dd>{esc(usd(call.get('amount_used_in_income_statment') or 0))}</dd>"
            "</dl>"
            f"<p class='resolution'>{esc(resolution)}</p>"
            "<p class='label'>Evidence</p>"
            f"<ul>{evidence_html}</ul>"
            "</article>"
        )
    return "\n".join(cards)


def main() -> None:
    args = parse_args()
    json_dir = args.json_dir
    statement = load_json(json_dir / STATEMENT_NAME)
    log_rows = load_json(json_dir / LOG_NAME)
    judgments = load_json(json_dir / JUDGMENT_NAME)

    log_by_id = {row.get("id"): row for row in log_rows if isinstance(row, dict)}
    excluded = [row for row in log_rows if is_excluded(row)]
    personal = [row for row in excluded if excluded_bucket(row) == "personal"]
    business = [row for row in excluded if excluded_bucket(row) == "business"]

    title = period_label(statement.get("period") or "2026-01")
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Spoke &amp; Wrench - {esc(title)} Income Statement</title>
  <style>
    :root {{
      --yale-blue: #00356B;
      --yale-med: #286DC0;
      --yale-light: #5F92C3;
      --ink: #1B2430;
      --muted: #5B6770;
      --paper: #EEF2F6;
      --card: #FFFFFF;
      --line: #D7DEE7;
      --low: #8F2D2D;
      --medium: #8A5A00;
      --high: #0F5C38;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Mulish", "Helvetica Neue", Helvetica, Arial, sans-serif;
      color: var(--ink);
      background: var(--paper);
    }}
    header {{
      background: var(--yale-blue);
      color: #fff;
      padding: 28px 8vw 24px;
    }}
    header p {{
      margin: 0 0 6px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      font-size: 12px;
      color: var(--yale-light);
    }}
    h1, h2, h3 {{ margin: 0; }}
    h1 {{ font-size: 32px; font-weight: 700; }}
    main {{
      padding: 28px 8vw 48px;
      max-width: 1200px;
      margin: 0 auto;
    }}
    .kpis {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 16px;
      margin: -36px 0 28px;
    }}
    .kpi {{
      background: var(--card);
      border: 1px solid var(--line);
      border-top: 4px solid var(--yale-med);
      border-radius: 8px;
      padding: 16px 18px;
      box-shadow: 0 8px 20px rgba(0, 53, 107, 0.08);
    }}
    .kpi span {{ color: var(--muted); font-size: 13px; text-transform: uppercase; letter-spacing: 0.06em; }}
    .kpi strong {{ display: block; margin-top: 8px; font-size: 26px; color: var(--yale-blue); }}
    section {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 20px 22px 8px;
      margin-bottom: 22px;
    }}
    h2 {{
      color: var(--yale-blue);
      font-size: 20px;
      margin-bottom: 12px;
      padding-bottom: 8px;
      border-bottom: 2px solid var(--yale-light);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
      margin-bottom: 16px;
    }}
    th {{
      text-align: left;
      color: var(--yale-blue);
      font-size: 12px;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      border-bottom: 1px solid var(--line);
      padding: 8px 8px 8px 0;
    }}
    td {{
      padding: 8px 8px 8px 0;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
    }}
    .num {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
    .muted {{ color: var(--muted); font-size: 12px; }}
    .calls {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 16px;
      margin-bottom: 16px;
    }}
    .call {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      background: #f7fafc;
    }}
    .call-top {{ display: flex; justify-content: space-between; gap: 8px; align-items: start; }}
    .call h3 {{ font-size: 15px; color: var(--yale-blue); }}
    .badge {{
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      padding: 3px 8px;
      border-radius: 999px;
      color: #fff;
      background: var(--yale-med);
      white-space: nowrap;
    }}
    .badge.low {{ background: var(--low); }}
    .badge.medium {{ background: var(--medium); }}
    .badge.high {{ background: var(--high); }}
    dl {{ display: grid; grid-template-columns: auto 1fr; gap: 4px 12px; margin: 12px 0; }}
    dt {{ color: var(--muted); font-size: 12px; text-transform: uppercase; }}
    dd {{ margin: 0; font-weight: 600; }}
    .resolution {{ font-size: 13px; line-height: 1.45; }}
    .label {{ margin: 10px 0 4px; font-size: 12px; text-transform: uppercase; color: var(--muted); }}
    ul {{ margin: 0 0 8px; padding-left: 18px; font-size: 13px; }}
    @media (max-width: 900px) {{
      .kpis, .calls {{ grid-template-columns: 1fr; }}
      main, header {{ padding-left: 20px; padding-right: 20px; }}
    }}
  </style>
</head>
<body>
  <header>
    <p>Spoke &amp; Wrench Bicycle Repair</p>
    <h1>{esc(title)} Income Statement</h1>
  </header>
  <main>
    <div class="kpis">
      <div class="kpi"><span>Revenue</span><strong>{esc(usd(statement.get("revenue_usd") or 0))}</strong></div>
      <div class="kpi"><span>Total expenses</span><strong>{esc(usd(statement.get("total_expenses_usd") or 0))}</strong></div>
      <div class="kpi"><span>Net income</span><strong>{esc(usd(statement.get("net_income_usd") or 0))}</strong></div>
    </div>

    <section>
      <h2>January Income Statement</h2>
      <table>
        <thead>
          <tr><th>Expense</th><th>Category</th><th class="num">Amount</th><th>Sources</th></tr>
        </thead>
        <tbody>
          {render_expense_rows(statement.get("expense_lines") or [])}
          <tr>
            <td colspan="2"><strong>Total expenses</strong></td>
            <td class="num"><strong>{esc(usd(statement.get("total_expenses_usd") or 0))}</strong></td>
            <td></td>
          </tr>
          <tr>
            <td colspan="2"><strong>Net income</strong></td>
            <td class="num"><strong>{esc(usd(statement.get("net_income_usd") or 0))}</strong></td>
            <td></td>
          </tr>
        </tbody>
      </table>
    </section>

    <section>
      <h2>Excluded - personal</h2>
      <table>
        <thead>
          <tr><th>Item</th><th class="num">Amount seen</th><th>Sources</th><th>Why excluded</th></tr>
        </thead>
        <tbody>
          {render_excluded_rows(personal)}
        </tbody>
      </table>
    </section>
    <section>
      <h2>Excluded - business</h2>
      <table>
        <thead>
          <tr><th>Item</th><th class="num">Amount seen</th><th>Sources</th><th>Why excluded</th></tr>
        </thead>
        <tbody>
          {render_excluded_rows(business)}
        </tbody>
      </table>
    </section>

    <section>
      <h2>Judgment calls</h2>
      <div class="calls">
        {render_judgments(judgments, log_by_id)}
      </div>
    </section>
  </main>
</body>
</html>
"""
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(page, encoding="utf-8")
    print(args.out)


if __name__ == "__main__":
    main()
