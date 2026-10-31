#!/usr/bin/env python3
"""Study B: raw vs rendered HTML on JavaScript-framework sites.

For each site in sites.csv: fetch robots.txt, then the homepage, one listing
page and one detail page, both as raw HTML (plain GET) and as a rendered DOM
(Playwright Chromium, network idle, 15 s cap). Compare what a crawler sees
before and after JavaScript runs.

Etiquette (see ../README.md): serial, >=1 s between requests to a host, 20 s
timeout for raw fetches, honest User-Agent on raw fetches (Playwright keeps its
default headless UA), robots.txt checked before every page, stop on
401/403/418/429 or a bot challenge. Raw responses go to cache/, the request log
to data/; both are git-ignored. output/ holds structural facts only.

Usage:
    python3 study.py [--sites sites.csv] [--only host ...]
"""
import argparse
import csv
import gzip
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
import urllib.robotparser
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from playwright.sync_api import sync_playwright

USER_AGENT = "IvanLabsResearch/1.0 (+https://ivanlabs.com/contact/)"
TIMEOUT = 20
RENDER_TIMEOUT_MS = 15_000
MIN_INTERVAL = 1.1
MAX_BYTES = 10 * 1024 * 1024

HERE = Path(__file__).resolve().parent
CACHE, DATA, OUT = HERE / "cache", HERE / "data", HERE / "output"

MARKERS = {
    "nextjs": [r'id="__NEXT_DATA__"', r'/_next/static/', r'self\.__next_f'],
    "nuxt": [r'window\.__NUXT__', r'id="__nuxt"', r'/_nuxt/', r'data-nuxt'],
    "angular": [r'ng-version="', r'<app-root', r'ng-server-context'],
    "sveltekit": [r'data-sveltekit', r'/_app/immutable/', r'__sveltekit_'],
    "remix": [r'__remixContext', r'window\.__remixManifest', r'__reactRouterContext'],
    "gatsby": [r'id="___gatsby"', r'/page-data/', r'window\.___'],
}
CHALLENGE = re.compile(r"captcha|cf-chl|challenge-platform|px-captcha|are you a robot|datadome|access denied", re.I)
LISTING_HINT = re.compile(r"/(blog|news|category|categories|c|shop|products|collections|templates|plugins|"
                          r"modules|integrations|docs|guides|tutorials|stories|destinations|deals|jobs|search|"
                          r"homes|for-sale|browse|explore|community|archive|articles|events)/?$", re.I)


