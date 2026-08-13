# Decision Quality

The decision layer answers a different question from benchmarking:

> Given the evidence we have today, which products deserve action, patience, experimentation or no attention?

It produces a ranked `Buy / Watch / Ignore / Experimental` report from market evidence without manufacturing performance precision.

## Inputs

The decision engine uses:

- observed price history;
- exact-SKU/configuration confidence;
- seller/source confidence;
- conservative memory/model-fit screening;
- software maturity;
- project risk labels;
- listing freshness/availability state;
- sourced FX for CAD normalization;
- price trend and volatility;
- existing change-intelligence alerts.

It does **not** convert TOPS, TFLOPS, bandwidth, shader/core count or TDP into tokens/sec.

## Deal score

`deal_score` is a 0-100 decision-support score. It is not a benchmark score.

Current weighting:

| Component | Weight | Meaning |
|---|---:|---|
| price-history position | 35% | how favorable the current observed price is versus this product's history |
| model-capacity fit | 25% | which Q4 model-size presets fit the trustworthy memory capacity |
| evidence confidence | 20% | market/SKU/seller + memory + software + risk confidence |
| opportunity freshness | 10% | whether the live listing is still fresh enough to act on |
| price stability | 10% | volatility penalty so a transient noisy price does not dominate |

Missing live price caps the score below the `Buy` range.

## Model-fit presets

The default transparent capacity presets are:

- 7B Q4;
- 14B Q4;
- 32B Q4;
- 70B Q4.

Required memory is estimated as nominal model weights plus 40% planning headroom. This is only a capacity screen. Runtime overhead, KV cache, context length and backend behavior can require more memory.

For GPUs, the screen uses fixed VRAM. For system boards, it uses included/fixed memory or verified board maximum according to the evidence rules.

## Price history

Historical price comparisons use observations matched to the catalog product with a minimum configuration-confidence threshold.

The current candidate price is selected from active latest listing observations and converted to CAD with the current sourced FX snapshot.

### New all-time low

`new_all_time_low` is deliberately detected in the listing's native currency so a changing FX rate cannot manufacture a fake seller price record.

A new all-time low means the current matched listing price is lower than prior observed prices for the same catalog product/currency. Shipping, tax and FX-driven landed-cost changes are reported separately.

### Trend

Trend compares the median of the earlier half of the recent normalized observation window with the median of the later half.

Negative is falling; positive is rising.

### Volatility

Volatility is population standard deviation divided by mean price over the recent observation window. High volatility reduces the stability component of the deal score.

## Opportunity expiry

`opportunity.expires_at` is an internal decision-freshness deadline, not a prediction that a seller will remove an item.

Default freshness windows are source-class dependent:

- structured marketplace: 36 hours;
- authorized distributor: 96 hours;
- manufacturer: 168 hours;
- unknown source class: 72 hours.

When a parseable seller-provided end time exists, the earlier deadline wins.

An expired opportunity cannot receive `Buy`, but its history remains intact.

## Recommendation classes

### Buy

Requires a sufficiently strong score, a known current price, non-expired opportunity, usable model-fit evidence, adequate confidence and a favorable observed price position.

### Watch

Promising but not strong enough for immediate action. Typical reasons include missing current price, ordinary price position, incomplete confidence or an aging opportunity.

### Experimental

Research/high-risk platforms remain separate even when price appears excellent. This protects the catalog from recommending a difficult FPGA, unusual ASIC or risky decommissioned accelerator as though it were a plug-and-play GPU.

### Ignore

Current evidence does not justify attention. This is not permanent: a later price drop, better software support or stronger evidence can move the product into another class.

## Alert prioritization

Existing alerts receive an additional 0-100 priority score based on:

- severity;
- alert type;
- change magnitude when available;
- whether the associated product is currently `Buy` or `Watch`;
- market confidence;
- approaching opportunity expiry.

Priority bands:

- `P1`: 75+
- `P2`: 55-74.9
- `P3`: 35-54.9
- `P4`: below 35

New all-time lows are synthesized into the priority stream so they appear next to price drops, stock returns, new products and compatible benchmark changes.

## Generated outputs

Each autonomous refresh generates:

- `reports/current/daily-recommendations.json`
- `reports/current/daily-recommendations.md`

The Markdown report contains:

- prioritized alerts;
- ranked Buy candidates;
- ranked Watch candidates;
- ranked Experimental candidates;
- ranked Ignore candidates;
- current CAD price where available;
- model-fit ceiling;
- decision confidence;
- price trend;
- volatility;
- opportunity freshness;
- all-time-low marker.

The JSON form preserves the complete inputs and reasons for downstream dashboards or notifications.

## GPU treatment

Discrete GPUs use the same decision framework with two important guardrails:

1. fixed VRAM is valid model-fit capacity evidence;
2. GPU TGP/TBP is board power, not complete-node energy efficiency.

A 24GB GPU may rank highly because of VRAM and price history while still carrying substantial host/PSU/cooling friction. That friction should be surfaced rather than hidden behind a synthetic performance-per-watt number.
