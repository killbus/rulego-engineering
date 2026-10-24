# Plugin delivery

RuleGo dynamic plugins are Go build artifacts loaded by a compiled host. The
`.so` format alone does not establish compatibility: the host, Go toolchain,
platform, and shared dependency identities form a build contract.

## Contract chain

```text
host source -> ABI lock -> immutable SDK/runtime -> plugin artifact
           -> matching-runtime registration -> deployment installation
```

The host distributor owns the ABI lock and publishes matching build and runtime
artifacts. Each plugin consumes that contract and proves its own artifact. Read
the active values from the host release and plugin release records; do not copy
them into this guide.

## Build inputs

A reproducible plugin build pins:

- the host ABI lock or its immutable release record;
- the SDK image and matching runtime image by digest, not only by mutable tags;
- the target operating system, architecture, C library, Go version, and build
  mode required by the host contract;
- plugin source revision and resolved dependency graph.

Use the repository-owned build command as the implementation truth. CI should
invoke that command rather than reproduce build logic in workflow YAML.

## Release evidence

Every released plugin artifact must have:

- an unambiguous platform and architecture in its name;
- an artifact checksum;
- a machine-readable ABI sidecar that identifies the consumed host contract,
  immutable SDK/runtime digests, and relevant build inputs;
- repository tests for the node contract;
- a load-and-register check in the matching runtime;
- architecture coverage for every advertised target;
- a module-identity check that the artifact links the dependency versions the
  repository declares.
- when the plugin requires a peer service contract, a declaration of the
  contract version it needs, asserted against a value compiled from that
  dependency rather than retyped by hand.

Coexistence is not on this list. That requirement is real — Go plugins can share
package identities even when node APIs are independent, and a successful
isolated load does not prove a multi-plugin host — but it is a claim about a set
of artifacts, not a property of one artifact, so no single artifact can carry it
as evidence.

## Member evidence versus composition evidence

Keep these two kinds of proof apart, because mixing them couples repositories
that are not coupled:

- **Member evidence** asserts only properties of the artifact being published:
  its own bytes against its own sidecar, its own registration in the matching
  runtime, its own module identity against the versions its manifest declares.
  It is order-independent, so any repository can be released first.
- **Composition evidence** asserts that a named set of built artifacts loads in
  one process on the matching runtime. It belongs to whoever can name the
  expected set, and it runs after every member has a publishable run.

Consequences that follow from that split:

- A member gate must not download a sibling's published artifacts to prove
  coexistence, and must not require a sibling's artifact bytes to equal values
  in its own sidecar. That is a set assertion placed inside a member gate, and
  an N-member set assertion repeated in every member gate requires N-1 already
  published members, so no member can ever be first: a synchronized migration
  of that fleet deadlocks by construction.
- A compile-time dependency on a sibling module is satisfied by that sibling's
  release tag through the module proxy. It never requires the sibling's
  published binary artifacts, so a real source dependency creates no release
  ordering constraint. Do not let a gate read a dependency as "sibling has
  shipped".
- A declaration and its proof each get exactly one home. If a version literal
  appears in both the manifest and a gate assertion, every upgrade becomes two
  edits that can drift apart; assert the manifest against the built artifact
  instead of asserting the manifest against a literal.
- A shared-package-identity check that compares two binaries belongs to the
  composition carrier. The member-level equivalent costs the same and stays
  order-independent: assert that the artifact links the dependency version and
  hash the manifest declares.
- Composition evidence consumes the artifacts of the runs the releases will
  publish from, so the set proof covers the shipped bytes rather than a
  separately built approximation. It is installation and composition evidence:
  it does not produce ABI identity claims, which remain valid only in the pinned
  CI environment.
- Whoever removes a set assertion from member gates has to name the carrier that
  proves the set instead. Otherwise the fleet ships with no coexistence proof at
  all: the repositories whose gates happen to download siblings are the only
  ones that ever verified it, and the repositories whose gates do not were
  already unverified.

