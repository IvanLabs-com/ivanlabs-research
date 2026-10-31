#!/usr/bin/env python3
"""Sample N URLs per template from a list of URLs (e.g. extracted from sitemaps).

Large sites have millions of URLs but only dozens of templates. Auditing a
fixed sample per template finds template-level problems for a fraction of the
crawl. A URL's "template key" here is its path with variable-looking segments
collapsed: numbers, long slugs and IDs become placeholders.

Usage:
    python3 sample_by_template.py urls.txt --per-template 25 --seed 1 > sample.txt
"""
import argparse
import random
import re
from collections import defaultdict
from urllib.parse import urlsplit


def template_key(url):
    parts = []
    for seg in urlsplit(url).path.strip("/").split("/"):
        if not seg:
            continue
        if re.fullmatch(r"\d+", seg):
            parts.append("{n}")
        elif re.fullmatch(r"[0-9a-f]{8,}|[A-Z0-9]{8,}", seg, re.I) and re.search(r"\d", seg):
            parts.append("{id}")
        elif seg.count("-") >= 2 or len(seg) > 40:
            parts.append("{slug}")
        else:
            parts.append(seg.lower())
    return "/" + "/".join(parts) + ("?" if urlsplit(url).query else "")


def sample(urls, per_template, seed):
    groups = defaultdict(list)
    for u in urls:
        groups[template_key(u)].append(u)
    rng = random.Random(seed)
    return {k: rng.sample(v, min(per_template, len(v))) for k, v in sorted(groups.items())}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("urls", help="file with one URL per line")
    ap.add_argument("--per-template", type=int, default=25)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    urls = [l.strip() for l in open(args.urls) if l.strip()]
    for key, picked in sample(urls, args.per_template, args.seed).items():
        print(f"# {key}  ({len(picked)} sampled)")
        print("\n".join(picked))


if __name__ == "__main__":
    main()
