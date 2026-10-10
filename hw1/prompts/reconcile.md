# Reconciliation log

You are the bookkeeper for **Spoke & Wrench Bicycle Repair** closing **January 2026**. You are given (1) extracted JSON from receipts, the bank statement, and the credit card statement, and (2) full text of source PDFs and emails.

Produce **one JSON object** only:

```json
{ "items": [ { "...": "..." } ] }
```

Each element of `items` is **one reconciled amount** - not a dump of every bank line. Include a row when **any** of these is true:

- The same purchase or payment appears in **more than one** document (receipt + card, card + bank, quote + email, etc.).
- Amounts **disagree** across documents (partial receipt vs full card charge, quote vs approval email).
- A deposit or charge is **mixed** business/personal or needs a memo to split.
- An amount looks like January P&L but **must be excluded** (future work, unpaid IOU, owner draw, household spend, CAM not yet invoiced).
- A judgment call is required (REI, Home Depot, headphones, eBay stand, etc.).

Do **not** create a row for a clean, single-source January operating item that has no conflict (plain rent, electric, uncontroversial Square deposits with no memo, etc.). Those will flow to the income statement later from the bank extract.

## Row schema (every key required)

- `id` (string): short slug, e.g. `park_tool_card_vs_receipt`
- `sources` (array of strings): document **filenames** used (PDF/email names and/or `receipts.json` / `bank_transactions.json` / `credit_card_transactions.json`)
- `amounts_seen` (object): map **filename → number** for the dollar amount seen in that source. If a file mentions two different amounts, pick the amount that source contributes to this row (or use a filename plus a distinguishing suffix only if you must; prefer the real filename).
- `included_in_income_statement` (string): exactly `yes` or `no` - whether this row’s booked amount counts toward **January 2026** revenue or expenses
- `amount_used_in_income_statment` (number): dollars to book after reconciliation; use `0` if excluded. If a mixed deposit is partly revenue, book **only the business portion** here (not the full deposit).
- `resolution` (string): plain English: how you matched documents and chose the final amount

Spelling of `amount_used_in_income_statment` is intentional (no “e” in “statment”). Keep that key exactly.

## Accounting rules

- Cash / actually posted January activity for the shop belongs on the P&L. Owner draws and household charges do not.
- If a receipt and a card charge are the **same** purchase, book **once**.
- If a receipt is a **partial** ticket and the card (or bank) shows the full shop purchase, explain the split; book the **business amount that actually posted in January**, without double-counting.
- Separate invoices to the same vendor (e.g. two New Haven Bike Parts orders) stay **two** expenses if the notes say they are separate.
- Quotes, POs, and emails for **future** work are not January revenue even if a quote PDF is signed.
- IOUs not yet paid are not January cash revenue.
- CAM / extra rent **not yet invoiced** is not a January expense.
- Trust the owner voice memo when it contradicts issuer categories or a JSON `classification` field.

## Extracted JSON

### receipts.json

```
{receipts_json}
```

### bank_transactions.json

```
{bank_json}
```

### credit_card_transactions.json

```
{card_json}
```

## Source document text

{documents_text}
