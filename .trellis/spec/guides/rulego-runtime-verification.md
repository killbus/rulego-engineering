# Runtime verification

Runtime verification proves that registered capabilities compose into the
deployed outcome. It supplements repository tests; it does not redefine node
contracts inside a rule chain.

## Compose with RuleGo-native mechanisms

- Use the graph for sequencing, routing, provider policy, transformations, and
  response presentation.
- Use `ref://` references for explicitly shared component owners instead of
  duplicating clients or lifecycle-bearing dependencies in nodes.
- Resolve credentials through the deployment's secret-reference mechanism.
  Rules and examples contain references, never credential values.
- Keep external services behind their declared protocol and health boundary.
- Treat a node's documented input and output message as its public contract.

## Deploy and read back

For every runtime change:

1. confirm required plugin components are registered;
2. write the rule or configuration through the supported API or deployment
   mechanism;
3. read it back from the server and compare semantic content, including node
   types, references, endpoints, and enabled state;
4. invoke the narrow route with a minimal known input;
5. inspect status, headers, body or stream, and relevant service logs;
6. repeat with the actual downstream consumer when compatibility is claimed.

Editor visibility is registration evidence. It is not invocation, publication,
or consumer evidence.

## Read-back answers different questions

A deployment exposes more than one kind of read-back, and a verification claim
must name which one it used:

- **registry or definition read-back** — which components or handlers are
  installed, and which version each reports;
- **instance or configuration read-back** — which shared or owned instances the
  deployment actually runs, and with which limits.

A version seen in a definition catalog does not evidence configuration. An
absent configuration field in a catalog entry is not "unset at runtime"; it
usually means the catalog carries definitions and the instances live behind
another endpoint. Read instance configuration from the endpoint that owns
instances in that deployment, and keep the authoritative field map in the owning
source rather than restating a route body here.

When a preflight reads either form:

- fail closed on an unknown or ambiguous envelope, and name the check that failed
  (`version`, `retainedBytes`, ...) so the abort stays attributable;
- require a unique match. A selector such as "the resourceOrigin component" that
  can match zero or several entries is a check failure, not a first-match;
- never persist the raw body. Instance configuration can carry upstream
  credentials, secrets, and scripts; keep hashes, extracted numeric bounds, and
  sanitized identifiers only.

### A fail-closed harness must first be proven against the envelope

A harness that cannot parse the deployed envelope is indistinguishable from a
deployment that violates its contract: both abort before the workload runs, and
both produce an empty evidence window. Before any abort is recorded as a verdict
on the system under test, probe the same endpoints read-only and replay the real
bodies through the harness parser. An accepted replay is the harness's own
precondition, and a parser abort is a harness defect to fix, not a product
finding.

#### Wrong

```text
preflight reads only the definition catalog
  -> catalog entries carry identity and version, not instance configuration
  -> the missing limit reads as "capacity contract violated"
  -> abort, no player spawned

# a parser defect now looks exactly like a product verdict, and the
# evidence window closes before the workload ever runs
```

#### Correct

```text
preflight: version <- definition read-back   (unique match, fail closed)
           limits  <- instance read-back     (unique match, fail closed)
           replay both recorded bodies through the parser before authorizing
           the run; an abort there is a harness defect, not a product verdict
```

## Published resources and public origin

When a graph publishes generated resources, verify each owner independently:

- the publication owner reports a stable resource identity and readiness;
- RuleGo static-resource mapping exposes the owned bytes;
- shared HTTP serving is enabled when the endpoint and resources must share an
  origin;
- manifests contain client-reachable URLs, using public-origin presentation
  when relative resolution would target an intermediary host;
- the public path, internal storage path, and lifecycle identity are not
  conflated;
- GET, range behavior when relevant, content type, and cache behavior match the
  consumer contract.

Public origin is deployment/presentation configuration. It must be read from
the deployment rather than embedded as a plugin default.

## Bounded seekable-media evidence

A generic seekable-media claim requires evidence for all applicable dimensions:

- normalized audio/video sources can be reopened or refreshed when temporary
  upstream URLs expire;
- the indexed producer can start at a requested media position;
- production is demand-driven and bounded by explicit look-ahead, retention,
  inactivity, and storage limits rather than running unconditionally to EOF;
- requests outside the current window replace or reposition work without
  retaining an unbounded prior job;
- concurrent equivalent requests share the intended owner and do not multiply
  production accidentally;
- cancellation, timeout, eviction, restart, and partial-output recovery have
  observable behavior;
- manifests expose coherent duration/timeline data and stable, reachable
  segment URLs;
- early, middle, near-end, repeated, backward, and concurrent seeks return
  playable bytes within the stated latency boundary;
- cache and disk measurements demonstrate bounded growth;
- a target consumer is tested separately from protocol and HTTP correctness.

Provider-specific resolution, including YouTube extraction, is an upstream
integration case. A particular media server or player is downstream evidence.
Neither belongs in the generic indexed-production plugin contract.

## Evidence ladder

Collect the narrowest proof for each claim:

1. node tests for message semantics;
2. matching-runtime invocation for registration and execution;
3. HTTP probes for endpoint and resource behavior;
4. system traces for cross-node ownership and lifecycle;
5. consumer playback and seek observations for compatibility.

Record failures at the owner boundary that produced them. Do not compensate in
an unrelated plugin merely because the symptom appears downstream.
