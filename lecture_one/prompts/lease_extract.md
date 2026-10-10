# Commercial lease extraction

Extract **one JSON object** from the commercial lease (or lease memo / draft / amendment) text below. Use only facts stated in the document. If a field is missing, blank, TBD, or explicitly not stated, set it to `null`. Do not invent values.

Return **only** valid JSON (no markdown fences, no commentary) with these keys:

- `source_file` (string): `{source_file}`
- `landlord_name` (string or null)
- `tenant_name` (string or null)
- `address` (string or null): full street address of the premises
- `space_type` (string or null)
- `rentable_sqft` (number or null): rentable square footage as a number, no commas or units
- `annual_base_rent` (number or null): annual base rent in USD as a number
- `rent_per_sqft` (number or null): rent per square foot as a number
- `lease_structure` (string or null): e.g. Triple Net (NNN), Modified Gross, Gross
- `commencement_date` (string or null): as written in the document
- `expiration_date` (string or null): as written in the document
- `security_deposit` (number or null): USD as a number
- `permitted_use` (string or null): the permitted use / business description

## Lease filename

`{source_file}`

## Lease text

```
{lease_text}
```
