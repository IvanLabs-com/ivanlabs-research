#!/usr/bin/env python3
"""Aggregate Study B output into stats.json and one SVG chart.

Pages are excluded when the render produced no body text (a failed render) or
when the "listing" page resolved to the same path as the homepage (counted once).

Usage: python3 analyze.py
"""
import csv
import json
import statistics as st
from collections import Counter
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
T = lambda v: v == "True"


def load():
    sites = list(csv.DictReader(open(OUT / "results.csv")))
    pages = list(csv.DictReader(open(OUT / "results-pages.csv")))
    kept, excluded, seen = [], [], set()
    for p in pages:
        key = (p["host"], p["url"])
        if int(p["words_rendered"] or 0) == 0:
            excluded.append(dict(host=p["host"], page_type=p["page_type"], reason="render produced no text"))
        elif key in seen:
            excluded.append(dict(host=p["host"], page_type=p["page_type"], reason="same path as another page"))
        else:
            seen.add(key)
            kept.append(p)
    return sites, kept, excluded


def stats(sites, pages, excluded):
    n = len(pages)
    pct = [float(p["pct_rendered_words_in_raw"]) for p in pages]
    both = lambda f: [p for p in pages if T(p[f"{f}_raw"]) and T(p[f"{f}_rendered"])]
    links_up = [p for p in pages if int(p["links_rendered"]) > int(p["links_raw"])]
    links_up10 = [p for p in pages if int(p["links_rendered"]) >= 1.1 * max(int(p["links_raw"]), 1)]
    ok_sites = sorted({p["host"] for p in pages})
    return dict(
        sites_total=len(sites),
        site_status=dict(Counter(s["status"] for s in sites)),
        sites_analysed=len(ok_sites),
        frameworks_by_site=dict(Counter(next(p["framework"] for p in pages if p["host"] == h) for h in ok_sites)),
        pages_analysed=n,
        pages_excluded=excluded,
        median_pct_rendered_words_in_raw=st.median(pct),
        pages_ge_90pct=sum(x >= 90 for x in pct),
        pages_50_to_90pct=sum(50 <= x < 90 for x in pct),
        pages_lt_50pct=sum(x < 50 for x in pct),
        title_in_raw=sum(T(p["title_raw"]) for p in pages),
        description_in_raw=sum(T(p["description_raw"]) for p in pages),
        canonical_in_raw=sum(T(p["canonical_raw"]) for p in pages),
        h1_in_raw=sum(T(p["h1_raw"]) for p in pages),
        h1_in_rendered=sum(T(p["h1_rendered"]) for p in pages),
        h1_only_after_render=sum(not T(p["h1_raw"]) and T(p["h1_rendered"]) for p in pages),
        h1_gone_after_render=sum(T(p["h1_raw"]) and not T(p["h1_rendered"]) for p in pages),
        title_changed_by_js=sum(not T(p["title_equal"]) for p in both("title")),
        description_changed_by_js=sum(not T(p["description_equal"]) for p in both("description")),
        canonical_changed_by_js=sum(not T(p["canonical_equal"]) for p in both("canonical")),
        h1_changed_by_js=sum(not T(p["h1_equal"]) for p in both("h1")),
        robots_meta_differs=sum(not T(p["robots_equal"]) for p in pages),
        pages_more_links_after_render=len(links_up),
        pages_10pct_more_links_after_render=len(links_up10),
        pages_with_no_href_clickables=sum(int(p["no_href_clickables_rendered"]) > 0 for p in pages),
        pages_with_query_links=sum(int(p["query_urls_rendered"]) > 0 for p in pages),
        sites_with_query_links=len({p["host"] for p in pages if int(p["query_urls_rendered"]) > 0}),
        max_query_links_on_a_page=max(int(p["query_urls_rendered"]) for p in pages),
        pages_render_timeout=sum(p["render_note"].startswith("timeout") for p in pages),
    )


FONT = "system-ui, -apple-system, sans-serif"
INK, MUTED, GRID, BG, HEAD = "#1A1A1A", "#6B7280", "#E5E7EB", "#FAFAF9", "#0F172A"
COLORS = {"≥90%": "#10B981", "50–89%": "#1346BE", "<50%": "#EF4444"}


def chart(s, path, day):
    """One stacked bar: share of pages by how much rendered text was already in the raw HTML."""
    w, h, left, width, top = 720, 230, 40, 640, 96
    n = s["pages_analysed"]
    parts = [("≥90%", s["pages_ge_90pct"]), ("50–89%", s["pages_50_to_90pct"]), ("<50%", s["pages_lt_50pct"])]
    title = "How much of the rendered page was already in the raw HTML?"
    aria = (f"Of {n} pages on {s['sites_analysed']} JavaScript-framework sites, {parts[0][1]} had at least 90% of their "
            f"rendered text in the raw HTML, {parts[1][1]} had 50 to 89%, and {parts[2][1]} had under 50%.")
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="{escape(aria)}">',
           f'<rect width="{w}" height="{h}" rx="8" fill="{BG}"/>',
           f'<rect width="{w}" height="44" rx="8" fill="{HEAD}"/><rect y="36" width="{w}" height="8" fill="{HEAD}"/>',
           f'<text x="{w / 2}" y="28" text-anchor="middle" font-family="{FONT}" font-size="14" font-weight="600" fill="#F9FAFB">{escape(title)}</text>',
           f'<text x="{left}" y="76" font-family="{FONT}" font-size="12" fill="{INK}">Share of rendered words present in the raw HTML, per page ({n} pages, {s["sites_analysed"]} sites)</text>']
    x = left
    for label, c in parts:
        bw = width * c / n
        out.append(f'<rect x="{x:.1f}" y="{top}" width="{bw:.1f}" height="40" fill="{COLORS[label]}"/>')
        if bw > 60:
            out.append(f'<text x="{x + bw / 2:.1f}" y="{top + 25}" text-anchor="middle" font-family="{FONT}" font-size="13" font-weight="600" fill="#FFFFFF">{c}</text>')
        x += bw
    lx = left
    for label, c in parts:
        out.append(f'<rect x="{lx}" y="{top + 58}" width="12" height="12" rx="2" fill="{COLORS[label]}"/>')
        out.append(f'<text x="{lx + 18}" y="{top + 69}" font-family="{FONT}" font-size="12" fill="{INK}">{escape(label)} in raw HTML: {c} pages</text>')
        lx += 210
    out.append(f'<text x="{left}" y="{h - 16}" font-family="{FONT}" font-size="11" fill="{MUTED}">IvanLabs Study B, {day}. Raw = plain GET; rendered = headless Chrome after network idle (15 s cap).</text>')
    out.append("</svg>")
    path.write_text("\n".join(out) + "\n")


def main():
    sites, pages, excluded = load()
    s = stats(sites, pages, excluded)
    (OUT / "stats.json").write_text(json.dumps(s, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(s, indent=1, ensure_ascii=False))
    day = json.loads((OUT / "run.json").read_text())["started"][:10]
    chart(s, OUT / "render-gap-study.svg", day)


if __name__ == "__main__":
    main()
