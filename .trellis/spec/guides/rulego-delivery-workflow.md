# Delivery workflow

Use a proportional workflow that preserves first-principles scope and produces
evidence strong enough for the claimed outcome.

## Frame the task

1. Describe the capability or user-visible outcome without naming a preferred
   implementation prematurely.
2. Identify producers, consumers, state owners, and authoritative repositories.
3. Separate confirmed facts, hypotheses, decisions, and acceptance evidence.
4. Create or update the Trellis task in the repository that owns the change.
5. Keep normative guidance positive: describe the selected practice, while
   task research retains only evidence useful to the task.

Do not open a separate task for a correction whose first-principles ownership
and acceptance boundary are unchanged. Fold it into the current logical change.

## Goal-first delegation

Delegate only a concrete, bounded subproblem that can progress independently.
Every dispatched agent receives:

- the active task path and exact role;
- an explicit goal before repository actions;
- the same scope and acceptance evidence as the parent task;
- instructions to treat stream disconnections, HTTP 429 responses, and
  retryable HTTP 5xx failures as transient and resume the same goal;
- a prohibition on commits, pushes, releases, or unrelated repository changes
  unless that authority is explicitly delegated.

Check active agent state periodically at meaningful boundaries. Resume an
unexpectedly archived incomplete goal, stop duplicate work, and clean up idle
or zombie agents. The main agent remains responsible for integration and final
completion evidence.

Routine local edits do not require standing expert discussion. Use a bounded
Chatroom or reviewer when ownership, contract semantics, or architectural
placement remains genuinely unresolved. Give the discussion a decision goal,
then record only the converged result in normative documentation.

## Commit boundary

A commit represents one coherent first-principles change:

- include all files required to make that change true and verifiable;
- exclude unrelated working-tree and pre-staged content;
- stage with explicit path boundaries;
- inspect the staged diff and run relevant checks before committing;
- use fixup and rebase for corrections within the same unpublished logical
  change rather than manufacturing a new narrative commit;
- do not rewrite shared published history solely to improve aesthetics.

The final history describes the resulting capability, not discarded detours.

A contract value and the assertions that read it cannot be split apart: each
revision that separates them fails its own checks. When such a change also
carries work that is independent of the contract version, cut the commits along
that independence rather than along file type. The version-independent work
lands first and stays green against the old contract; the re-sign follows and
carries the value, the assertions, and the documentation that must move
together. Prove the split by running the gate on each interim revision, not
only on the tip.

Iterative work advances on a dedicated branch so its history stays traceable
and isolated from the shared default branch. Reaching the merge point is gated:
before merging to the default branch, resolve commit fragmentation first —
collapse the branch's interim commits into the small set of coherent logical
commits the change actually is. A fragmented branch is not merge-ready, and the
consolidation is a prerequisite of the merge, not cleanup performed after it.

## Verification placement

Run fast, deterministic checks locally. Put compilation, container builds,
multi-architecture coverage, matching-runtime plugin loads, integration suites,
and release publication in the owning repository's GitHub workflows. Workflow
files should call repository-owned scripts so validation logic has one source.

A verification claim is only as valid as the environment that produced it. A
local toolchain is not a stand-in for the pinned CI environment, so evidence
that depends on the exact toolchain, platform, or dependency identity must come
from CI; a lighter local check may support it but never replace it.

Where a release is gated on a CI run — a run whose success and commit identity
the publication step re-reads before shipping artifacts it did not rebuild —
that run's reproducibility is part of the release guarantee. Workflow steps then
reference pinned action commits rather than floating major tags, check out
without persisting credentials, and serialize runs per ref so two runs of one
commit cannot interleave. Pinning to the commit a floating tag resolves to today
changes no behaviour; prove that by re-parsing the rewritten workflow and
asserting the document is structurally identical to the original once the
intended edits are reversed.

After pushing an authorized change:

1. identify the exact remote commit;
2. monitor all required checks for that commit;
3. inspect failure logs and resume the same task on retryable infrastructure
   failures;
4. read back release, package, deployment, or rule state when delivery changes
   external state;
5. distinguish successful publication from successful installation and runtime
   behavior.

## Completion audit

Before declaring completion, map every requirement and named deliverable to
authoritative evidence. For each item, classify the evidence as proving,
contradicting, incomplete, indirect, or missing. Continue while any required
item lacks proof.

Tests and green workflows count only after confirming that their scope covers
the claim. Intent, a clean diff, artifact existence, editor visibility, or a
narrow smoke test cannot establish a broader runtime outcome.

The task is complete only when the requested state exists, required checks pass,
remote or deployed state has been read back where applicable, and no required
work remains.
