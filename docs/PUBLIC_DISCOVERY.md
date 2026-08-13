# Credential-free public discovery

LowPowerLLMCluster can discover hardware continuously without API credentials by following public web surfaces and then parsing schema.org `Product` / `Offer` data from candidate product pages.

## Built-in public source types

### `html_index`

Use a public category, marketplace, search, or index page as a seed. The adapter extracts normal HTTP(S) links, filters them with `include_patterns` / `exclude_patterns`, and parses matching product pages.

Good fits:

- retailer GPU / desktop / laptop categories;
- manufacturer marketplaces;
- public clearance / refurbished indexes;
- product-directory pages.

### `sitemap`

Use an XML `urlset` or `sitemapindex`. Sitemap indexes are followed recursively with a strict `max_index_pages` bound. Product URLs are filtered before they are fetched.

### `feed`

Use an RSS or Atom feed whose entries link to product or announcement pages. The linked pages are filtered and then parsed as product pages when they expose schema.org product metadata.

### `jsonld`

Use known public product URLs directly. This remains the highest-confidence no-auth path for manufacturer product pages.

## Safety and crawl boundaries

Public discovery is intentionally not a general-purpose spider. It does not log in, bypass access controls, call private APIs, or attempt anti-bot evasion.

Every public source supports bounded controls:

- `same_host` — keep candidates on seed hosts by default;
- `include_patterns` — explicitly define product URL shapes;
- `exclude_patterns` — reject carts, login pages, support pages, comparison tools, etc.;
- `max_index_pages` — cap category/sitemap/feed expansion;
- `max_candidate_pages` — cap product-page fetches per source per cycle;
- `subworkers` — bound product-page concurrency;
- shared HTTP retry/backoff, adaptive concurrency, cache, and circuit-breaker behavior.

Continuously running installations should keep these caps conservative and follow each site's published terms and robots policy.

## Credential-free sources verified 2026-08-13

### Memory Express

Public category pages expose product links, IDs, current prices, availability text, and ordinary public product pages.

Configured categories:

- `https://www.memoryexpress.com/Category/VideoCards`
- `https://www.memoryexpress.com/Category/DesktopComputers`
- `https://www.memoryexpress.com/Category/Processors`

Product URL shape:

- `https://www.memoryexpress.com/Products/MX...`

The default example caps this source at 120 candidate pages per cycle.

### Canada Computers

Public category and sitemap pages expose GPU, desktop/mini-PC and other hardware listings with prices and ordinary public product pages.

Configured categories:

- `https://www.canadacomputers.com/en/915/desktop-graphics-cards`
- `https://www.canadacomputers.com/en/931/desktop-computers`

The default example caps this source at 100 candidate pages per cycle.

### Manufacturer product pages

The example config also uses public schema.org pages from Minisforum, Raspberry Pi, Framework and Turing Pi. Manufacturer pages should generally carry higher source trust than retailer listings because they are stronger identity/specification evidence, even when they do not contain a useful street price.

### Framework Marketplace

`https://frame.work/marketplace/` is a useful public manufacturer marketplace for discovering mainboards, desktops, refurbished components and other modular hardware. It is a good candidate for an `html_index` source with a narrow `/products/` URL pattern and a conservative per-cycle cap.

## Example source

```json
{
  "name": "public-retailer",
  "type": "html_index",
  "source_trust": 0.8,
  "seeds": ["https://shop.example/hardware"],
  "include_patterns": ["^https://shop\\.example/products/[A-Za-z0-9-]+$"],
  "exclude_patterns": ["/login", "/cart", "/compare"],
  "same_host": true,
  "max_index_pages": 2,
  "max_candidate_pages": 100,
  "subworkers": 2,
  "batch_size": 32
}
```

## What gets saved

Discovered public products flow through the same runtime as authenticated/API sources:

`public index -> candidate URL -> JSON-LD Product/Offer -> ProductObservation -> normalize -> catalog-history.sqlite3 -> listing_state -> live /discoveries dashboard`

They appear immediately in the live/staging dashboard. They are not silently promoted into the canonical catalog; the normal identity/evidence rules still apply.

## Next public-source targets

Useful additions include:

- additional Canadian and US retailer category pages with stable public product URLs;
- manufacturer storefront/marketplace category pages;
- vendor product sitemaps;
- refurbished/open-box category pages;
- public RSS/Atom release feeds linked to product pages;
- community-maintained hardware directories where provenance can be preserved.

Prefer direct source pages over scraping search-engine result pages. Direct sources are more stable, easier to rate-limit, and retain clearer provenance.
