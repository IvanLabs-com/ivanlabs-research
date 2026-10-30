#!/usr/bin/env python3
"""Aggregate Study A output into stats.json and two SVG charts.

Only sites with status "ok" are analysed; a site blocked part-way through is
excluded even if some of its sitemaps were read.

Usage: python3 analyze.py
"""
import csv
import json
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"

STATUS_LABELS = [
    ("ok", "Sitemaps read"),
    ("no_sitemap_found", "No sitemap in robots.txt or default paths"),
    ("robots_disallows_ua", "robots.txt disallows unlisted bots"),
    ("blocked", "Blocked (403, 418, 429 or bot wall)"),
    ("timeout", "Timed out"),
]


def load():
    sites = list(csv.DictReader(open(OUT / "results.csv")))
    files = list(csv.DictReader(open(OUT / "results-sitemaps.csv")))
    manual = {r["host"]: r for r in csv.DictReader(open(HERE / "scheme_manual.csv"))}
    return sites, files, manual


def stats(sites, files, manual):
    ok = [s for s in sites if s["status"] == "ok"]
    okh = {s["host"] for s in ok}
    files = [f for f in files if f["host"] in okh]
    by_site = defaultdict(list)
    for f in files:
        by_site[f["host"]].append(f)
    n = len(ok)
    idx = [s for s in ok if int(s["index_levels"]) >= 1]
    idx_lm = [s for s in idx if s["pct_index_lastmod"] not in ("", "0.0")]
    url_lm_sites = [h for h, fs in by_site.items() if st.median(float(f["pct_lastmod"] or 0) for f in fs) >= 50]
    counts = [int(f["url_count"]) for f in files]
    schemes = Counter()
    for s in ok:
        for part in manual[s["host"]]["scheme_manual"].split("+"):
            schemes[part] += 1
    any_flag = lambda k: sorted(h for h, fs in by_site.items() if any(f[k] == "True" for f in fs))
    any_pos = lambda k: sorted(h for h, fs in by_site.items() if any(float(f[k] or 0) > 0 for f in fs))
    declared = sorted(int(s["n_declared"]) for s in ok)
    return dict(
        sites_total=len(sites),
        status=dict(Counter(s["status"] for s in sites)),
        sites_ok=n,
        files_analysed=len(files),
        declared_in_robots=sum(s["declared_in_robots"] == "True" for s in ok),
        declared_count_median=st.median(declared), declared_count_max=max(declared),
        use_index=len(idx), nested_index=sum(int(s["index_levels"]) >= 2 for s in ok),
        index_children_median=st.median(int(s["n_child_sitemaps"]) for s in idx),
        index_children_max=max(int(s["n_child_sitemaps"]) for s in idx),
        index_lastmod_sites=len(idx_lm),
        index_lastmod_identical=sorted(s["host"] for s in idx_lm if s["identical_child_lastmod"] == "True"),
        url_lastmod_sites=len(url_lm_sites),
        urls_per_file_median=st.median(counts), urls_per_file_max=max(counts),
        files_at_50000=sum(c == 50000 for c in counts), files_ge_45000=sum(c >= 45000 for c in counts),
        files_empty=sum(c == 0 for c in counts),
        files_over_limit=sum(f["over_url_limit"] == "True" or f["over_size_limit"] == "True" for f in files),
        bytes_max=max(int(f["bytes_uncompressed"]) for f in files),
        scheme_parts=dict(schemes),
        scheme_ambiguous=sorted(h for h in okh if manual[h]["ambiguous"] == "yes"),
        sites_with_query_urls=any_pos("pct_query"),
        sites_with_other_host_urls=any_pos("pct_other_host"),
        sites_with_non_https_urls=any_pos("pct_non_https"),
        sites_hreflang=any_flag("hreflang"), sites_image=any_flag("image_ext"),
        sites_video=any_flag("video_ext"), sites_news=any_flag("news_ext"),
        sites_nonstandard_ns=sorted(s["host"] for s in ok if s["nonstandard_ns"] == "True"),
    )


