# Distributed Resource Scheduling

Secure v2 workers advertise capabilities, locality labels and a resource snapshot. Source `worker_requirements` are divided into hard eligibility constraints and soft affinity.

## Hard constraints and unknown measurements

When a source explicitly configures a CPU-load, thermal, available-memory, or worker power-budget requirement, the worker must report the corresponding measurement. If that measurement is missing or null, the worker is ineligible for the task. Unknown telemetry is not evidence that a configured resource boundary is satisfied.

This applies only to explicitly configured hard constraints. A worker may still run a source that does not require a metric it cannot measure.

## Affinity and work stealing

`worker_affinity` is a locality preference, not a permanent pin. A non-affinity worker remains ineligible until the configured work-steal delay elapses, then it may take the task only if all hard capability, label and resource constraints still pass.

## Power semantics

Power and energy budgets are operator-supplied scheduling boundaries. They are not guessed power measurements and must not be presented as measured node consumption or LLM efficiency evidence.
