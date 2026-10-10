#!/usr/bin/env python3
"""Render dashboard.html from the seller profile, targets, and draft emails."""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
from pathlib import Path

HW2 = Path(__file__).resolve().parent
DEFAULT_PROFILE = HW2 / "assets" / "company_profile.json"
DEFAULT_TARGETS = HW2 / "output" / "targets.json"
DEFAULT_EMAILS = HW2 / "output" / "emails.json"
DEFAULT_OUT = HW2 / "dashboard.html"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the Sierra sales dashboard HTML")
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--targets", type=Path, default=DEFAULT_TARGETS)
    parser.add_argument("--emails", type=Path, default=DEFAULT_EMAILS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args()


def load_json(path: Path) -> dict:
    if not path.is_file():
        sys.exit(f"Missing {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def list_or_empty(value: object) -> list:
    return value if isinstance(value, list) else []


def chips(items: list, extra_class: str = "") -> str:
    bits = []
    for item in items:
        if isinstance(item, dict):
            label = item.get("name") or item.get("claim") or item.get("title") or ""
        else:
            label = item
        if not label:
            continue
        bits.append(f'<span class="chip {extra_class}">{esc(label)}</span>')
    return "".join(bits) if bits else '<span class="muted">None listed</span>'


def email_for_target(emails_doc: dict, company_name: str) -> dict | None:
    for item in list_or_empty(emails_doc.get("emails")):
        if item.get("company_name") == company_name:
            return item
    return None


def render(profile: dict, targets_doc: dict, emails_doc: dict, logo_src: str) -> str:
    seller = profile.get("company_name") or targets_doc.get("seller_name") or "Seller"
    seller_url = profile.get("company_url") or targets_doc.get("seller_url") or ""
    tagline = profile.get("tagline_or_one_liner") or ""
    products = list_or_empty(profile.get("products_and_services"))
    industries = list_or_empty(profile.get("industries"))
    channels = list_or_empty(profile.get("customer_channels"))
    offices = list_or_empty((profile.get("geography") or {}).get("offices"))
    leadership = list_or_empty(profile.get("leadership_or_executives_named"))
    icp = list_or_empty(profile.get("icp_evidence"))
    who = list_or_empty(profile.get("who_they_sell_to"))
    targets = list_or_empty(targets_doc.get("targets"))
    drafts = list_or_empty(emails_doc.get("emails"))

    with_email = sum(1 for t in targets if list_or_empty(t.get("contact_emails")))
    unsent = sum(1 for e in drafts if not e.get("sent"))

    product_cards = []
    for prod in products:
        product_cards.append(
            "<article class='card product'>"
            f"<h3>{esc(prod.get('name'))}</h3>"
            f"<p>{esc(prod.get('description'))}</p>"
            f"<p class='muted'>{esc(prod.get('value_proposition'))}</p>"
            "</article>"
        )

    leader_html = "".join(
        f"<li><strong>{esc(p.get('name'))}</strong> "
        f"<span class='muted'>{esc(p.get('title'))}</span></li>"
        for p in leadership
    )

    icp_html = "".join(
        "<li>"
        f"<strong>{esc(row.get('icp_criterion'))}</strong>"
        f"<p>{esc(row.get('site_evidence'))}</p>"
        "</li>"
        for row in icp
    )

    target_cards = []
    for idx, tgt in enumerate(targets, start=1):
        name = tgt.get("company_name") or "Target"
        url = tgt.get("company_url") or ""
        contacts = list_or_empty(tgt.get("contact_emails"))
        if contacts:
            mail_html = " ".join(
                f'<a class="chip" href="mailto:{esc(addr)}">{esc(addr)}</a>' for addr in contacts
            )
        else:
            mail_html = '<span class="chip warn">No public email found</span>'
        draft = email_for_target(emails_doc, name)
        draft_link = f'<a class="text-link" href="#email-{idx}">Open draft</a>' if draft else ""
        target_cards.append(
            f"<article class='card target' id='target-{idx}'>"
            f"<p class='kicker'>Target {idx:02d}</p>"
            f"<h3>{esc(name)}</h3>"
            f"<p><a class='text-link' href='{esc(url)}'>{esc(url)}</a> {draft_link}</p>"
            f"<div class='chip-row'><span class='chip-label'>Contact</span>{mail_html}</div>"
            f"<h4>Why they fit</h4><p>{esc(tgt.get('mutual_fit_reason'))}</p>"
            f"<h4>Business context</h4><p>{esc(tgt.get('business_context'))}</p>"
            "</article>"
        )

    email_blocks = []
    for idx, draft in enumerate(drafts, start=1):
        to_list = list_or_empty(draft.get("to_emails"))
        to_line = ", ".join(to_list) if to_list else "No public To: address (draft only)"
        status = "Unsent draft" if not draft.get("sent") else "Marked sent"
        body = esc(draft.get("body") or "").replace("\n", "<br>\n")
        email_blocks.append(
            f"<article class='card email' id='email-{idx}'>"
            f"<p class='kicker'>{esc(status)}</p>"
            f"<h3>{esc(draft.get('company_name'))}</h3>"
            f"<p class='meta'><span>To</span> {esc(to_line)}</p>"
            f"<p class='meta'><span>Subject</span> {esc(draft.get('subject'))}</p>"
            f"<div class='letter'>{body}</div>"
            "</article>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(seller)} sales workspace</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #f4f7f2;
      --surface: #ffffff;
      --text: #14261a;
      --muted: #5a6b60;
      --green: #1f6b43;
      --green-2: #2f8f58;
      --mint: #e6f5eb;
      --peach: #ffe8cc;
      --sky: #d9eefc;
      --border: #cfe0d4;
      --warn: #b86a00;
      --radius: 18px;
      --shadow: 0 18px 40px rgba(20, 70, 40, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      font-family: Inter, -apple-system, Segoe UI, Roboto, sans-serif;
      color: var(--text);
      line-height: 1.55;
      background:
        radial-gradient(900px 520px at -8% -20%, #b7f0c8 0%, transparent 58%),
        radial-gradient(720px 420px at 108% 0%, #ffd9a8 0%, transparent 52%),
        radial-gradient(640px 380px at 80% 110%, #c5e8ff 0%, transparent 50%),
        linear-gradient(180deg, #f7fbf6 0%, #eef6f0 40%, #f7f4ee 100%);
      min-height: 100vh;
    }}
    a {{ color: var(--green); }}
    .wrap {{ max-width: 1120px; margin: 0 auto; padding: 28px 20px 80px; }}
    header.hero {{
      padding: 12px 0 8px;
    }}
    .brand {{
      display: flex; justify-content: space-between; gap: 16px; flex-wrap: wrap;
      align-items: center;
      padding: 10px 4px 18px;
    }}
    .logo img {{
      height: 42px;
      width: auto;
      display: block;
    }}
    nav a {{
      color: var(--muted); text-decoration: none; margin-left: 18px; font-size: 14px; font-weight: 500;
    }}
    nav a:hover {{ color: var(--green); }}
    .hero-panel {{
      background: linear-gradient(135deg, rgba(255,255,255,0.92), rgba(230,245,235,0.9) 55%, rgba(255,232,204,0.55));
      border: 1px solid rgba(31, 107, 67, 0.12);
      border-radius: 28px;
      padding: 36px 36px 28px;
      box-shadow: var(--shadow);
      position: relative;
      overflow: hidden;
    }}
    .hero-panel::after {{
      content: "";
      position: absolute;
      width: 220px; height: 220px;
      right: -40px; top: -50px;
      background: radial-gradient(circle, #7be39a 0%, transparent 70%);
      opacity: 0.45;
      pointer-events: none;
    }}
    h1 {{
      font-size: clamp(2.2rem, 5vw, 3.6rem);
      font-weight: 700;
      letter-spacing: -0.04em;
      line-height: 1.08;
      margin: 0 0 14px;
      max-width: 12em;
      color: var(--green);
      position: relative;
    }}
    .lede {{ color: var(--muted); max-width: 62ch; font-size: 1.05rem; position: relative; }}
    .kpis {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 12px;
      margin: 26px 0 0;
      position: relative;
    }}
    .kpi {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 16px 18px;
      box-shadow: 0 8px 20px rgba(31, 107, 67, 0.05);
    }}
    .kpi .n {{ font-size: 1.8rem; font-weight: 700; color: var(--green); }}
    .kpi .l {{ color: var(--muted); font-size: 13px; }}
    section {{ margin-top: 56px; }}
    h2 {{
      font-size: 1.75rem; letter-spacing: -0.03em; margin: 0 0 8px; color: var(--text);
    }}
    .section-lede {{ color: var(--muted); margin: 0 0 20px; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 14px;
    }}
    .card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 20px;
      box-shadow: 0 10px 28px rgba(20, 70, 40, 0.05);
      transition: transform 0.18s ease, box-shadow 0.18s ease;
    }}
    .card:hover {{
      transform: translateY(-3px);
      box-shadow: 0 16px 36px rgba(31, 107, 67, 0.12);
    }}
    .card h3 {{ margin: 0 0 8px; font-size: 1.15rem; }}
    .card h4 {{ margin: 16px 0 6px; font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--green); }}
    .kicker {{
      text-transform: uppercase; letter-spacing: 0.12em; font-size: 11px; color: var(--green-2); margin: 0 0 8px; font-weight: 600;
    }}
    .muted {{ color: var(--muted); }}
    .chip-row {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 10px 0 4px; align-items: center; }}
    .chip-label {{ font-size: 12px; color: var(--muted); margin-right: 4px; }}
    .chip {{
      display: inline-block;
      border: 1px solid var(--border);
      background: var(--mint);
      border-radius: 999px;
      padding: 4px 10px;
      font-size: 12px;
      text-decoration: none;
      color: var(--green);
      font-weight: 500;
    }}
    .chip.warn {{ background: var(--peach); border-color: #f0c48a; color: var(--warn); }}
    .text-link {{ color: var(--green); font-weight: 600; }}
    @media (max-width: 800px) {{
      nav a {{ margin-left: 0; margin-right: 14px; }}
      .hero-panel {{ padding: 24px 20px; }}
    }}
    ul.plain {{ padding-left: 18px; }}
    ul.plain li {{ margin: 8px 0; }}
    .letter {{
      margin-top: 16px;
      padding: 18px;
      background: linear-gradient(180deg, #fffdf8, #f6f1e8);
      color: #14261a;
      border-radius: 12px;
      border: 1px solid var(--border);
      font-size: 14.5px;
      line-height: 1.6;
    }}
    .meta {{ margin: 6px 0; color: var(--muted); }}
    .meta span {{
      display: inline-block; min-width: 64px; color: var(--green); font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 600;
    }}
    footer {{
      margin-top: 64px; color: var(--muted); font-size: 13px; border-top: 1px solid var(--border); padding-top: 20px;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <header class="hero">
      <div class="brand">
        <a class="logo" href="https://sierra.ai"><img src="{esc(logo_src)}" alt="Sierra"></a>
        <nav>
          <a href="#seller">Seller</a>
          <a href="#targets">Targets</a>
          <a href="#emails">Drafts</a>
        </nav>
      </div>
      <div class="hero-panel">
      <h1>Sierra AI Sales Platform</h1>
      <p class="lede">{esc(tagline)}</p>
      <p class="lede"><a href="{esc(seller_url)}">{esc(seller_url)}</a> · Outcome-based conversational AI</p>
      <div class="kpis">
        <div class="kpi"><div class="n">{len(targets)}</div><div class="l">Target accounts</div></div>
        <div class="kpi"><div class="n">{len(drafts)}</div><div class="l">Outreach drafts loaded</div></div>
        <div class="kpi"><div class="n">{with_email}/{len(targets)}</div><div class="l">Public emails found</div></div>
        <div class="kpi"><div class="n">{unsent}</div><div class="l">Marked unsent</div></div>
      </div>
      </div>
    </header>

    <section id="seller">
      <h2>Who the seller is</h2>
      <p class="section-lede">{esc(profile.get("business_model"))}</p>
      <div class="chip-row">{chips(industries)}</div>
      <div class="grid" style="margin-top:18px">{''.join(product_cards)}</div>
      <div class="grid" style="margin-top:14px">
        <article class="card">
          <h3>Channels the platform covers</h3>
          <div class="chip-row">{chips(channels)}</div>
          <h4>Offices</h4>
          <div class="chip-row">{chips(offices)}</div>
        </article>
        <article class="card">
          <h3>Who they sell to</h3>
          <div class="chip-row">{chips(who)}</div>
          <h4>Founders named on-site</h4>
          <ul class="plain">{leader_html}</ul>
        </article>
      </div>
      <article class="card" style="margin-top:14px">
        <h3>ICP evidence from the company site</h3>
        <ul class="plain">{icp_html}</ul>
      </article>
    </section>

    <section id="targets">
      <h2>Target customers</h2>
      <p class="section-lede">Three healthcare systems with evidenced patient-access or automation programs. Contact chips are only addresses found on their public sites.</p>
      <div class="grid">{''.join(target_cards)}</div>
    </section>

    <section id="emails">
      <h2>Drafted emails</h2>
      <p class="section-lede">Full copy is loaded from output/emails.json.</p>
      {''.join(email_blocks)}
    </section>

    <footer>
      Source files: assets/company_profile.json, output/targets.json, output/emails.json.
      Link to Sierra: <a href="https://sierra.ai">https://sierra.ai</a>.
      Profiled {esc(profile.get("profiled_at"))}; targets {esc(targets_doc.get("created_at"))}.
    </footer>
  </div>
</body>
</html>
"""


def main() -> None:
    args = parse_args()
    profile = load_json(args.profile if args.profile.is_absolute() else HW2 / args.profile)
    targets = load_json(args.targets if args.targets.is_absolute() else HW2 / args.targets)
    emails = load_json(args.emails if args.emails.is_absolute() else HW2 / args.emails)
    out = args.out if args.out.is_absolute() else HW2 / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    logo = HW2 / "assets" / "sierra-logo.png"
    try:
        logo_src = Path(os.path.relpath(logo, out.parent)).as_posix()
    except Exception:
        logo_src = "../assets/sierra-logo.png"
    out.write_text(render(profile, targets, emails, logo_src), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
