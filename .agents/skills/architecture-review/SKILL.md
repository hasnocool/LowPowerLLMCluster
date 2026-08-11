# Architecture Review Skill

Use for router, scheduler, node daemon, RPC or network-design changes.

Ask first: can the request run completely on one appropriate node? Prefer that path. Use cross-node model sharding only when capacity or a measured workload justifies it. Keep control-plane services separable from inference workers. Any asynchronous network/storage code must avoid blocking the event loop and use thread-safe/non-blocking primitives. Document failure modes, node loss and degraded operation.