class Blocked(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Page(HTMLParser):
    """Collects the SEO-relevant structure of one HTML document."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = None
        self.meta = {}
        self.canonical = None
        self.h1 = []
        self.links = []
        self.no_href_links = 0
        self.text = []
        self._skip = 0
        self._in = None

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag in ("script", "style", "noscript", "template", "svg"):
            self._skip += 1
        elif tag == "title" and self.title is None:
            self._in, self.title = "title", ""
        elif tag == "h1":
            self._in = "h1"
            self.h1.append("")
        elif tag == "meta" and a.get("name", "").lower() in ("description", "robots"):
            self.meta[a["name"].lower()] = a.get("content", "").strip()
        elif tag == "link" and "canonical" in a.get("rel", "").lower().split():
            self.canonical = a.get("href", "").strip()
        if tag == "a":
            if "href" in a and a["href"].strip():
                self.links.append(a["href"].strip())
            else:
                self.no_href_links += 1
        elif a.get("role") == "link" and "href" not in a:
            self.no_href_links += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "template", "svg") and self._skip:
            self._skip -= 1
        elif tag in ("title", "h1"):
            self._in = None

    def handle_data(self, data):
        if self._skip:
            return
        if self._in == "title":
            self.title += data
            return  # the <title> is not visible body text
        if self._in == "h1":
            self.h1[-1] += data
        self.text.append(data)

    def words(self):
        return re.findall(r"\w{2,}", " ".join(self.text).lower())


def parse(html):
    p = Page()
    try:
        p.feed(html)
    except Exception:
        pass
    return p


class Raw:
    def __init__(self, host, log):
        self.host, self.log, self.last, self.robots = host, log, 0.0, None

    def get(self, url, check_robots=True):
        if check_robots and self.robots is not None and not self.robots.can_fetch(USER_AGENT, url):
            self.log.append(dict(host=self.host, url=url, ts=now(), kind="raw", status="disallowed"))
            return None, None
        wait = self.last + MIN_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        ts = now()
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                status, final, body = r.status, r.geturl(), r.read(MAX_BYTES)
        except urllib.error.HTTPError as e:
            status, final, body = e.code, url, b""
        except Exception as e:
            self.last = time.monotonic()
            self.log.append(dict(host=self.host, url=url, ts=ts, kind="raw", status=f"error:{type(e).__name__}"))
            return None, None
        self.last = time.monotonic()
        self.log.append(dict(host=self.host, url=url, ts=ts, kind="raw", status=status, final=final, bytes=len(body)))
        if status in (401, 403, 418, 429) or (status < 300 and status != 200):
            raise Blocked(f"{status} {url}")
        while body[:2] == b"\x1f\x8b":
            body = gzip.decompress(body)
        text = body.decode("utf-8", "replace")
        if status == 200 and not url.endswith("robots.txt") and CHALLENGE.search(text[:20000]) and len(text) < 50000:
            raise Blocked(f"challenge {url}")
        f = CACHE / self.host / (hashlib.sha1(url.encode()).hexdigest() + ".raw.html")
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
        return status, (final, text)


def detect(html):
    found = [fw for fw, pats in MARKERS.items() if any(re.search(p, html) for p in pats)]
    return found


def internal(links, base):
    host = urlsplit(base).hostname.removeprefix("www.")
    out = []
    for l in links:
        if l.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        u = urljoin(base, l)
        h = urlsplit(u).hostname or ""
        if h.removeprefix("www.") == host and urlsplit(u).scheme in ("http", "https"):
            out.append(u.split("#")[0])
    return out


def pick_pages(home_url, links):
    """Listing: a section-like URL; detail: a deeper URL under the same section."""
    links = list(dict.fromkeys(l for l in links if "?" not in l))
    depth = lambda u: len([s for s in urlsplit(u).path.split("/") if s])
    listing = next((l for l in links if LISTING_HINT.search(urlsplit(l).path)), None)
    if listing is None:
        firsts = Counter("/" + urlsplit(l).path.strip("/").split("/")[0] for l in links if depth(l) >= 2)
        if firsts:
            listing = urljoin(home_url, firsts.most_common(1)[0][0] + "/")
    detail = None
    if listing:
        prefix = urlsplit(listing).path.rstrip("/") + "/"
        cands = [l for l in links if urlsplit(l).path.startswith(prefix) and depth(l) > depth(listing)]
        detail = cands[0] if cands else None
    if detail is None:
        cands = [l for l in links if depth(l) >= 2 and l != listing]
        detail = max(cands, key=depth) if cands else None
    return listing, detail


def compare(raw_html, rendered_html, url):
    r, d = parse(raw_html), parse(rendered_html)
    rw, dw = Counter(r.words()), Counter(d.words())
    overlap = sum(min(c, rw[w]) for w, c in dw.items())
    total = sum(dw.values())
    norm = lambda s: re.sub(r"\s+", " ", (s or "")).strip()
    field = {}
    for name, rv, dv in [("title", r.title, d.title), ("description", r.meta.get("description"), d.meta.get("description")),
                         ("canonical", r.canonical, d.canonical), ("robots", r.meta.get("robots"), d.meta.get("robots")),
                         ("h1", r.h1[0] if r.h1 else None, d.h1[0] if d.h1 else None)]:
        field[f"{name}_raw"] = rv is not None and norm(rv) != ""
        field[f"{name}_rendered"] = dv is not None and norm(dv) != ""
        field[f"{name}_equal"] = norm(rv) == norm(dv)
    ri, di = internal(r.links, url), internal(d.links, url)
    return dict(
        words_rendered=total, words_raw=sum(rw.values()),
        pct_rendered_words_in_raw=round(100 * overlap / total, 1) if total else None,
        links_raw=len(ri), links_rendered=len(di),
        no_href_clickables_rendered=d.no_href_links,
        query_urls_rendered=len({u for u in di if "?" in u}),
        **field,
    )


def render(page, url, host, log):
    ts = now()
    try:
        resp = page.goto(url, wait_until="networkidle", timeout=RENDER_TIMEOUT_MS)
        status = resp.status if resp else None
        note = ""
    except Exception as e:  # network idle never reached: keep whatever rendered
        status, note = None, f"timeout:{type(e).__name__}"
    html = page.content()
    log.append(dict(host=host, url=url, ts=ts, kind="rendered", status=status, note=note, bytes=len(html)))
    if status in (401, 403, 418, 429) or (CHALLENGE.search(html[:20000]) and len(html) < 50000):
        raise Blocked(f"rendered {status} {url}")
    f = CACHE / host / (hashlib.sha1(url.encode()).hexdigest() + ".rendered.html")
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(html)
    return html, note


def study_site(row, browser, log):
    host = row["host"]
    site = dict(host=host, vertical=row["vertical"], expected=row["expected_framework"], detected="", status="ok", note="")
    pages = []
    raw = Raw(host, log)
    try:
        st, res = raw.get(f"https://{host}/robots.txt", check_robots=False)
        rp = urllib.robotparser.RobotFileParser()
        rp.parse(res[1].splitlines() if st == 200 and res else [])
        raw.robots = rp
        st, res = raw.get(f"https://{host}/")
        if not res or st != 200:
            site["status"], site["note"] = ("robots_disallows" if st is None and log[-1]["status"] == "disallowed" else "no_homepage"), str(st)
            return site, pages
        home_url, home_html = res
        found = detect(home_html)
        site["detected"] = "+".join(found)
        if not found:
            site["status"] = "no_framework_marker"
            return site, pages
        # The expected framework is only a guess from the site list; measure the
        # framework actually detected and note when the guess was wrong.
        framework = row["expected_framework"] if row["expected_framework"] in found else found[0]
        if framework != row["expected_framework"]:
            site["note"] = f"expected {row['expected_framework']}, detected {framework}"
        listing, detail = pick_pages(home_url, internal(parse(home_html).links, home_url))
        targets = [("home", home_url, home_html)]
        for kind, u in (("listing", listing), ("detail", detail)):
            if not u:
                continue
            st, res = raw.get(u)
            if res and st == 200:
                targets.append((kind, res[0], res[1]))
        ctx = browser.new_context()
        page = ctx.new_page()
        try:
            for kind, u, raw_html in targets:
                time.sleep(MIN_INTERVAL)
                rendered, note = render(page, u, host, log)
                pages.append(dict(host=host, framework=framework, vertical=row["vertical"],
                                  page_type=kind, url=u, render_note=note, **compare(raw_html, rendered, u)))
        finally:
            ctx.close()
    except Blocked as e:
        site["status"], site["note"] = "blocked", str(e)
        pages = []
    site["pages"] = len(pages)
    return site, pages


def write_csv(path, rows):
    if not rows:
        path.write_text("")
        return
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sites", default=str(HERE / "sites.csv"))
    ap.add_argument("--only", nargs="*")
    args = ap.parse_args()
    rows = list(csv.DictReader(open(args.sites)))
    if args.only:
        rows = [r for r in rows if r["host"] in args.only]
    for d in (CACHE, DATA, OUT):
        d.mkdir(exist_ok=True)

    started, log, sites, pages = now(), [], [], []
    with sync_playwright() as pw:
        # STUDY_BROWSER_CHANNEL=chrome uses an installed Google Chrome instead of
        # Playwright's downloaded Chromium (e.g. inside the mcp-browsers container).
        channel = os.environ.get("STUDY_BROWSER_CHANNEL") or None
        browser = pw.chromium.launch(channel=channel, args=["--no-sandbox"] if channel else [])
        ua = browser.new_context().new_page().evaluate("navigator.userAgent")
        for r in rows:
            site, ps = study_site(r, browser, log)
            sites.append(site)
            pages += ps
            print(f'{site["host"]:28} {site["status"]:20} expected={site["expected"]:9} detected={site["detected"]:18} pages={site.get("pages", 0)} {site["note"]}', flush=True)
        browser.close()

    # Page URLs are cached locally only; the published per-page file keeps the path, not the full URL.
    published = [{**p, "url": urlsplit(p["url"]).path} for p in pages]
    write_csv(OUT / "results.csv", sites)
    write_csv(OUT / "results-pages.csv", published)
    (DATA / "requests.jsonl").write_text("".join(json.dumps(x) + "\n" for x in log))
    (OUT / "run.json").write_text(json.dumps(dict(started=started, finished=now(), raw_user_agent=USER_AGENT,
                                                  render_user_agent=ua, sites=len(sites), pages=len(pages),
                                                  requests=len(log)), indent=1))
    print(f"\n{len(sites)} sites, {len(pages)} pages compared, {len(log)} page-level requests -> {OUT}")


if __name__ == "__main__":
    main()
