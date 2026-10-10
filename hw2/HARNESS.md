# HARNESS.md

This file describes how we keep the homework 2 sales agent under control. The agent (`sales_agent.py`) can (A) profile a company website or (B) find a few customer targets and **draft** outreach emails. A reviewer can treat this page as the safety contract: what the agent is allowed to touch, when it must stop, and what it is forbidden to do.

Every run is recorded in `output/audit_log.json` (time, model turns, tool names, argument and result summaries, and why the run stopped). API keys stay in `hw2/.env` and are never written into prompts, HTML, or the audit log.

---

## Tools

The model cannot browse or write files except through these tools. There is **no** send-email, login, or payment tool.

### `fetch_page`

Opens one web page in a headless browser (Playwright) and reads visible text. Used to profile the seller’s site, or later to inspect a candidate customer’s homepage and contact pages.

- **Inputs:** a single `http`/`https` URL.
- **Outputs:** JSON with the final URL, page title, a truncated copy of the visible text (at most 8,000 characters), same-site links, and any public email addresses found on the page (`mailto:` links and text). Errors (timeouts, blocked hosts, off-site redirects) are returned as JSON instead of crashing the run.
- **Limits:** at most **6** pages when building a company profile; at most **12** pages when hunting targets. Each page load is capped at about **25 seconds**. Downloads, form fills, and logins are disabled.

### `save_company_profile`

Writes the structured company profile after a site crawl.

- **Inputs:** one profile object (name, products, ICP evidence, and the other fields defined in `prompts/sales_agent.md`).
- **Outputs:** `assets/company_profile.json` (or the `--out` path). Missing fields are listed rather than guessed. Can be called successfully only **once** per run.

### `read_company_profile`

Loads the seller profile so target-finding starts from facts we already collected (for this assignment, Sierra).

- **Inputs:** none from the model; the path comes from `--profile` (for example `assets/company_profile.json`).
- **Outputs:** the profile JSON (truncated if it is very large). The seller’s own website is added to a blocklist so we do not treat Sierra as a “customer of Sierra.”

### `web_search`

Asks OpenAI, through Portkey, to search the public web (Responses API web-search tool, low search-context size to limit cost). Used only in target-finding, not while building a site-only profile.

- **Inputs:** a short search query (capped at 400 characters).
- **Outputs:** the search write-up plus any company homepage hosts we add to a crawl **allowlist**. Social, news, and search-engine domains (LinkedIn, Wikipedia, Google, and similar) are not treated as company homepages.
- **Limits:** at most **3** searches per run; at most **10** hosts on the allowlist.

### `save_targets`

Writes the kept customer list.

- **Inputs:** seller name/URL plus an array of targets (company name, URL, public contact emails, mutual-fit reason, business context, source URLs).
- **Outputs:** `output/targets.json`. At most **5** targets in the file (we ask for **3**). One successful save per run.

### `save_emails`

Writes outreach **drafts**.

- **Inputs:** subject, body, company name, and `to_emails` for each target.
- **Outputs:** `output/emails.json`. The file is stamped `Drafts only. Never sent.` and every `sent` flag is forced to **false**, even if the model tries to set it true. One successful save per run.

The language model itself (GPT-5.6-luna via Portkey) is not a “tool” the agent calls; it is the reasoner that chooses among the tools above.

---

## Stopping rules

The agent is **done** when it has finished the task the human asked for, or when the harness cuts it off.

**Done (success)**

- **Profile a company:** crawl the seed site, then `save_company_profile` once. Stop. Do not keep browsing.
- **Find targets and draft email:** read the profile, search, crawl only mutual-fit candidates, then `save_targets` and `save_emails` once each. Stop when the requested number of targets is saved (3 in the Sierra run), even if page or search budget remains.
- If the human is not asking for a profile or for targets, refuse in a short answer and **do not** call tools.

**Must stop (limits and failures)**

- **Model turns:** at most **10** LLM requests for a profile run; at most **18** for a target run.
- **Tool calls:** at most **8** successful tool uses for a profile run; at most **22** for a target run. Hitting the cap raises a usage-limit stop (`UsageLimitExceeded`); the audit log records `stop_reason: usage_limit`.
- **Pages:** 6 (profile) or 12 (targets). Further `fetch_page` calls get a “budget exhausted” message instead of loading more sites.
- **Searches:** 3. Further searches are refused.
- **Targets:** do not save more than requested; the save tool rejects more than 5.
- **Bad or missing inputs:** profile mode without `--url`, or target mode without a readable `--profile` file, exits before the agent starts.
- **Blocked URL or private network:** the fetch is refused; the agent should skip that candidate, not retry forever.
- **Crashes:** exceptions are written to the audit log with `stop_reason: error`.
- **Normal finish:** `stop_reason: end` in `output/audit_log.json`.

A new run **appends** to the audit log; it does not erase earlier Sierra profile or target runs.

---

## Guardrails

These rules live in `prompts/sales_agent.md` and are enforced again in Python so a persuasive model cannot talk its way around them.

**Truth**

- Do not invent facts, metrics, buyer names, tech-stack vendors, or email addresses.
- Profile fields must come from pages actually fetched. If something is missing, leave it empty and list it in `fields_not_found`.
- Email copy may only refer to context from search or crawled pages (no fake “I loved your Q3 earnings”).
- Missing public email is an empty list `[]`, not a guessed `info@` address.

**Who may be a “target”**

- Keep a company only if there is **mutual fit**: they look like the seller’s ideal customer *and* the seller actually sells something that would help, with evidence.
- Do not pick a random small business, a competitor (other CX-agent / chatbot platforms such as Decagon, Ada, Intercom Fin, Zendesk AI), or a famous brand only because it is famous.
- Do not pitch companies already listed as the seller’s customers.
- The seller’s own domain (e.g. `sierra.ai`) cannot be crawled as a customer.

**Email**

- **Never send email.** There is no SMTP, mailbox, or “send” tool.
- Drafts are files only. `sent` is always false.

**Cost**

- Prefer one focused web search over many.
- Truncate page text and audit summaries so prompts do not grow without bound.
- Web search uses a **low** search-context setting.
- Hard caps on pages, searches, model turns, and tool calls (see Stopping rules).
- Keys are not passed on the command line.

**Unsafe browsing**

- Only `http`/`https`. No `file://`, no credentials in the URL.
- No localhost, cloud-metadata, or private/reserved IP addresses (SSRF protection).
- In profile mode, stay on the seed company’s host.
- In target mode, fetch only hosts that appeared in web-search results and passed the allowlist (max 10). Off-site redirects are dropped.
- Headless Chromium: JavaScript may run so modern sites load; the agent must not click, type into forms, download files, or authenticate.
- Do not use web search while building a site-only company profile.

**Secrets and logging**

- `PORTKEY_API_KEY` lives only in `.env`.
- Audit logs store tool argument/result **summaries**, not secrets and not entire page dumps.

Together, the prompt, the tool implementations, and PydanticAI `UsageLimits` are the harness: the model proposes actions; the script decides what is allowed and when the loop ends.
