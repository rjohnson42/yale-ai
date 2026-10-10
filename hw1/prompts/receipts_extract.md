# Purchase receipt extraction

You are a bookkeeper for **Spoke & Wrench Bicycle Repair**, a small New Haven bike shop. Extract **one JSON object** from the purchase receipt text below. Do not invent line items that are not on this receipt. Ignore bank statements, leases, quotes, IOUs, and other non-receipt documents if they appear.

Return **only** valid JSON (no markdown fences, no commentary) with these keys:

- `vendor` (string): store or seller name
- `date` (string): transaction / order date as `YYYY-MM-DD`
- `description` (string): concise summary of what was purchased (item names, not payment method)
- `amount_usd` (number): **this receipt's** total in US dollars (not a related charge mentioned only as a note)
- `category` (string): one expense label, using:
  - `cogs_parts` - parts, tubes, tires, chains, and similar resale/repair inventory
  - `tools_equipment` - shop tools, stands, bins, brooms, and durable shop gear
  - `shipping` - courier / delivery fees
  - `supplies` - consumable shop/office supplies that are not parts
  - `personal` - clearly personal / non-shop purchases
  - `other` - only if none of the above fit
- `source_file` (string): `{source_file}`
- `fields_not_found` (array of strings): names of the fields above that are missing or cannot be determined from this receipt. Use `[]` if everything is present.

If a field cannot be determined, set it to `null` and list its name in `fields_not_found`. Do not put `source_file` in `fields_not_found`.

If the document mentions **another** order, backorder, or payment that is **not** on this receipt, do **not** include that other amount in `amount_usd`. Use only the total printed for **this** receipt.

## Receipt filename

`{source_file}`

## Receipt text

```
{receipt_text}
```
