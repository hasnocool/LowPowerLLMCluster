# Architecture

The project is built around a simple rule: **use the network to send jobs, not memory traffic, whenever possible.**

A local LLM spends a lot of time reading model weights from memory. Local DDR5 can move tens of gigabytes per second. A 2.5GbE link has a theoretical line rate of only about 0.3125 GB/s before protocol overhead. That is why splitting every token across several cheap Ethernet-connected machines can be disappointing.

The preferred design is independent workers:

```text
                              ┌───────────────────┐
                              │  REQUEST ROUTER   │
                              │                   │
                              │ model / task /    │
                              │ power / load      │
                              └─────────┬─────────┘
                                        │
                             2.5GbE switching fabric
                                        │
              ┌─────────────────────────┼─────────────────────────┐
              │                         │                         │
              ▼                         ▼                         ▼
       ┌──────────────┐          ┌──────────────┐          ┌──────────────┐
       │ WORKER A     │          │ WORKER B     │          │ WORKER C     │
       │ Ryzen 7735U  │          │ Ryzen 8845HS │          │ Ryzen 8745HS │
       │ 32/64GB      │          │ 64GB         │          │ 64/96GB      │
       │ small model  │          │ coding model │          │ heavy model  │
       └──────────────┘          └──────────────┘          └──────────────┘
              │                         │                         │
              └──────── independent inference ──────────────────┘
```

## Why this is better

If three requests arrive, three nodes can work at the same time. The weights for each model stay in that machine's RAM instead of repeatedly crossing Ethernet.

Model sharding with llama.cpp RPC can still exist:

```text
                 LARGE MODEL THAT WILL NOT FIT ONE NODE

            ┌────────────────┐        ┌────────────────┐
            │ NODE A         │  RPC   │ NODE B         │
            │ model layers   │◄──────►│ model layers   │
            └────────────────┘        └────────────────┘

                 useful fallback, not the default path
```

## Planned control plane

```text
                   ┌─────────────────────────┐
                   │      CLUSTER API        │
                   ├─────────────────────────┤
                   │ capability registry     │
                   │ model placement         │
                   │ health checks           │
                   │ queue depth             │
                   │ power-aware routing     │
                   │ benchmark database      │
                   └────────────┬────────────┘
                                │
          ┌─────────────────────┼─────────────────────┐
          ▼                     ▼                     ▼
   llama.cpp server      llama.cpp server      llama.cpp server
     cheap worker           fast worker           big-memory
```

The future software layer should expose an OpenAI-compatible endpoint so clients do not need to know which node actually ran the model.
