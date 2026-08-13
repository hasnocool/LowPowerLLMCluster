# Credential-free public discovery

LowPowerLLMCluster can discover hardware continuously without API credentials by following public web surfaces and then parsing schema.org `Product` / `Offer` data from candidate product pages.

## Built-in public source types

### `html_index`

Use a public category, marketplace, search, or index page as a seed. The adapter extracts normal HTTP(S) links, filters them with `include_patterns` / `exclude_patterns`, and parses matching product pages.

Good fits include retailer GPU/CPU/motherboard/desktop categories, manufacturer storefronts, public clearance/refurbished indexes, and product-directory pages.

### `sitemap`

Use an XML `urlset` or `sitemapindex`. Sitemap indexes are followed recursively with a strict `max_index_pages` bound. Product URLs are filtered before they are fetched.

### `feed`

Use an RSS or Atom feed whose entries link to product or announcement pages. Linked pages are filtered and parsed when they expose schema.org product metadata.

### `jsonld`

Use known public product URLs directly. This remains the highest-confidence no-auth path for manufacturer product pages.

## Safety and crawl boundaries

Public discovery is intentionally not a general-purpose spider. It does not log in, bypass access controls, call private APIs, or attempt anti-bot evasion.

Every public source supports bounded controls:

- `same_host` keeps candidates on seed hosts by default;
- `include_patterns` explicitly define product URL shapes;
- `exclude_patterns` reject carts, login pages, support pages and comparison tools;
- `max_index_pages` caps category/sitemap/feed expansion;
- `max_candidate_pages` caps product-page fetches per source per cycle;
- `subworkers` bounds product-page concurrency;
- shared HTTP retry/backoff, adaptive concurrency, cache, and circuit-breaker behavior applies to every source.

Continuously running installations should keep these caps conservative and follow each site's published terms and robots policy.

## Active credential-free source pool

The default example now contains ten bounded public-web source groups plus a direct manufacturer JSON-LD group. All public-web groups use ordinary unauthenticated HTTPS pages.

| Source | Coverage | Mode | Per-cycle candidate cap |
| --- | --- | --- | ---: |
| Memory Express | GPUs, desktops, CPUs | `html_index` | 120 |
| Canada Computers | GPUs, desktops, motherboards | `html_index` | 140 |
| Best Buy Canada | GPUs, CPUs, motherboards, desktops | `html_index` | 160 |
| Newegg Canada | GPUs, barebones, mini PCs | `html_index` | 150 |
| HP Canada | desktops, mini PCs, workstations | `html_index` | 80 |
| Dell Canada | desktops, workstations, desktop deals | `html_index` | 90 |
| Lenovo Canada | ThinkCentre desktops, technical workstations | `html_index` | 80 |
| Framework Marketplace | mainboards and modular system parts | `html_index` | 70 |
| GMKtec | AMD/Intel/AI mini PCs | `html_index` | 60 |
| Minisforum | mini PCs, AI systems, workstations, NAS/mainboard products | `html_index` | 70 |
| Direct manufacturer pages | Minisforum, Raspberry Pi, Framework, Turing Pi | `jsonld` | fixed URL set |

This gives the continuous scanner broad coverage across complete systems and components without requiring API credentials.

### Canadian retailer seeds

Memory Express:

- `https://www.memoryexpress.com/Category/VideoCards`
- `https://www.memoryexpress.com/Category/DesktopComputers`
- `https://www.memoryexpress.com/Category/Processors`

Canada Computers:

- `https://www.canadacomputers.com/en/915/desktop-graphics-cards`
- `https://www.canadacomputers.com/en/931/desktop-computers`
- `https://www.canadacomputers.com/en/53/motherboards`

Best Buy Canada:

- `https://www.bestbuy.ca/en-ca/category/graphics-cards/20397`
- `https://www.bestbuy.ca/en-ca/category/cpu-computer-processors/29080`
- `https://www.bestbuy.ca/en-ca/category/motherboards/29079`
- `https://www.bestbuy.ca/en-ca/category/desktop-computers/20213`

Newegg Canada:

- `https://www.newegg.ca/p/pl?N=40000048&Submit=ENE`
- `https://www.newegg.ca/p/pl?d=barebones+desktop`
- `https://www.newegg.ca/p/pl?d=mini+pc`

### OEM and compact-system seeds

- HP Canada: `https://www.hp.com/ca-en/shop/listings/desktops`
- Dell Canada: desktop/workstation catalog plus desktop deals
- Lenovo Canada: ThinkCentre and technical-workstation public indexes
- Framework: mainboards and Framework-branded parts
- GMKtec: mini-PC and all-product collections
- Minisforum: all-product and AI-focused collections

Manufacturer/OEM sources carry higher trust than general retailer listings when they provide exact identity/specification evidence.

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

## Growing the pool further

Good next candidates are additional Canadian/US hardware retailers with stable public product URLs, OEM outlet/refurbished pages, vendor product sitemaps, public RSS/Atom release feeds, and community-maintained hardware directories where provenance can be preserved.

Prefer direct source pages over scraping search-engine result pages. Direct sources are more stable, easier to rate-limit, and retain clearer provenance. Keep new sources bounded and add a URL-pattern regression fixture before enabling them in the continuous default.
