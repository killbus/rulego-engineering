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

## Verification placement

Run fast, deterministic checks locally. Put compilation, container builds,
multi-architecture coverage, matching-runtime plugin loads, integration suites,
and release publication in the owning repository's GitHub workflows. Workflow
files should call repository-owned scripts so validation logic has one source.

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
