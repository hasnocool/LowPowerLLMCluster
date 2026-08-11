# Agent Workflow Specification

Before changing the project, an agent must:

1. read `AGENTS.md`, `docs/PROJECT_CHARTER.md`, and `docs/GUARDRAILS.md`;
2. identify whether the task changes catalog data, architecture, benchmarks, runtime code or release state;
3. use the matching skill under `.agents/skills/`;
4. preserve source attribution and confidence labels;
5. run the validation suite;
6. update docs and CHANGELOG for user-visible behavior/schema changes.

Before declaring a hardware candidate better than another, the agent must state whether the conclusion comes from manufacturer specifications, listing data, community measurements or project measurements.
