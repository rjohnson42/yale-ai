# Bank statement extraction

You are a bookkeeper for **Spoke & Wrench Bicycle Repair** (Jordan Lee, sole prop). Extract **every posted transaction line** from the January bank statement text below. Do **not** turn header totals (beginning balance, total deposits, total withdrawals, ending balance) into rows. Do **not** invent lines.

Return **only** valid JSON (no markdown fences, no commentary) as one object:

```json
{ "transactions": [ { "...": "..." } ] }
```

Each element of `transactions` must have:

- `date` (string): posting date as `YYYY-MM-DD` (statement year is 2026 unless the PDF says otherwise)
- `description` (string): the statement description text as shown (you may normalize whitespace)
- `amount_usd` (number): the dollar amount as a **positive** number (never negative)
- `classification` (string): `business` or `personal`
- `direction` (string): `credit` (money in / deposit) or `debit` (money out / withdrawal / payment / fee)
- `accounting_label` (string): one of:
  - `revenue` - customer / shop sales deposits (Square, ACH from customers, cash & card walk-ins)
  - `expense` - operating costs paid from the account (rent, utilities, internet, parts, insurance, bank fees, vendor portal charges)
  - `owner_draw` - owner personal withdrawals, including ATM cash marked personal and transfers described as owner draws
  - `transfer` - account transfers that are **not** owner draws
  - `other` - only if none of the above fit
- `expense_type` (string or null): set **only** when `accounting_label` is `expense`. Use a short subcategory such as:
  - `rent`
  - `utilities`
  - `internet`
  - `cogs_parts`
  - `tools_equipment`
  - `insurance`
  - `bank_fees`
  - `other`
  For revenue, owner draws, and transfers, set `expense_type` to `null`.

Classification rules from the statement notes:

- Square POS deposits are **business revenue**.
- Transfers and ATM withdrawals marked **personal** / **owner draw** are `personal` and `owner_draw`.
- Rent, electric, internet, wholesale parts, liability insurance, vendor charges, and monthly service fees are **business** expenses unless the line itself says personal.

`source_file` for this document is `{source_file}`. You may include it on each row but it is optional.

## Statement filename

`{source_file}`

## Statement text

```
{statement_text}
```
