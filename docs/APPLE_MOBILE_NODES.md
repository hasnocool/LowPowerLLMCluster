# Apple silicon and mobile nodes

LowPowerLLMCluster treats Macs, phones and tablets as first-class low-power hardware, but does not pretend they share the same deployment model as a PCIe GPU workstation.

## Current Apple scope

The catalog covers Apple silicon from M1-era Macs through the current M5 generation, including MacBook Air, MacBook Pro, Mac mini, iMac, Mac Studio, iPad Pro/Air, iPhone-class devices and Apple TV where useful as a specialist reference.

Current-generation notes as of 2026-08-11:

- MacBook Air: M5.
- MacBook Pro: M5, M5 Pro and M5 Max.
- Mac mini: M4 and M4 Pro.
- iMac: M4.
- Mac Studio: M4 Max and M3 Ultra.
- iPad Pro: M5.
- iPad Air: M4.
- iPhone 17: A19; iPhone 17 Pro: A19 Pro.
- Apple TV 4K (3rd generation): A15 Bionic.

The project also tracks used M1/M2/M3/M4 Macs because their used-market price can make them better value than a new system.

## Runtime classes

`apple_silicon_system`

- General-purpose macOS node.
- Metal, MLX, llama.cpp Metal and Core ML are relevant runtimes.
- Can participate as an unattended/headless service node.
- Unified memory is fixed at purchase, so exact RAM configuration must be resolved from the listing.

`mobile_phone`

- Android/iOS mobile inference endpoint.
- Do not assume persistent daemon hosting.
- Thermal throttling and OS process restrictions matter.
- Charger wattage is not inference wall power.

`tablet`

- Useful interactive/mobile inference endpoint.
- iPadOS remains sandboxed even when the SoC is shared with a Mac.
- Use a larger conservative memory reserve for model-fit screening.

`media_device`

- Restricted/specialist endpoint such as Apple TV.
- Not ranked as a normal LLM-serving node unless a supported deployment path is demonstrated.

## Memory guardrail

Unified/shared memory is valuable for local inference, but the installed capacity is not fully available to a model. `mobile_platform.model_fit_memory_budget()` applies a conservative reserve for the OS and runtime. This is capacity accounting only; it does not predict tokens/sec.

For Apple products where Apple does not publish RAM in its normal technical specifications (notably iPhone and Apple TV), memory remains `unknown` until a separate reliable evidence source is attached. The catalog does not silently import teardown values.

## Market sourcing

Daily and weekly market profiles now search for representative Apple silicon and current mobile-phone configurations on the existing structured/marketplace adapters. Used Macs are especially important because exact chip + unified-memory combinations can have very different local-LLM value.

## Power evidence

Battery Wh, USB-C adapter wattage, and maximum charging rate are not measured inference power. They may be retained as device/charging facts, but complete-node idle/load power must come from measured or clearly labeled planning evidence before energy-efficiency rankings use it.
