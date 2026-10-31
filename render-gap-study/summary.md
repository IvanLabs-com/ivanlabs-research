# Study B: raw vs rendered HTML on JavaScript-framework sites

Run on 2026-10-31 (02:16–02:34 UTC), 141 page-level requests. Code: `study.py` (collection) and `analyze.py` (aggregation). Per-site rows are in `output/results.csv` and per-page rows in `output/results-pages.csv`; the aggregates below come from `output/stats.json`.

## Sample and access

The sample was 30 public sites expected to run on Next.js, Nuxt, Angular, SvelteKit, Remix or Gatsby (`sites.csv`, with a reason for each pick). The framework was confirmed from markers in the raw HTML (for example `__NEXT_DATA__`, `/_nuxt/`, `ng-version`, `data-sveltekit`, `__remixContext`, `___gatsby`). When the expected framework was wrong but another one was detected, the detected framework was used.

| Outcome | Sites |
|---|---|
| Measured | **15** |
| Blocked (403, 429 or a bot challenge, on the raw or the rendered fetch) | 9 |
| No framework marker in the raw HTML | 6 |

**So N = 15 sites and 41 pages.** By detected framework, the 15 sites are: Next.js 6, Nuxt 3, SvelteKit 2, Remix 2, Angular 1 and Gatsby 1. Two pages were excluded: one render produced no body text, and one listing page resolved to the same path as its homepage. Angular and Gatsby rest on one site each, so the study reports no per-framework comparisons.

## Findings

1. **Most server output already contains most of the page.** The median page had 95.4% of its rendered words in the raw HTML. 27 of 41 pages had at least 90%, 12 had 50–89%, and 2 had under 50%. One documentation listing page was an empty shell before JavaScript ran: 0.2% of its words were in the raw HTML.
2. **The SEO head is server-rendered almost everywhere.** The `<title>` was in the raw HTML on 41 of 41 pages, the canonical on 35, the meta description on 36 and an H1 on 37. JavaScript changed the title on 2 pages, the H1 on 2, the description on 1 and the canonical on 1. The robots meta differed on 1 page.
3. **H1s can disappear as well as appear.** One page gained its H1 only after rendering, and 2 pages had an H1 in the raw HTML that was gone after rendering.
4. **Rendering adds links.** 22 of 41 pages had more internal links after rendering. On 7 pages, rendering added 10% or more.
5. **Query-string links are common.** 19 of 41 pages, on 9 of 15 sites, linked to internal URLs with query parameters after rendering. One page had 88 of them. Each one is a URL a crawler can follow, so this is the measurable seed of crawl waste.
6. **JS-only clickables exist but are rare.** 10 pages had at least one `<a>` without an `href`, or an element with `role="link"` and no `href`. Google's crawler generally can't follow those.
7. **Network idle isn't guaranteed.** 5 of 41 renders hit the 15-second network-idle cap. The DOM was measured as it stood at that point.

## Methodology and limitations

- **Pages:** the homepage, plus one listing page and one detail page picked from the homepage's internal links by a URL-pattern rule (`pick_pages` in `study.py`). Pages were only fetched where robots.txt allowed it.
- **Raw:** a plain GET with `IvanLabsResearch/1.0 (+https://ivanlabs.com/contact/)`. **Rendered:** Google Chrome 156 in headless mode, driven by Playwright with its default headless user agent. Each page got a fresh browser context, waited for network idle and was capped at 15 seconds.
- **Words:** visible body text, tokenised to words of 2+ characters. The overlap is the multiset of rendered words also present in the raw HTML. The `<title>`, scripts, styles, `noscript` and `svg` were excluded.
- **Etiquette:** requests were serial, at least 1.1 seconds apart per host, with a 20-second raw timeout. The study stopped at the first 401, 403, 418 or 429, non-standard 2xx or challenge page. Subresources loaded during a render (JS, CSS, images, APIs) are not counted in the 141 page-level requests.
- **Location:** the fetches came from an IP in Cyprus/Greece, and several sites served localised versions (for example `/gr/`, `/el-gr`). Other regions may get different markup.
- **Environment:** the study ran inside a throwaway Incus container (Debian 12), which was deleted afterwards.
- **Not measured:** what Googlebot itself renders or indexes, how long rendering is deferred, whether the query-string URLs are canonicalised or blocked in robots.txt, and anything behind a block. The sites were picked by hand and aren't a random sample.
