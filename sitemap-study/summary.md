# Study A: how large public sites structure their XML sitemaps

Run on 2026-10-30 (14:56–15:03 UTC), seed 20261030, 260 requests in total. Code: `study.py` (collection) and `analyze.py` (aggregation). Per-site rows are in `output/results.csv` and per-sitemap rows in `output/results-sitemaps.csv`; the aggregates below come from `output/stats.json`.

## Sample and access

The sample was 40 large public sites, 5 in each of 8 verticals: marketplaces, retail, travel, real estate and classifieds, jobs, news, reference and UGC, and local reviews. The list and the reason for each pick are in `sites.csv`. Each site got one identified bot (`IvanLabsResearch/1.0 (+https://ivanlabs.com/contact/)`) that respected robots.txt and made at most 15 requests.

| Outcome | Sites |
|---|---|
| Sitemaps read | **17** |
| No `Sitemap:` line in robots.txt, and nothing at `/sitemap.xml` or `/sitemap_index.xml` | 4 |
| robots.txt disallows every user agent it doesn't list by name | 5 |
| Blocked (403, 418, 429, a non-standard 2xx status, or a bot wall) | 13 |
| Timed out after robots.txt answered | 1 |

**So N = 17.** Every structural finding below is about those 17 sites and their 154 sampled child sitemaps. One site was blocked part-way through and is excluded, even though two of its sitemaps had been read. The sample leans towards marketplaces, retail, travel, real estate and news. Jobs and reference sites are almost absent, because they disallowed or blocked the bot.

## Findings

1. **Every site that served a sitemap declared it in robots.txt (17 of 17).** None relied on the default `/sitemap.xml` path alone. The number of `Sitemap:` lines varies widely: the median is 7 and the maximum is 434.
2. **Almost every site uses a sitemap index, and only one level deep.** 16 of 17 sites use a sitemap index; the other declares two urlsets directly. No sampled child was itself an index. The indexes we fetched list a median of about 160 child sitemaps (159.5) (max 2,316). The method only reads up to three declared files, so these counts are a floor.
3. **Files are filled close to the 50,000-URL limit, but never past it.** The median child holds 7,674 URLs. 31 of 154 files hold at least 45,000, and 21 hold exactly 50,000. None exceeded the protocol's 50,000-URL or 50 MB (uncompressed) limits; the largest was 49.96 MB. Shards also tend to use fixed sizes per site, such as 10,000, 20,000, 45,000 or 50,000.
4. **Segmentation is almost always by page type.** Classified by hand from filenames (`scheme_manual.csv`): 15 of 17 sites segment by content or page type, 10 add numeric shards, 3 add locale, 2 use dates (news), and 1 uses geography. Two sites' schemes are ambiguous from the filenames alone.
5. **`lastmod` is common but not universal, and sometimes it's only a build stamp.** 12 of 17 sites put `lastmod` on most URLs. 10 of the 16 index sites put it on index entries, and at 4 of those 10, every child had the same `lastmod`, which looks like a regeneration time rather than a content change. Google says it uses `lastmod` only if it's "consistently and verifiably" accurate.
6. **Parameter, cross-host and legacy URLs do appear.** 3 of 17 sites list query-string URLs, such as keyword or SKU parameters. 2 list URLs on another host, and 1 lists `http://` URLs from a former domain.
7. **Extensions are used where they matter.** Image extensions appear at 5 sites, news extensions at 3 (all of them news publishers), video at 2, and hreflang `xhtml:link` at only 2. Two of the three sites that segment by locale carry no hreflang in the sampled files. 1 site uses a non-standard sitemap namespace.
8. **Two of 154 sampled child sitemaps were empty** (0 URLs).

## Methodology and limitations

- **Discovery:** the study read robots.txt `Sitemap:` lines. Only if there were none did it try `/sitemap.xml` and then `/sitemap_index.xml`. It fetched up to 3 declared top-level files per site, then a seeded random sample of up to 10 child sitemaps from the indexes it found. It read gzip in memory, and matched XML elements by local name so that files with non-standard namespaces still parse.
- **Limits:** 50,000 URLs and 50 MB (52,428,800 bytes) uncompressed per file, from the sitemaps.org protocol (https://www.sitemaps.org/protocol.html), checked 2026-10-30. Google's sitemap documentation states the same limits.
- **Etiquette:** requests were serial, at least 1.1 seconds apart, with a 20-second timeout and at most 15 requests per site. robots.txt was checked before every non-robots fetch. The study stopped at the first 401, 403, 418, 429, non-standard 2xx or challenge page.
- **Not measured:** whether the listed URLs return 200, are canonical, or are indexed. How search engines actually use these sitemaps. Anything behind a block. Child sitemaps outside the sample. The sample of 40 sites was chosen by hand and isn't random, so the results describe these sites, not "the web".
- **Classification:** segmentation schemes were first classified by a filename rule in `study.py`, then reviewed by hand in `scheme_manual.csv`. The filename rule misses non-English or abbreviated type names, which is why the manual review exists.
- **Robots.txt quirk:** the "disallows unlisted bots" group is a real result for an identified research bot. Search engines named in those files are allowed.
