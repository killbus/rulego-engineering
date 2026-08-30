# RuleGo Engineering Knowledge Base Bootstrap

## Goal

Create a durable RuleGo engineering knowledge repository whose Trellis specs
let a new agent session quickly recover the capability boundaries, sources of
truth, Plugin ABI delivery model, rule-chain/runtime practice, and delivery
workflow proven across the current RuleGo ecosystem.

## User value

Future RuleGo work should begin from the established facts and ownership
boundaries instead of reconstructing them from a long conversation or copying
one project's task history.

## Confirmed facts

- This is a documentation and engineering-practice repository initialized with
  Trellis; it is not a backend or frontend application.
- Normative reusable knowledge belongs under `.trellis/spec/` so Trellis
  sessions and task manifests can load it directly.
- Current implementation facts remain owned by their source repositories and
  deployed systems. This repository routes agents to those authorities rather
  than duplicating versions, schemas, credentials, or release artifacts.
- The current RuleGo ecosystem includes the upstream RuleGo host,
  `rulego-server-docker`, `rulego-ffmpeg-over-ip`,
  `rulego-resource-origin`, `rulego-indexed-vod`, a yt-dlp HTTP wrapper, and
  deployed rule chains.
- Local work should remain lightweight; compilation, multi-architecture plugin
  loading, container builds, and release gates run in the owning repositories'
  GitHub Actions workflows.
- The public GitHub repository is `killbus/rulego-engineering`.

## Requirements

### R1. One discoverable entry path

- `AGENTS.md`, the Trellis guides index, and a concise root README must direct
  readers to one RuleGo engineering entry guide.
- The entry guide must route by work type instead of duplicating every detail.

### R2. Explicit authority and capability boundaries

- Document which repository or runtime owns RuleGo host behavior, Plugin ABI,
  plugin contracts, provider resolution, rule composition, publication state,
  external services, and consumer validation.
- Define a first-principles placement test for graph versus plugin versus
  independent service versus consumer/presentation behavior.
- Separate stable node configuration from per-message invocation semantics.

### R3. Plugin ABI and release practice

- Document the host/lock/SDK/plugin/runtime producer-consumer chain without
  copying current ABI values.
- Require immutable SDK/runtime digests, artifact checksum and ABI sidecar,
  matching-runtime registration checks, architecture coverage, and relevant
  multi-plugin coexistence checks.
- Keep heavy verification in CI and workflows thin over repository-owned
  verification commands.

### R4. Rule-chain and runtime practice

- Document RuleGo-native composition, shared owners through `ref://`, secret
  references, deploy/read-back checks, component registration, static resource
  mapping, shared HTTP serving, public-origin handling, and downstream
  validation boundaries.
- Include the evidence dimensions needed for bounded seekable-media workflows
  without making YouTube or one player part of a generic plugin contract.

### R5. Delivery workflow

- Capture first-principles requirement framing, repository/task ownership,
  bounded goal-first expert/reviewer dispatch, same-goal resume across transient
  disconnect/429/retryable-5xx failures, periodic agent-state checks, commit
  boundaries, fixup/rebase policy, CI placement, delivery read-back, and
  requirement-by-requirement completion evidence.
- Keep the process proportional: routine local work must not require standing
  Chatroom or reviewer ceremony.

### R6. Positive and maintainable documentation

- Normative guides describe only the selected present practice, never the
  sequence of discarded designs that led to it.
- Task evidence may retain research, but no task archive is copied from another
  repository.
- No secret, temporary token, fixed deployed credential, or volatile ABI value
  is committed.
- Temporary work is created only below repository `./tmp`, which is ignored by
  Git together with local Python cache files.
- Generic backend/frontend placeholders must be replaced with an explicit
  not-applicable boundary for this documentation-only repository.

### R7. Mechanical validation and delivery

- Provide a lightweight, dependency-free validator for owned documentation:
  required files, relative links, placeholders, and credential patterns.
- Run the validator in a minimal GitHub Actions workflow.
- Initialize Git with one coherent bootstrap commit and publish it to the
  selected public repository.

## Acceptance criteria

- [x] AC1: Starting from `AGENTS.md` or `README.md`, a new session reaches the
      RuleGo engineering entry guide and every specialized guide through valid
      relative links.
- [x] AC2: The ownership guide names each current source of truth and clearly
      distinguishes stable practice from volatile project/runtime facts.
- [x] AC3: The capability guide gives a testable graph/plugin/service/consumer
      placement method and configuration/message/state boundaries.
- [x] AC4: The Plugin ABI guide covers the full immutable build, verification,
      coexistence, release, and install evidence chain.
- [x] AC5: The runtime guide covers rule deployment/read-back and scoped
      end-to-end validation, including bounded seekable-media evidence.
- [x] AC6: The delivery guide records the established goal, agent, retry,
      review, commit, CI, and completion practices without mandating them for
      trivial work.
- [x] AC7: Normative content contains no copied task history, credentials,
      current ABI constants, unresolved placeholders, or unrelated project
      concepts.
- [x] AC7a: Root ignore rules exclude `./tmp` and Python cache files, and no
      temporary artifact is staged.
- [x] AC8: The dependency-free validator passes locally and in GitHub Actions.
- [x] AC9: The final Git commit contains one coherent positive bootstrap and
      the remote delivered state, when authorized, matches it.

## Out of scope

- Implementing or changing RuleGo, a plugin, yt-dlp, ffmpeg-over-ip, or a
  deployed rule chain.
- Becoming a registry for current plugin versions, artifacts, node schemas, or
  credentials.
- Replacing the Trellis lifecycle or generalizing these practices outside the
  RuleGo ecosystem.
- Importing another repository's task archive or historical discussion.
