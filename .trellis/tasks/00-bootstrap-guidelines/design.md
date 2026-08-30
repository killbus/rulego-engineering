# Design

## Information architecture

```text
AGENTS.md ─┐
README.md ─┴─> .trellis/spec/guides/rulego-engineering.md
                         ├─> rulego-ownership.md
                         ├─> rulego-capability-design.md
                         ├─> rulego-plugin-delivery.md
                         ├─> rulego-runtime-verification.md
                         └─> rulego-delivery-workflow.md
```

The entry guide owns routing. Each specialized guide owns one topic. README and
AGENTS only point to the entry and explain repository purpose; they do not copy
policy prose.

## Authority model

This repository owns stable cross-repository RuleGo engineering practice. It
does not own current product facts. Each guide identifies the authoritative
source an agent must inspect:

- upstream RuleGo source/release for engine and component behavior;
- `rulego-server-docker/plugin-abi.lock` and published release record for the
  host ABI/SDK/runtime contract;
- each plugin repository for its node API, compatibility metadata, tests, and
  release artifacts;
- deployed server configuration and API read-back for operational state;
- downstream clients for their own compatibility evidence.

This prevents copied versions and examples from becoming a competing source of
truth.

## Trellis integration

- `.trellis/spec/guides/index.md` lists the RuleGo entry guide first.
- Backend and frontend indexes state that those application layers do not
  exist. Unreferenced generated placeholder files are removed.
- Task manifests explicitly inject the RuleGo guides needed by implementation
  and checking agents.
- Project-local AGENTS content is appended outside the Trellis-managed block so
  future `trellis update` operations preserve it.

## Validation

`scripts/validate.py` uses only Python's standard library. It validates the
owned document set, relative links, exact required entry points, absence of
TODO placeholders and common credential patterns, and the documentation-only
backend/frontend boundary. It also requires root ignore rules for repository
`./tmp` and Python caches. CI calls this single command.

## Delivery

The repository begins with one bootstrap commit after validation and publishes
to the selected public GitHub repository. CI is then monitored for the exact
pushed commit.

## Recovery

All work before publication is local and reversible. If validation reveals an
ownership or information-architecture defect, update the planning artifact and
fold the correction into the same bootstrap commit. Published immutable
release history is not part of this task.
