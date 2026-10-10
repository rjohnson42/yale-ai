# Spoke & Wrench - Homework 1

January 2026 bookkeeping pipeline: extract receipts, bank lines, and card charges with an LLM, reconcile them, build an income statement, and render HTML.

## Layout

```
hw1/
  README.md
  AI_prompts.md
  requirements.txt
  .env.example
  read_receipts.py
  read_bank.py
  read_card.py
  reconcile.py
  income_statement.py
  report.py
  run_all.py
  prompts/
    receipts_extract.md
    bank_extract.md
    card_extract.md
    reconcile.md
  output/
    receipts.json
    bank_transactions.json
    credit_card_transactions.json
    reconciliation_log.json
    judgment_calls.json
    income_statement_jan2026.json
    income_statement.html
    pipeline.html
    hw1_spoke_and_wrench/   # source document pack
```

`judgment_calls.json` and `pipeline.html` are not produced by `run_all.py`. They are included as sample outputs (Problems 6 and 9).

## Install

From this `hw1/` folder:

```bash
python3 -m pip install -r requirements.txt
```

## Environment

Copy `.env.example` to `.env` in this folder. Do not commit `.env`.

```bash
cp .env.example .env
```

Set:

```
PORTKEY_API_KEY=your_key_here
LLM_MODEL=gpt-5.6-luna
```

Scripts load `.env` automatically. You can also export the same variables in the shell. Optional: `OPENAI_API_KEY` if you are not using Portkey.

Never put a real API key in README, prompts, or sample JSON.

## Run everything

```bash
python3 run_all.py --docs-dir output/hw1_spoke_and_wrench --json-dir output --out-dir output
```

This runs Problems 2-5, 7, and 8 in order (LLM extraction, reconcile, income statement, HTML report). It does not overwrite `judgment_calls.json` or `pipeline.html`.

## Run each script

From `hw1/`:

```bash
python3 read_receipts.py --docs-dir output/hw1_spoke_and_wrench --out-dir output
python3 read_bank.py --docs-dir output/hw1_spoke_and_wrench --out-dir output
python3 read_card.py --docs-dir output/hw1_spoke_and_wrench --out-dir output
python3 reconcile.py --docs-dir output/hw1_spoke_and_wrench --json-dir output --output-dir output
python3 income_statement.py --json-dir output --out-dir output
python3 report.py --json-dir output --out output/income_statement.html
```

| Script | Reads | Writes |
| --- | --- | --- |
| `read_receipts.py` | receipt PDFs, `prompts/receipts_extract.md` | `output/receipts.json` |
| `read_bank.py` | `bank_statement_jan2026.pdf`, `prompts/bank_extract.md` | `output/bank_transactions.json` |
| `read_card.py` | `credit_card_jan2026.pdf`, `prompts/card_extract.md` | `output/credit_card_transactions.json` |
| `reconcile.py` | extracts + document pack + `prompts/reconcile.md` | `output/reconciliation_log.json` |
| `income_statement.py` | JSON extracts + reconciliation log | `output/income_statement_jan2026.json` |
| `report.py` | statement, log, judgment calls | `output/income_statement.html` |

Open `output/income_statement.html` and `output/pipeline.html` in a browser.

## Notes

- LLM steps need network access and a valid Portkey key.
- `output/hw1_spoke_and_wrench` is the messy source pack (PDFs and emails). Keep it next to the sample JSON if you re-run extraction.