The installation evidence below already asks for the set — "other required
plugins still register in the same process" — so the carrier question is not
new. What a batch adds is a schedule: if the deployment step is not run for
every batch, the set needs a batch gate that runs whether or not anyone
deploys.
What a batch adds is a schedule: if the deployment step is not run for every
batch, the set needs a batch gate that runs whether or not anyone deploys.

## CI and release flow

1. Validate source and node behavior with repository-owned commands.
2. Build in the pinned SDK environment.
3. Verify the artifact checksum and compatibility metadata.
4. Start or inspect a matching runtime and prove component registration.
5. Run architecture checks for every advertised target.
6. Publish immutable artifacts and their evidence together.
7. Read the release and workflow state back from the hosting platform.

Composition evidence is a batch gate, not one of these per-repository steps. Run
it once per batch against the member runs, before those runs feed a release.

Keep expensive compilation, container builds, multi-architecture checks, and
release gates in GitHub Actions. Local validation should remain lightweight
unless the task explicitly requires a local runtime experiment.

The ABI contract is proven only in the pinned CI environment. The host SDK
base image, its Go release, and the runner platform are the single source of
toolchain and ABI evidence: a computed ABI identity, a module-graph digest, and
a matching-runtime load are valid only when produced there. A local toolchain —
a second operating system or architecture, a different Go patch release, a
workstation, or a remote shell standing in for the runner — is not the matching
toolchain and cannot establish ABI equivalence. An ABI-compatibility claim that
cannot be produced in CI is unproven, not merely expected.

Derived contract identities are byte-scoped, so record the byte form that
produces them. An `abi_id` or lock digest is a `sha256` over canonical JSON,
and canonical output is not platform-neutral: the Windows `jq` build appends a
carriage return to every emitted line, silently changing the hashed bytes. The
canonical form is LF, so a normalizer may strip an emitter-added carriage
return only when that is a no-op in the pinned CI environment — prove it by
recomputing the committed contract identity both ways and confirming the LF
value is the one already recorded. Keep the committed contract file and any
derived manifest LF-only, and prefer an explicit line-ending assertion over a
silent strip, because a digest must still describe the committed bytes. An
identity computed locally that differs from the committed one is a local byte
mistake, not a CI failure to explain away, and never a reason to move the hash.

Trigger ABI verification from a pull request on the dedicated branch. A
workflow that also runs on pushes to the default branch is not permission to
push interim or failing states there just to obtain a run: doing so breaks the
merge-point commit-consolidation gate. A red pull-request run is a normal and
useful outcome — it publishes nothing, cannot be referenced by consumers, and
its failure line is the authoritative reading of the contract. Only after the
branch is consolidated and merged does a publication run become eligible,
because the publication revision it records must be a default-branch commit.

Repository contract suites that gate the ABI must themselves run in CI. A check
that exists only as a local command leaves the contract unverified on the one
authoritative environment, and a local green run there proves only that the
local toolchain agreed with itself.

## Fleet repository

The composition owner (`rulego-fleet`) is part of the ecosystem, not a
sidecar of it, and changes to it follow the same merge-point discipline as
member repositories: a feature branch, commits that leave a trail, a pull
request with CI green, commit fragmentation resolved (rebase/fixup/squash)
before the merge, then a rebase merge. There is no direct push to the default
branch, not even for a one-line manifest edit: the fleet's git history is the
audit trail of the composition, so a silent push into it defeats the point.
Process lives here and in the delivery workflow; the fleet's own README
carries only identity and boundary, not process.

## Installation evidence

Installing a plugin means more than copying a file. Verify all of the following:

- the selected artifact checksum matches its release record;
- the runtime implements the same host contract declared by the artifact;
- the plugin is present in the configured plugin directory;
- the process was restarted or reloaded according to the host's mechanism;
- the component registry contains the expected node type;
- a minimal rule invocation proves input/output behavior;
- other required plugins still register in the same process.

The plugin repository owns node semantics. The deployment owns the installed
artifact and observed registration state.
