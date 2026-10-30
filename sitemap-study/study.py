#!/usr/bin/env python3
"""Study A: how large public sites structure their XML sitemaps.

Reads sites.csv, fetches each site's robots.txt and a bounded sample of its
sitemap files, and writes per-site and per-sitemap structural facts.

Etiquette (see ../README.md): serial requests, >=1 s between requests,
20 s timeout, at most MAX_REQUESTS per site, an honest User-Agent, robots.txt
checked before every non-robots fetch, and a stop on 401/403/429 or a bot
challenge. Raw responses go to cache/ and the request log to data/; both are
git-ignored. Only structural facts and aggregates are written to output/.

Usage:
    python3 study.py [--sites sites.csv] [--seed 20261030] [--only host ...]
"""
import argparse
import csv
import gzip
import hashlib
import json
import random
import re
import time
import urllib.error
import urllib.request
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

USER_AGENT = "IvanLabsResearch/1.0 (+https://ivanlabs.com/contact/)"
TIMEOUT = 20
MIN_INTERVAL = 1.1          # seconds between requests to the same host
MAX_REQUESTS = 15           # per site, robots.txt included
MAX_DECLARED = 3            # top-level sitemaps fetched from robots.txt
MAX_CHILDREN = 10           # child sitemaps sampled per site
MAX_BYTES = 60 * 1024 * 1024
URL_LIMIT = 50_000          # sitemaps.org protocol limits, verified 2026-10-30
SIZE_LIMIT = 50 * 1024 * 1024

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
DATA = HERE / "data"
OUT = HERE / "output"

SM_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
EXT_NS = {
    "image": "http://www.google.com/schemas/sitemap-image/1.1",
    "video": "http://www.google.com/schemas/sitemap-video/1.1",
    "news": "http://www.google.com/schemas/sitemap-news/0.9",
    "xhtml": "http://www.w3.org/1999/xhtml",
}
CHALLENGE = re.compile(rb"captcha|cf-chl|challenge-platform|px-captcha|access denied|are you a robot|datadome", re.I)


class Blocked(Exception):
    pass


class Budget(Exception):
    pass


class Fetcher:
    """Serial, rate-limited, budgeted fetcher for one site."""

    def __init__(self, host, log):
        self.host = host
        self.log = log
        self.count = 0
        self.last = 0.0
        self.robots = None
        self.errors = 0
        self.disallowed = 0

    def get(self, url, check_robots=True):
        if self.count >= MAX_REQUESTS:
            raise Budget(url)
        if check_robots and self.robots is not None and not self.robots.can_fetch(USER_AGENT, url):
            self.disallowed += 1
            self.log.append(dict(host=self.host, url=url, ts=now(), status="disallowed"))
            return None, None
        wait = self.last + MIN_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self.count += 1
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"})
        ts = now()
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                body = r.read(MAX_BYTES + 1)
                status, final, enc, ctype = r.status, r.geturl(), r.headers.get("Content-Encoding", ""), r.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            status, final, body, enc, ctype = e.code, url, b"", "", ""
        except Exception as e:  # timeouts, DNS, TLS
            self.last = time.monotonic()
            self.errors += 1
            self.log.append(dict(host=self.host, url=url, ts=ts, status=f"error:{type(e).__name__}"))
            return None, None
        self.last = time.monotonic()
        self.log.append(dict(host=self.host, url=url, ts=ts, status=status, final=final, bytes=len(body)))
        if status in (401, 403, 418, 429) or (status < 300 and status != 200):
            raise Blocked(f"{status} {url}")  # 418 and non-standard 2xx (e.g. 247) are bot walls
        while body[:2] == b"\x1f\x8b":  # .xml.gz, sometimes also sent with Content-Encoding: gzip
            body = gzip.decompress(body)
        if status == 200 and "html" in ctype and not url.endswith("robots.txt") and CHALLENGE.search(body[:20000]):
            raise Blocked(f"challenge {url}")
        cache_file = CACHE / self.host / hashlib.sha1(url.encode()).hexdigest()
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_bytes(body)
        return status, body


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_xml(body):
    """Return ('index'|'urlset'|None, root element)."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return None, None
    tag = root.tag.split("}")[-1]
    return (tag if tag in ("sitemapindex", "urlset") else None), root


def local(el):
    return el.tag.rsplit("}", 1)[-1]


def kids(el, name):
    """Children by local name, so non-standard namespaces still parse."""
    return [c for c in el if local(c) == name]


def text(el, name):
    found = kids(el, name)
    return (found[0].text or "").strip() if found else ""


def namespaces(root):
    return {el.tag[1:].split("}")[0] for el in root.iter() if el.tag.startswith("{")}


def index_entries(root):
    out = []
    for sm in kids(root, "sitemap"):
        loc = text(sm, "loc")
        if loc:
            out.append((loc, text(sm, "lastmod")))
    return out


def classify_name(url):
    """Signals in a child sitemap's filename/path."""
    name = urlsplit(url).path.lower() + "?" + urlsplit(url).query.lower()
    name = re.sub(r"sitemaps?|index|\.xml|\.gz", "", name)  # "sitemap" contains "item"; strip the boilerplate
    sig = set()
    if re.search(r"(19|20)\d{2}[-_/]?(0[1-9]|1[0-2])|(19|20)\d{2}(?!\d)", name):
        sig.add("date")
    if re.search(r"(^|[/_.-])([a-z]{2}[-_][a-z]{2}|[a-z]{2})([/_.-]|$)", name) and re.search(
            r"(^|[/_.-])(en|de|fr|es|it|nl|pt|pl|ja|zh|ko|ru|sv|da|fi|no|tr|ar|he|cs|hu|ro|el|uk|id|th|vi|ms)([-_][a-z]{2})?([/_.-]|$)", name):
        sig.add("locale")
    if re.search(r"(product|item|listing|categor|brand|store|shop|article|news|video|image|job|compan|review|"
                 r"location|city|place|hotel|propert|home|rental|search|tag|topic|author|page|question|user|"
                 r"profile|title|name|event|deal|destination|route|flight|static|landing|guide|biz)", name):
        sig.add("content_type")
    stripped = re.sub(r"(19|20)\d{2}[-_/]?\d{0,2}[-_/]?\d{0,2}", "", name)
    if re.search(r"[-_./](\d{1,6})(\.xml|\.gz|$|\?|[-_.])", stripped) or re.search(r"(page|p|part|shard)=?\d+", stripped):
        sig.add("numeric_shard")
    return sig


