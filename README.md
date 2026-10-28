# RuleGo Engineering

This repository is the durable engineering knowledge base for work across the
RuleGo ecosystem. It documents capability ownership, plugin delivery, runtime
verification, and delivery practice without duplicating live project state.

Deployable RuleGo example profiles live under [`examples/`](examples/), each a
self-contained, boundary-proofed artifact (chain JSON, index mappings, fixtures,
and a Go/goja harness that runs the committed scripts through the real engine).
Examples are the consumer-side acceptance for their owning plugin and are never
imported by the plugin package; each example is self-contained under its own
directory and names the consumer contract it wires (e.g. the Budva push webhook).

Start with the [RuleGo engineering guide](.trellis/spec/guides/rulego-engineering.md).
Implementation details and current versions remain in their owning repositories.
