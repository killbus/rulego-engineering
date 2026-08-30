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
