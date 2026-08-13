# Catalog and Decision Scoring Specification

## Purpose

`llm-cluster rank` remains a **shopping/research shortlist**, not a simulated benchmark.

The autonomous decision layer goes further by producing a ranked **Buy / Watch / Ignore / Experimental** report from real market evidence. Neither score may manufacture throughput from hardware specifications.

## Catalog shortlist score

The catalog shortlist may use:

- current acquisition price;
- included/fixed memory or discounted configurable memory potential;
- published power hints, clearly distinguished from complete-node measurements;
- software maturity;
- lifecycle/availability;
- setup/ownership risk.

It must not use TOPS, TFLOPS or invented tokens/sec.

## Decision-quality deal score

The daily deal score is 0-100 and uses:

- **35% price-history position** — current observed price relative to the product's own sourced history;
- **25% model-capacity fit** — transparent Q4 memory-fit presets only;
- **20% evidence confidence** — SKU/seller/market, memory evidence, software maturity and risk;
- **10% opportunity freshness** — whether the current listing remains fresh enough to act on;
- **10% price stability** — volatility penalty so noisy/transient prices do not dominate.

A product without a current priced opportunity is capped below the `Buy` range.

## Model-capacity fit

Default presets are 7B, 14B, 32B and 70B at nominal 4-bit weights with 40% planning headroom.

This is a capacity screen only. It does not predict:

- tokens/sec;
- runtime compatibility;
- context/KV-cache limits;
- prompt/decode behavior;
- complete-node efficiency.

For discrete GPUs, fixed VRAM is valid capacity evidence. For configurable systems, board-verified memory maximum receives less confidence than included/fixed RAM/VRAM.

## Memory confidence

Memory contributes according to evidence quality:

1. included/fixed RAM or VRAM — strongest;
2. verified board maximum — useful but requires additional purchase;
3. CPU theoretical maximum — weak and heavily discounted;
4. unknown — little/no capacity credit.

This prevents a barebone with a CPU that theoretically supports 256GB from appearing to include 256GB.

## Price-history position

Price observations must be matched to a catalog product with sufficient configuration confidence.

The current decision price is chosen from active latest listing observations and converted to CAD using the current sourced FX snapshot. Historical normalized CAD comparisons use the same current FX snapshot so the price-position signal reflects seller-price movement rather than pretending historical FX is known when it is not.

### All-time low

A new all-time low is detected in the seller's native currency. This avoids generating a fake seller-price record solely from exchange-rate movement.

### Trend

Recent trend compares median price in the earlier half of the recent observation window with the median in the later half.

### Volatility

Volatility is recent population standard deviation divided by mean. High volatility reduces the stability component of the deal score.

## Evidence confidence

Decision confidence combines:

- exact-SKU/configuration confidence;
- seller/source confidence;
- memory evidence quality;
- software maturity;
- project risk level.

Confidence does not mean speed.

## Opportunity freshness

Opportunity expiry is an internal freshness TTL unless the seller supplies a parseable listing end time. It is not a prediction that a product will definitely sell or disappear.

Expired/stale opportunities cannot receive `Buy`.

## Recommendation classes

### Buy

Requires a strong score, current price, non-expired opportunity, adequate confidence, usable model-fit evidence and favorable observed price position.

### Watch

Promising but price, evidence or freshness is not yet strong enough for action.

### Experimental

Research/high-risk hardware is isolated from ordinary purchasing recommendations even when it scores well on raw price/capacity.

### Ignore

Current evidence does not justify attention. This can change automatically when the market changes.

## Alert priority

Change alerts receive a second priority score using:

- alert severity/type;
- magnitude;
- current Buy/Watch status;
- market confidence;
- opportunity urgency.

Priority bands are P1/P2/P3/P4, with P1 highest.

All-time lows join the same stream as price drops, stock returns, landed-cost changes, new products and compatible benchmark changes.

## GPU treatment

Discrete GPUs are evaluated using:

- live price history;
- fixed VRAM/model fit;
- exact board/listing confidence;
- software maturity;
- used-market risk where applicable;
- opportunity freshness.

GPU TGP/TBP is board-power/deployment friction. It is **not** complete-node power and does not become tokens/joule without a complete-node measurement.

## Performance evidence remains separate

When vendor/community/local performance exists, display it alongside source type and confidence. Do not multiply a weak benchmark into the deal score.

Optional benchmark comparisons may use genuinely compatible measured tokens/sec and complete-node energy, but those measurements remain evidence records rather than prerequisites for catalog inclusion or daily recommendations.
