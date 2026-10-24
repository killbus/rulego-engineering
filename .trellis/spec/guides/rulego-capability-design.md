# Capability design

Model a capability by the transformation or lifecycle it owns, not by the
first provider, workflow, or client that demonstrates it.

## Placement test

Apply the questions in order:

1. **Is it composition or policy?** Put sequencing, branching, provider
   selection, field mapping, retries, and presentation assembly in the RuleGo
   graph when existing nodes can express them.
2. **Is it a reusable RuleGo capability missing from the graph?** Put one
   cohesive operation behind a RuleGo plugin node with a stable message
   contract.
3. **Does it require an independently operated process or protocol?** Keep it
   as a service. A plugin may expose an adapter, while the service retains
   process lifecycle, resource control, and protocol ownership.
4. **Is it interpretation or display behavior?** Keep it in the downstream
   consumer or presentation layer.

A boundary is valid when its contract can be named without referring to one
particular rule layout or consumer workaround, and when its owner can test the
whole claimed behavior.

## Configuration, message, and state

Keep three semantics distinct:

| Kind | Meaning | Examples |
| --- | --- | --- |
| Node configuration | Stable instance policy and dependencies | service reference, named resolver, publication owner, bounded limits |
| Input message | Per-invocation facts | source identity, normalized streams, request parameters, correlation data |
| Owned state | Lifecycle that the capability itself must coordinate | publication record, bounded production member, cancellation, deduplication |

Do not promote provider invocation flags, temporary URLs, request headers, or
one asset's codec observations into stable node configuration. Do not hide
workflow policy inside a plugin merely because code can express it there.

State belongs with the capability whose invariant requires it. The graph can
carry message context, but durable identity, bounded shared work, cleanup, and
concurrency coordination need one explicit owner rather than incidental node
memory.

## RuleGo ecosystem applications

- Provider resolution is graph or adapter policy and produces a normalized
  source description. Provider-specific arguments remain at that boundary.
- Generic ffmpeg-over-ip invocation remains an independent service capability;
  the RuleGo plugin exposes it without absorbing unrelated media policy.
- Resource publication owns stable identity and readiness lifecycle; byte
  serving remains the HTTP/static-resource owner's responsibility.
- Indexed media production starts from normalized source data and owns a bounded
  indexed output member. Provider resolution and final manifest presentation
  remain composable concerns.
- Public-origin rewriting is presentation composition. It must not change the
  identity or storage ownership of the published resource.

## Contract review

For every proposed field or output, ask:

- Which owner produces it, and can that owner know it reliably?
- Is it stable configuration, a per-message fact, or derived output?
- Does the capability need it to satisfy its invariant?
- Is it already represented by an upstream or downstream contract?
- Can the field be removed without weakening the named capability?

Expose only semantics required by the capability. Preserve opaque provider
data only when a downstream owner explicitly consumes it; otherwise avoid
turning pass-through glue into a public contract.