# --- SVG helpers, styled like the site's existing blog figures ---------------
FONT = "system-ui, -apple-system, sans-serif"
INK, MUTED, GRID, BG, BAR, HEAD = "#1A1A1A", "#6B7280", "#E5E7EB", "#FAFAF9", "#1346BE", "#0F172A"


def frame(w, h, title, aria):
    return [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="{escape(aria)}">',
            f'<rect width="{w}" height="{h}" rx="8" fill="{BG}"/>',
            f'<rect width="{w}" height="44" rx="8" fill="{HEAD}"/><rect y="36" width="{w}" height="8" fill="{HEAD}"/>',
            f'<text x="{w / 2}" y="28" text-anchor="middle" font-family="{FONT}" font-size="14" font-weight="600" fill="#F9FAFB">{escape(title)}</text>']


def hbars(rows, total, title, aria, note, path, w=720):
    """rows: [(label, count)] drawn as share of `total`."""
    left, top, bar_h, gap, width = 300, 64, 22, 12, 330
    h = top + len(rows) * (bar_h + gap) + 44
    out = frame(w, h, title, aria)
    for i, (label, c) in enumerate(rows):
        y = top + i * (bar_h + gap)
        bw = width * c / total if total else 0
        out.append(f'<text x="{left - 12}" y="{y + 15}" text-anchor="end" font-family="{FONT}" font-size="12" fill="{INK}">{escape(label)}</text>')
        out.append(f'<rect x="{left}" y="{y}" width="{width}" height="{bar_h}" rx="3" fill="{GRID}"/>')
        out.append(f'<rect x="{left}" y="{y}" width="{bw:.1f}" height="{bar_h}" rx="3" fill="{BAR}"/>')
        out.append(f'<text x="{left + width + 10}" y="{y + 15}" font-family="{FONT}" font-size="12" font-weight="600" fill="{INK}">{c} of {total}</text>')
    out.append(f'<text x="24" y="{h - 16}" font-family="{FONT}" font-size="11" fill="{MUTED}">{escape(note)}</text>')
    out.append("</svg>")
    path.write_text("\n".join(out) + "\n")


def main():
    sites, files, manual = load()
    s = stats(sites, files, manual)
    (OUT / "stats.json").write_text(json.dumps(s, indent=1) + "\n")
    print(json.dumps(s, indent=1))

    run = json.loads((OUT / "run.json").read_text())
    day = run["started"][:10]
    hbars([(label, s["status"].get(k, 0)) for k, label in STATUS_LABELS], s["sites_total"],
          "What happened when a polite bot asked 40 large sites for their sitemaps",
          f"Of 40 large sites, {s['sites_ok']} served sitemaps to an identified research bot; the rest had no discoverable sitemap, disallowed unlisted bots, blocked the request or timed out.",
          f"IvanLabs Study A, {day}. User-Agent IvanLabsResearch/1.0, robots.txt respected, ≤15 requests per site.",
          OUT / "sitemap-study-access.svg")
    n = s["sites_ok"]
    hbars([("Declared in robots.txt", s["declared_in_robots"]),
           ("Uses a sitemap index", s["use_index"]),
           ("lastmod on index entries", s["index_lastmod_sites"]),
           ("lastmod on most URLs", s["url_lastmod_sites"]),
           ("Image sitemap extension", len(s["sites_image"])),
           ("Query-string URLs listed", len(s["sites_with_query_urls"])),
           ("hreflang in sitemaps", len(s["sites_hreflang"])),
           ("News sitemap extension", len(s["sites_news"]))],
          n, f"How {n} large sites build their XML sitemaps",
          f"Sitemap practices across {n} large sites: all declare sitemaps in robots.txt and {s['use_index']} use a sitemap index; lastmod, image, query-string, hreflang and news usage vary.",
          f"IvanLabs Study A, {day}. {s['files_analysed']} child sitemaps sampled (up to 10 per site, seeded).",
          OUT / "sitemap-study-practices.svg")


if __name__ == "__main__":
    main()
