#!/usr/bin/env python3
"""Build a Plotly dashboard from extracted lease JSON."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

import plotly.express as px
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs

ROOT = Path(__file__).resolve().parent
LEASES_PATH = ROOT / "data" / "leases_test.json"
GEO_PATH = ROOT / "data" / "geocodes.json"
OUTPUT_PATH = ROOT / "dashboard.html"

DATE_FMT = "%B %d, %Y"
YALE_BLUE = "#00356b"
YALE_MEDIUM = "#286dc0"
YALE_LIGHT = "#63aaff"
YALE_PALE = "#c9d7e8"
YALE_SCALE = [[0, YALE_PALE], [0.45, YALE_MEDIUM], [1, YALE_BLUE]]
STRUCTURE_COLORS = {
    "Triple Net (NNN)": YALE_BLUE,
    "Modified Gross": YALE_MEDIUM,
    "Gross": YALE_LIGHT,
    "TBD / Draft": "#978d85",
}
FALLBACK_COORDS = {
    "25 Science Park, Suite 410, New Haven, CT 06511": (41.3239343, -72.9275854),
}


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, DATE_FMT)
    except ValueError:
        return None


def city_from_address(address: str) -> str:
    match = re.search(r",\s*([^,]+),\s*CT", address)
    return match.group(1).strip() if match else "Unknown"


def money(value: float | None) -> str:
    if value is None:
        return "—"
    return f"${value:,.0f}"


def load_rows() -> list[dict]:
    leases = json.loads(LEASES_PATH.read_text(encoding="utf-8"))
    geocodes = json.loads(GEO_PATH.read_text(encoding="utf-8")) if GEO_PATH.is_file() else {}
    rows = []
    for lease in leases:
        geo = geocodes.get(lease["address"]) or {}
        lat = geo.get("lat")
        lon = geo.get("lon")
        if lat is None or lon is None:
            fallback = FALLBACK_COORDS.get(lease["address"])
            if fallback:
                lat, lon = fallback
        start = parse_date(lease.get("commencement_date"))
        end = parse_date(lease.get("expiration_date"))
        term_years = (end - start).days / 365.25 if start and end else None
        sf = lease.get("rentable_sqft")
        rent = lease.get("annual_base_rent")
        psf = lease.get("rent_per_sqft")
        implied_psf = (rent / sf) if (psf is None and rent and sf) else psf
        rows.append(
            {
                **lease,
                "lat": lat,
                "lon": lon,
                "city": city_from_address(lease["address"]),
                "start": start,
                "end": end,
                "term_years": term_years,
                "implied_psf": implied_psf,
                "structure_label": lease.get("lease_structure") or "TBD / Draft",
                "short_tenant": lease["tenant_name"].rstrip("."),
            }
        )
    return rows


def kpi_html(rows: list[dict]) -> str:
    rents = [r["annual_base_rent"] for r in rows if r["annual_base_rent"] is not None]
    sfs = [r["rentable_sqft"] for r in rows if r["rentable_sqft"] is not None]
    deposits = [r["security_deposit"] for r in rows if r["security_deposit"] is not None]
    terms = [r["term_years"] for r in rows if r["term_years"] is not None]
    total_rent = sum(rents)
    total_sf = sum(sfs)
    portfolio_psf = total_rent / total_sf if total_sf else None
    missing = sum(
        1
        for r in rows
        if r["rent_per_sqft"] is None or r["expiration_date"] is None or r["lease_structure"] is None or r["security_deposit"] is None
    )
    cards = [
        ("Leases", str(len(rows)), f"{missing} with incomplete terms"),
        ("Rentable area", f"{total_sf:,.0f} sf", f"{len(sfs)} spaces"),
        ("Annual base rent", money(total_rent), "portfolio total"),
        ("Portfolio $/sf", f"${portfolio_psf:,.2f}" if portfolio_psf else "—", "total rent ÷ total sf"),
        ("Security deposits", money(sum(deposits)), f"{len(deposits)} of {len(rows)} stated"),
        ("Avg term", f"{sum(terms) / len(terms):.1f} yrs" if terms else "—", f"{len(terms)} dated leases"),
    ]
    blocks = []
    for title, value, note in cards:
        blocks.append(
            f'<div class="kpi"><div class="kpi-label">{title}</div>'
            f'<div class="kpi-value">{value}</div>'
            f'<div class="kpi-note">{note}</div></div>'
        )
    return "\n".join(blocks)


def plot_records(rows: list[dict]) -> list[dict]:
    """Drop datetime objects so Plotly can serialize the traces."""
    skip = {"start", "end"}
    return [{k: v for k, v in row.items() if k not in skip} for row in rows]


def fig_map(rows: list[dict]) -> go.Figure:
    mapped = [r for r in plot_records(rows) if r["lat"] is not None and r["lon"] is not None]
    fig = px.scatter_mapbox(
        mapped,
        lat="lat",
        lon="lon",
        hover_name="short_tenant",
        hover_data={
            "address": True,
            "space_type": True,
            "rentable_sqft": ":,.0f",
            "annual_base_rent": ":$,.0f",
            "implied_psf": ":.2f",
            "structure_label": True,
            "lat": False,
            "lon": False,
        },
        size="annual_base_rent",
        size_max=28,
        color="implied_psf",
        color_continuous_scale=YALE_SCALE,
        zoom=9.4,
        center={"lat": 41.29, "lon": -72.91},
    )
    fig.update_layout(
        mapbox_style="open-street-map",
        margin=dict(l=0, r=0, t=48, b=0),
        title="Properties by location (size = annual rent, color = $/sf)",
        coloraxis_colorbar_title="$/sf",
        height=520,
    )
    return fig


def fig_rent_psf(rows: list[dict]) -> go.Figure:
    ordered = sorted(plot_records(rows), key=lambda r: (r["implied_psf"] is None, r["implied_psf"] or 0))
    colors = []
    for r in ordered:
        if r["rent_per_sqft"] is None:
            colors.append(YALE_LIGHT)
        else:
            colors.append(YALE_BLUE)
    fig = go.Figure(
        go.Bar(
            x=[r["implied_psf"] for r in ordered],
            y=[r["short_tenant"] for r in ordered],
            orientation="h",
            marker_color=colors,
            text=[f"${r['implied_psf']:.0f}" if r["implied_psf"] is not None else "—" for r in ordered],
            textposition="outside",
            hovertemplate="%{y}<br>$%{x:.2f} /sf<extra></extra>",
        )
    )
    fig.update_layout(
        title="In-place rent per square foot",
        xaxis_title="USD per sqft (light blue = implied from annual rent)",
        yaxis_title="",
        margin=dict(l=20, r=40, t=48, b=40),
        height=420,
        showlegend=False,
    )
    return fig


def fig_scatter(rows: list[dict]) -> go.Figure:
    fig = px.scatter(
        plot_records(rows),
        x="rentable_sqft",
        y="implied_psf",
        color="structure_label",
        size="annual_base_rent",
        hover_name="short_tenant",
        hover_data={"city": True, "space_type": True},
        title="Size vs. rent: industrial is cheap and large, downtown retail is small and expensive",
        color_discrete_map=STRUCTURE_COLORS,
    )
    fig.update_layout(
        xaxis_title="Rentable square feet",
        yaxis_title="Rent per sqft (USD)",
        legend_title="Lease structure",
        margin=dict(l=40, r=20, t=48, b=40),
        height=420,
    )
    return fig


def fig_structure(rows: list[dict]) -> go.Figure:
    counts = Counter(r["structure_label"] for r in plot_records(rows))
    fig = go.Figure(
        go.Pie(
            labels=list(counts.keys()),
            values=list(counts.values()),
            hole=0.45,
            textinfo="label+value",
            marker=dict(colors=[STRUCTURE_COLORS.get(label, YALE_BLUE) for label in counts]),
        )
    )
    fig.update_layout(
        title="Lease structure mix",
        margin=dict(l=20, r=20, t=48, b=20),
        height=420,
        showlegend=False,
    )
    return fig


def fig_timeline(rows: list[dict]) -> go.Figure:
    dated = sorted(
        [r for r in rows if r["start"] and r["end"]],
        key=lambda r: r["start"],
        reverse=True,
    )
    fig = go.Figure()
    for r in dated:
        fig.add_trace(
            go.Scatter(
                x=[r["start"].strftime("%Y-%m-%d"), r["end"].strftime("%Y-%m-%d")],
                y=[r["short_tenant"], r["short_tenant"]],
                mode="lines+markers",
                line=dict(width=8, color=YALE_BLUE),
                marker=dict(size=8, color=YALE_MEDIUM),
                name=r["short_tenant"],
                hovertemplate=(
                    f"{r['short_tenant']}<br>"
                    f"{r['commencement_date']} – {r['expiration_date']}<br>"
                    f"{r['term_years']:.1f} years<extra></extra>"
                ),
            )
        )
    fig.update_layout(
        title="Lease terms (Branford draft omitted — no expiration date)",
        xaxis_title="Year",
        yaxis_title="",
        showlegend=False,
        margin=dict(l=20, r=20, t=48, b=40),
        height=420,
    )
    return fig


def table_html(rows: list[dict]) -> str:
    header = [
        "Tenant",
        "City",
        "Type",
        "SF",
        "Annual rent",
        "$/sf",
        "Structure",
        "Term",
        "Deposit",
    ]
    thead = "".join(f"<th>{col}</th>" for col in header)
    body = []
    for r in sorted(rows, key=lambda x: -(x["annual_base_rent"] or 0)):
        term = (
            f"{r['commencement_date']} – {r['expiration_date']}"
            if r["expiration_date"]
            else f"{r['commencement_date']} – TBD"
        )
        psf = f"${r['implied_psf']:.2f}" if r["implied_psf"] is not None else "—"
        if r["rent_per_sqft"] is None and r["implied_psf"] is not None:
            psf += "*"
        body.append(
            "<tr>"
            f"<td>{r['short_tenant']}</td>"
            f"<td>{r['city']}</td>"
            f"<td>{r['space_type']}</td>"
            f"<td>{r['rentable_sqft']:,.0f}</td>"
            f"<td>{money(r['annual_base_rent'])}</td>"
            f"<td>{psf}</td>"
            f"<td>{r['structure_label']}</td>"
            f"<td>{term}</td>"
            f"<td>{money(r['security_deposit'])}</td>"
            "</tr>"
        )
    return f"<table><thead><tr>{thead}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def build_html(rows: list[dict]) -> str:
    figs = [
        fig_map(rows),
        fig_rent_psf(rows),
        fig_scatter(rows),
        fig_structure(rows),
        fig_timeline(rows),
    ]
    plot_divs = [figs[0].to_html(full_html=False, include_plotlyjs=False)]
    plot_divs.extend(fig.to_html(full_html=False, include_plotlyjs=False) for fig in figs[1:])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Greater New Haven Lease Dashboard</title>
  <script>{get_plotlyjs()}</script>
  <style>
    :root {{
      --ink: #00356b;
      --muted: #5b6770;
      --line: #c9d7e8;
      --bg: #eef3f8;
      --card: #ffffff;
      --accent: #00356b;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Source Serif 4", "Iowan Old Style", Georgia, serif;
      color: var(--ink);
      background: var(--bg);
    }}
    header {{
      padding: 32px 40px 16px;
      border-bottom: 1px solid var(--line);
      background: var(--accent);
    }}
    header p {{ margin: 8px 0 0; color: var(--muted); max-width: 720px; }}
    h1 {{ margin: 0; font-size: 28px; letter-spacing: -0.02em; color: #ffffff; }}
    main {{ padding: 24px 40px 48px; }}
    .kpis {{
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 20px;
    }}
    .kpi {{
      background: var(--card);
      border: 1px solid var(--line);
      padding: 14px 16px;
    }}
    .kpi-label {{ font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.06em; }}
    .kpi-value {{ font-size: 22px; margin-top: 6px; color: var(--accent); }}
    .kpi-note {{ font-size: 12px; color: var(--muted); margin-top: 4px; }}
    .panel {{
      background: var(--card);
      border: 1px solid var(--line);
      padding: 8px 8px 0;
      margin-bottom: 16px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: 1.3fr 0.7fr;
      gap: 16px;
    }}
    .grid-3 {{
      display: grid;
      grid-template-columns: 1fr 1fr 0.8fr;
      gap: 16px;
      margin-bottom: 16px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    th, td {{
      text-align: left;
      padding: 8px 10px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
    }}
    th {{ color: var(--muted); font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em; }}
    .note {{ color: var(--muted); font-size: 13px; margin-top: 8px; }}
    @media (max-width: 1100px) {{
      .kpis, .grid, .grid-3 {{ grid-template-columns: 1fr; }}
      header, main {{ padding-left: 20px; padding-right: 20px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Greater New Haven commercial leases</h1>
  </header>
  <main>
    <section class="kpis">{kpi_html(rows)}</section>
    <section class="panel">{plot_divs[0]}</section>
    <section class="grid-3">
      <div class="panel">{plot_divs[1]}</div>
      <div class="panel">{plot_divs[2]}</div>
      <div class="panel">{plot_divs[3]}</div>
    </section>
    <section class="panel">{plot_divs[4]}</section>
    <section class="panel" style="padding: 16px 20px 24px;">
      <h2 style="margin: 8px 0 12px; font-size: 18px;">Lease detail</h2>
      {table_html(rows)}
      <p class="note">* State Street rent per square foot was not stated in the draft; the table shows annual rent ÷ square footage. Branford has no expiration or expense structure yet. Coordinates from OpenStreetMap Nominatim; Science Park uses the Science Park campus point.</p>
    </section>
  </main>
</body>
</html>
"""


def main() -> None:
    rows = load_rows()
    missing_geo = [r["address"] for r in rows if r["lat"] is None]
    if missing_geo:
        raise SystemExit(f"Missing coordinates for: {missing_geo}")
    OUTPUT_PATH.write_text(build_html(rows), encoding="utf-8")
    print(f"Wrote dashboard to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
