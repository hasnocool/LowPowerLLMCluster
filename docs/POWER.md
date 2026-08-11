# Power Strategy

The goal is not to make every CPU run at its maximum advertised package power. The goal is **useful tokens per watt**.

```text
    PERFORMANCE
        ▲
        │                         ● maximum boost
        │                    ●
        │                ●
        │            ●
        │        ●  efficiency sweet spot
        │     ●
        │  ●
        └────────────────────────────────────► POWER

           modest power limits often preserve
           much more performance than expected
```

## Node classes

| Class | Suggested platform | CPU configurable range | Intended role |
|---|---|---:|---|
| Efficiency worker | Ryzen 7 7735U | 15-30W | 3B-14B jobs, embeddings, classifiers, background tasks |
| Main worker | Ryzen 7 8845HS | 35-54W | coding/general models and latency-sensitive jobs |
| Expandable worker | Ryzen 7 8745HS + OCuLink | roughly HS-class | larger RAM/storage, optional accelerator path |
| Premium worker | Ryzen AI 9 HX 370 | 15-54W | heavy request or high performance/watt node |

The CPU ranges above describe AMD's processor configuration envelopes where available. Whole-system wall power will be higher because RAM, SSDs, NICs, cooling and conversion losses also consume power.

## Cluster scheduling idea

A worker that is not needed should be allowed to idle or sleep. A future scheduler can prefer the smallest node that comfortably runs the requested model:

```text
request: 7B model
       │
       ▼
Can 7735U worker run it comfortably? ── yes ──► use low-power worker
       │
       no
       ▼
Can 8845HS worker run it? ──────────── yes ──► use main worker
       │
       no
       ▼
route to big-memory node / RPC fallback
```