def scheme(child_urls):
    if not child_urls:
        return "none", True
    counts = {}
    for u in child_urls:
        for s in classify_name(u):
            counts[s] = counts.get(s, 0) + 1
    n = len(child_urls)
    major = sorted(s for s, c in counts.items() if c / n >= 0.5)
    if not major:
        return "unclassified", True
    if len(major) == 1:
        return major[0], False
    return "mixed:" + "+".join(major), False


def child_stats(url, root, site_host, size):
    urls = kids(root, "url")
    n = len(urls)
    lastmod = q = nonhttps = otherhost = 0
    base = site_host.removeprefix("www.")
    ns = namespaces(root)
    for u in urls:
        loc = text(u, "loc")
        if kids(u, "lastmod"):
            lastmod += 1
        p = urlsplit(loc)
        q += bool(p.query)
        nonhttps += p.scheme != "https"
        otherhost += p.hostname is not None and p.hostname.removeprefix("www.") != base
    pct = (lambda k: round(100 * k / n, 1) if n else None)
    return dict(
        sitemap=url, url_count=n, pct_lastmod=pct(lastmod), pct_query=pct(q), pct_non_https=pct(nonhttps),
        pct_other_host=pct(otherhost),
        hreflang=EXT_NS["xhtml"] in ns,
        image_ext=EXT_NS["image"] in ns,
        video_ext=EXT_NS["video"] in ns,
        news_ext=EXT_NS["news"] in ns,
        nonstandard_ns=SM_NS not in ns,
        bytes_uncompressed=size, over_url_limit=n > URL_LIMIT, over_size_limit=size > SIZE_LIMIT,
    )


