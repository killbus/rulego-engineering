# Commit gate

Run this gate on the staged set of every commit, before `git commit`, and
again on the branch before a merge lands on the default branch. It exists
because content placed where its first-principles owner does not belong has
recurred: process text into a business repository's README (then into an
agent-instruction file, merged as `3808ee2`/`db19da8` into a recreated
`rulego-fleet`, task 10-20), and process into a manifest named for data.

## Path ownership

For every staged path, answer: *is the first-principles owner of this
content the repository and layer this path sits in?*

| Content | Belongs in | Never in |
| --- | --- | --- |
| process, discipline, how-to | the owning engineering guide (`.trellis/spec/` of the knowledge repository) | any business repository (README, agent-instruction files such as `AGENTS.md`, workflow files, manifests) |
| identity and boundary of an artifact owner | that repository's README | process guides outside the repository; other repositories |
| the declared set (coordinates, versions, digests) | the owning manifest / lockfile | prose, README examples, spec files |
| task-specific research and evidence | the active task's `research/` | spec guides; business repositories |
| agent dispatch roles and hook wiring | the platform agent/hook files of the platform that runs them | task artifacts; spec guides |

If the answer for any staged path is "no", the path is out of this commit:
move the content to its owner or remove it. Do not soften a misplaced path
by relocating it to another non-owner.

## Negative list

- No process text (branch rules, merge discipline, checklists, approval
  flow) into any business repository of the ecosystem.
- No agent-instruction or agent-role file created inside a business
  repository. Agent roles live in the platform directories of the platform
  that dispatches them; a role that has no dispatcher is not created.
- No `AGENTS.md`/`CLAUDE.md`/similar committed into a repository that is an
  artifact owner (plugin, contract, runtime, fleet) unless that repository
  also owns its own engineering workflow.
- No second source of truth for a value that already has an authority
  (see [Ownership and authority](./rulego-ownership.md)): no copied digest,
  version tuple, or release state.
- No volatile runtime or deployment facts into spec guides.

## Coherence

One commit = one coherent first-principles change (see [Delivery
workflow](./rulego-delivery-workflow.md), Commit boundary):

- the message names the change the file set proves, and every staged file
  is required to make that change true;
- a correction to an unpushed commit of the same logical change amends or
  fixups that commit; it does not manufacture a new narrative;
- the staged set contains nothing the working tree does not already
  explain (no pre-staged residue, no unrelated dirty paths).

## Message

The message is the change's statement to its readers:

- English, one line, present tense: `type(scope): <what the change
  establishes>`; a body only to carry scope and reason, not process.
- Positive phrasing: the message states what the change makes true, not
  what it avoids, removes, or guards against.
- Reviewer vocabulary stays in the gate: ownership checks, negative lists,
  and failure modes are what the gate applies; the message names only the
  resulting capability.
- This standard prevails over older history: drafting from a
  `git log --oneline -5` sample inherits prefix and length, not language or
  phrasing.

## Merge point

Before any merge to the default branch:

- the branch is not a direct push: it arrived through its normal branch and
  review path;
- fragmentation is resolved first (the branch's commits collapse to the
  coherent set the change actually is); a green CI run on fragmented
  commits does not make the branch merge-ready;
- the merge method is rebase merge, so the consolidated set lands in order.

## Failure mode this gate catches

The recurring error is not "a bad file was added"; it is "the content was
right and it was placed in the nearest writable home". The gate's first
question is therefore never about the text's quality but about the path's
owner. When in doubt, hold the path and name the doubt; do not choose the
second-most-plausible home.
