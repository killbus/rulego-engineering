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
- coexistence checks with relevant plugins that are expected to load together.

Coexistence is a separate requirement because Go plugins can share package
identities even when node APIs are independent. A successful isolated load does
not prove a multi-plugin host.

## CI and release flow

1. Validate source and node behavior with repository-owned commands.
2. Build in the pinned SDK environment.
3. Verify the artifact checksum and compatibility metadata.
4. Start or inspect a matching runtime and prove component registration.
5. Run relevant coexistence and architecture checks.
6. Publish immutable artifacts and their evidence together.
7. Read the release and workflow state back from the hosting platform.

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
