# ivanlabs-research

Small, reproducible studies and tools behind the Advisory Notes on [ivanlabs.com](https://ivanlabs.com/). Each folder holds its code, its methodology, and only aggregate or structural results. Raw responses are cached locally and are never committed.

| Folder | What it is | Used in |
|---|---|---|
| `sitemap-study/` | Study A: how large public sites structure their XML sitemaps | [SEO Architecture at Scale](https://ivanlabs.com/blog/seo-architecture-multi-million-page-sites/) |
| `render-gap-study/` | Study B: raw vs rendered HTML on JavaScript-framework sites | [Technical SEO at Scale](https://ivanlabs.com/blog/technical-seo-at-scale/) |
| `gsc-diagnostics/` | Tool C: Search Console diagnostics script | [AI SEO Diagnostics](https://ivanlabs.com/blog/ai-driven-technical-seo-diagnostics/) |
| `redirect-validator/` | Tool D: redirect-map validator | [Platform Migration Checklist](https://ivanlabs.com/blog/platform-migration-checklist/) |
| `seo-contracts-ci/` | Tool E: SEO contracts check for CI | [Technical SEO for Engineering Teams](https://ivanlabs.com/blog/technical-seo-for-engineering-teams/) |

## Research etiquette

The studies fetch only `robots.txt`, sitemap files and, where a study needs it, at most three HTML pages per site. Requests are serial, at most one per second per host, with a 20-second timeout and at most 15 requests per site. Every request sends an honest User-Agent, `IvanLabsResearch/1.0 (+https://ivanlabs.com/contact/)`. On a 401, 403, 429 or a bot challenge, the study stops for that host and records it as `blocked`. Published results are structural facts and aggregates, never page content.

## Running

Study A uses only the Python 3 standard library:

```bash
cd sitemap-study
python3 study.py      # fetches; writes output/ (and data/, cache/ locally)
python3 analyze.py    # aggregates output/ into stats.json and the SVG charts
```

Later folders list their own dependencies.
