# Credit card statement extraction

You are a bookkeeper for **Spoke & Wrench Bicycle Repair** (Jordan Lee). Extract **every posted charge** from the January credit card statement text below. Skip header fields (new balance, payment due, account number). Do **not** invent charges.

The issuer’s category column (e.g. “Grocery stores”, “Merchandise / electronics”) is **automated and often wrong** for how the shop should treat a charge. Use merchant name and common sense for a bike repair shop. Do **not** copy the issuer category into `expense_category`.

Jordan uses this card for **shop and household** purchases.

Return **only** valid JSON (no markdown fences) as:

```json
{ "transactions": [ { "...": "..." } ] }
```

Each element of `transactions` must have:

- `date` (string): charge date as `YYYY-MM-DD` (statement year is 2026 unless the PDF says otherwise)
- `merchant` (string): merchant name as shown on the statement
- `amount_usd` (number): charge amount as a **positive** number
- `classification` (string): `business` or `personal`
- `expense_category` (string or null): a **shop** expense label when `classification` is `business`; **must be `null`** when `classification` is `personal`. Prefer labels such as:
  - `cogs_parts` - bicycle parts / wholesale
  - `tools_equipment` - shop tools, stands, hardware used in the bay
  - `shipping` - courier / delivery
  - `office_supplies` - paper, printing, staples, and similar
  - `software_cloud` - hosting / cloud subscriptions used for the shop
  - `vehicle` - fuel or similar if it is a shop run
  - `marketing` - print/marketing for the business
  - `other` - business but none of the above
  Do **not** use issuer labels like “Groceries”.

Guidance (override only if the statement text clearly says otherwise):

- Groceries, streaming entertainment, and clearly household merchants → `personal`, `expense_category` null.
- Bike parts, shop tools, courier to the shop, hardware-store shop supplies, commercial printing for the shop, business cloud → `business`.
- If a sporting-goods or mixed merchant could be shop *or* personal and the statement does not say, classify your best judgment and still output one row.

`source_file` for this document is `{source_file}`.

## Statement filename

`{source_file}`

## Statement text

```
{statement_text}
```
