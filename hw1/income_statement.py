#!/usr/bin/env python3
"""Build the January 2026 income statement from extracts + reconciliation log."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HW1_ROOT = Path(__file__).resolve().parent
PERIOD = "2026-01"
LOG_NAME = "reconciliation_log.json"
BANK_NAME = "bank_transactions.json"
CARD_NAME = "credit_card_transactions.json"
RECEIPTS_NAME = "receipts.json"


def money(value: float) -> float:
    return round(float(value), 2)


def ascii_dash(value) -> str:
    return str(value).replace("\u2014", "-").replace("\u2013", "-")


def almost_equal(a: float, b: float) -> bool:
    return abs(float(a) - float(b)) < 0.005


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Roll reconciled amounts into income_statement_jan2026.json"
    )
    parser.add_argument("--json-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    return parser.parse_args()


def load_json(path: Path):
    if not path.is_file():
        sys.exit(f"Missing {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def is_yes(row: dict) -> bool:
    return str(row.get("included_in_income_statement", "")).strip().lower() == "yes"


def source_kind(name: str) -> str:
    lowered = str(name).lower()
    if "bank" in lowered:
        return "bank"
    if "credit_card" in lowered or lowered.startswith("card"):
        return "card"
    if "receipt" in lowered or lowered.endswith(".pdf"):
        return "receipt"
    if lowered.endswith(".txt") or "email" in lowered:
        return "email"
    return "other"


def bank_credits(bank_rows: list[dict]) -> list[dict]:
    return [
        row
        for row in bank_rows
        if row.get("direction") == "credit"
        and row.get("accounting_label") == "revenue"
    ]


def log_row_is_revenue(row: dict, bank_rows: list[dict]) -> bool:
    credits = bank_credits(bank_rows)
    for source, amount in (row.get("amounts_seen") or {}).items():
        if source_kind(source) != "bank":
            continue
        for credit in credits:
            if almost_equal(credit["amount_usd"], amount):
                return True
    return False


def log_covers_bank_line(log_rows: list[dict], bank_row: dict) -> bool:
    amount = bank_row["amount_usd"]
    for row in log_rows:
        for source, seen in (row.get("amounts_seen") or {}).items():
            if source_kind(source) == "bank" and almost_equal(seen, amount):
                return True
    return False


def log_covers_card_line(log_rows: list[dict], card_row: dict) -> bool:
    amount = card_row["amount_usd"]
    for row in log_rows:
        for source, seen in (row.get("amounts_seen") or {}).items():
            if source_kind(source) == "card" and almost_equal(seen, amount):
                return True
    return False


def category_for_log_expense(
    row: dict,
    bank_rows: list[dict],
    card_rows: list[dict],
    receipt_rows: list[dict],
) -> str:
    used = float(row.get("amount_used_in_income_statment") or 0)
    for source, seen in (row.get("amounts_seen") or {}).items():
        kind = source_kind(source)
        if kind == "card":
            for card in card_rows:
                if almost_equal(card["amount_usd"], seen) or almost_equal(
                    card["amount_usd"], used
                ):
                    cat = card.get("expense_category")
                    if cat:
                        return cat
        if kind == "receipt":
            for rec in receipt_rows:
                if almost_equal(rec.get("amount_usd"), seen) or almost_equal(
                    rec.get("amount_usd"), used
                ):
                    cat = rec.get("category")
                    if cat and cat != "personal":
                        return cat
        if kind == "bank":
            for bank in bank_rows:
                if bank.get("direction") != "debit":
                    continue
                if almost_equal(bank["amount_usd"], seen) or almost_equal(
                    bank["amount_usd"], used
                ):
                    return bank.get("expense_type") or "other"
    return "other"


def label_for_log_expense(row: dict, bank_rows: list[dict], card_rows: list[dict]) -> str:
    used = float(row.get("amount_used_in_income_statment") or 0)
    for source, seen in (row.get("amounts_seen") or {}).items():
        if source_kind(source) == "card":
            for card in card_rows:
                if almost_equal(card["amount_usd"], seen) or almost_equal(
                    card["amount_usd"], used
                ):
                    return str(card.get("merchant") or row["id"])
        if source_kind(source) == "bank":
            for bank in bank_rows:
                if bank.get("direction") != "debit":
                    continue
                if almost_equal(bank["amount_usd"], seen) or almost_equal(
                    bank["amount_usd"], used
                ):
                    return str(bank.get("description") or row["id"])
    return str(row.get("id"))


def unique_sources(values) -> list[str]:
    seen = []
    for item in values:
        name = str(item)
        if name not in seen:
            seen.append(name)
    return seen


def main() -> None:
    args = parse_args()
    log_rows = load_json(args.json_dir / LOG_NAME)
    if not isinstance(log_rows, list):
        sys.exit(f"{LOG_NAME} must be a JSON array")

    bank_path = args.json_dir / BANK_NAME
    card_path = args.json_dir / CARD_NAME
    receipts_path = args.json_dir / RECEIPTS_NAME
    bank_rows = load_json(bank_path) if bank_path.is_file() else []
    card_rows = load_json(card_path) if card_path.is_file() else []
    receipt_rows = load_json(receipts_path) if receipts_path.is_file() else []

    revenue_usd = 0.0
    expense_lines = []

    for row in log_rows:
        if not is_yes(row):
            continue
        amount = money(row.get("amount_used_in_income_statment") or 0)
        sources = unique_sources(row.get("sources") or [])
        if log_row_is_revenue(row, bank_rows):
            revenue_usd += amount
        else:
            expense_lines.append(
                {
                    "label": ascii_dash(label_for_log_expense(row, bank_rows, card_rows)),
                    "amount_usd": amount,
                    "category": category_for_log_expense(
                        row, bank_rows, card_rows, receipt_rows
                    ),
                    "sources": sources,
                }
            )

    for bank in bank_rows:
        if log_covers_bank_line(log_rows, bank):
            continue
        if bank.get("classification") == "personal":
            continue
        if bank.get("accounting_label") in ("owner_draw", "transfer"):
            continue
        amount = money(bank["amount_usd"])
        sources = [BANK_NAME]
        if bank.get("direction") == "credit" and bank.get("accounting_label") == "revenue":
            revenue_usd += amount
        elif bank.get("direction") == "debit" and bank.get("accounting_label") == "expense":
            expense_lines.append(
                {
                    "label": ascii_dash(bank.get("description") or "bank expense"),
                    "amount_usd": amount,
                    "category": bank.get("expense_type") or "other",
                    "sources": sources,
                }
            )

    for card in card_rows:
        if log_covers_card_line(log_rows, card):
            continue
        if card.get("classification") != "business":
            continue
        expense_lines.append(
            {
                "label": ascii_dash(card.get("merchant") or "card charge"),
                "amount_usd": money(card["amount_usd"]),
                "category": card.get("expense_category") or "other",
                "sources": [CARD_NAME],
            }
        )

    revenue_usd = money(revenue_usd)
    total_expenses_usd = money(sum(line["amount_usd"] for line in expense_lines))
    net_income_usd = money(revenue_usd - total_expenses_usd)

    statement = {
        "period": PERIOD,
        "revenue_usd": revenue_usd,
        "expense_lines": expense_lines,
        "total_expenses_usd": total_expenses_usd,
        "net_income_usd": net_income_usd,
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / "income_statement_jan2026.json"
    out_path.write_text(json.dumps(statement, indent=2) + "\n", encoding="utf-8")
    print(out_path)


if __name__ == "__main__":
    main()