def study_site(host, rng, log):
    f = Fetcher(host, log)
    site = dict(host=host, status="ok", note="", declared_in_robots=False, n_declared=0, index_levels=0,
                n_child_sitemaps=0, scheme="", scheme_ambiguous="", pct_index_lastmod="", identical_child_lastmod="",
                n_sampled=0, requests=0, nonstandard_ns=False)
    children = []
    try:
        st, body = f.get(f"https://{host}/robots.txt", check_robots=False)
        rp = urllib.robotparser.RobotFileParser()
        rp.parse((body or b"").decode("utf-8", "replace").splitlines() if st == 200 else [])
        f.robots = rp
        declared = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", (body or b"").decode("utf-8", "replace")) if st == 200 else []
        site["declared_in_robots"] = bool(declared)
        site["n_declared"] = len(declared)
        tops = declared[:MAX_DECLARED] or [f"https://{host}/sitemap.xml", f"https://{host}/sitemap_index.xml"]

        index_locs, index_lastmods, urlsets = [], [], []
        for url in tops:
            st, body = f.get(url)
            if st != 200 or not body:
                continue
            kind, root = parse_xml(body)
            if kind and SM_NS not in namespaces(root):
                site["nonstandard_ns"] = True
            if kind == "sitemapindex":
                site["index_levels"] = max(site["index_levels"], 1)
                ents = index_entries(root)
                index_locs += [e[0] for e in ents]
                index_lastmods += [e[1] for e in ents]
            elif kind == "urlset":
                urlsets.append((url, root, len(body)))
            if not declared and kind:
                break  # fallback found a sitemap; don't probe the second path

        site["n_child_sitemaps"] = len(index_locs)
        if index_lastmods:
            with_lm = [x for x in index_lastmods if x]
            site["pct_index_lastmod"] = round(100 * len(with_lm) / len(index_lastmods), 1)
            site["identical_child_lastmod"] = len(with_lm) > 1 and len(set(with_lm)) == 1
        sch, amb = scheme(index_locs or [u for u, _, _ in urlsets] or declared)
        site["scheme"], site["scheme_ambiguous"] = sch, amb

        for url, root, size in urlsets:
            children.append(child_stats(url, root, host, size))
        sample = rng.sample(index_locs, min(MAX_CHILDREN, len(index_locs))) if index_locs else []
        for url in sample:
            st, body = f.get(url)
            if st != 200 or not body:
                continue
            kind, root = parse_xml(body)
            if kind == "urlset":
                children.append(child_stats(url, root, host, len(body)))
            elif kind == "sitemapindex":
                site["index_levels"] = max(site["index_levels"], 2)
                nested = index_entries(root)
                if nested:
                    nurl = rng.choice(nested)[0]
                    st2, body2 = f.get(nurl)
                    k2, r2 = parse_xml(body2) if body2 else (None, None)
                    if k2 == "urlset":
                        children.append(child_stats(nurl, r2, host, len(body2)))
                    elif k2 == "sitemapindex":
                        site["index_levels"] = 3
        if f.errors and f.errors == f.count:
            site["status"], site["note"] = "network_error", "every request failed before a response"
        elif not index_locs and not urlsets and f.disallowed and f.count == 1:
            site["status"], site["note"] = "robots_disallows_ua", "robots.txt disallows unlisted user agents"
        elif not index_locs and not urlsets and f.errors == f.count - 1:
            site["status"], site["note"] = "timeout", "robots.txt answered; every sitemap request timed out"
        elif not index_locs and not urlsets:
            site["status"], site["note"] = "no_sitemap_found", "no sitemap at declared or fallback locations"
        elif urlsets and not index_locs:
            site["index_levels"] = 0
    except Blocked as e:
        site["status"], site["note"] = "blocked", str(e)
    except Budget as e:
        site["note"] = f"request budget reached before {e}"
    site["n_sampled"] = len(children)
    site["requests"] = f.count
    for c in children:
        c["host"] = host
    return site, children


def write_csv(path, rows, fields):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sites", default=str(HERE / "sites.csv"))
    ap.add_argument("--seed", type=int, default=20261030)
    ap.add_argument("--only", nargs="*", help="limit to these hosts (for testing)")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.sites)))
    if args.only:
        rows = [r for r in rows if r["host"] in args.only]
    for d in (CACHE, DATA, OUT):
        d.mkdir(exist_ok=True)

    started = now()
    rng = random.Random(args.seed)
    log, sites, children = [], [], []
    for r in rows:
        site, ch = study_site(r["host"], rng, log)
        site["vertical"] = r["vertical"]
        for c in ch:
            c["vertical"] = r["vertical"]
        sites.append(site)
        children += ch
        print(f'{site["host"]:28} {site["status"]:16} levels={site["index_levels"]} children={site["n_child_sitemaps"]:>5} '
              f'sampled={site["n_sampled"]:>2} reqs={site["requests"]:>2} scheme={site["scheme"]} {site["note"]}', flush=True)

    site_fields = ["vertical", "host", "status", "declared_in_robots", "n_declared", "index_levels", "n_child_sitemaps",
                   "scheme", "scheme_ambiguous", "pct_index_lastmod", "identical_child_lastmod", "nonstandard_ns", "n_sampled", "requests", "note"]
    child_fields = ["vertical", "host", "sitemap", "url_count", "pct_lastmod", "pct_query", "pct_non_https", "pct_other_host",
                    "hreflang", "image_ext", "video_ext", "news_ext", "bytes_uncompressed", "over_url_limit", "over_size_limit", "nonstandard_ns"]
    write_csv(OUT / "results.csv", sites, site_fields)
    write_csv(OUT / "results-sitemaps.csv", children, child_fields)
    (DATA / "requests.jsonl").write_text("".join(json.dumps(x) + "\n" for x in log))
    (OUT / "run.json").write_text(json.dumps(dict(started=started, finished=now(), seed=args.seed, user_agent=USER_AGENT,
                                                  sites=len(sites), requests=len(log)), indent=1))
    print(f"\n{len(sites)} sites, {len(children)} child sitemaps, {len(log)} requests -> {OUT}")


if __name__ == "__main__":
    main()
