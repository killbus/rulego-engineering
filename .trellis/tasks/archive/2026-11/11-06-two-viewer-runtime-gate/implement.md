# Two-viewer runtime gate implementation plan

## 1. Planning gate

1. Run the Paseo Design Reviewer profile against this task's `design.md`.
2. On a blocking D1-D8 finding, dispatch the Design Reviser and rerun the
   reviewer. Escalate after round two remains unresolved.
3. Record the approved design hash in `approval.md` and start this child task.

The parent authorization is limited to another bounded diagnostic run. It does
not authorize production edits, a third viewer, or AC5 completion.

## 2. Implementer scope

Use the Paseo Implementer profile. The implementer may change only:

```text
research/run-two-viewer.py
research/test_two_viewer.py
research/two-viewer-collector-notes.md
review/responses.json
```

It must preserve:

```text
research/run-single-baseline.py
research/test_single_baseline.py
research/single-baseline-collector-notes.md
research/runtime/*
all prior captures and planning artifacts
```

The new collector may import or copy the frozen single-viewer parsing helpers,
but it must not mutate the single-viewer harness or reinterpret its evidence.

## 3. Implementation steps

1. Implement bounded two-viewer arguments, a launch barrier, and a shared poller.
2. Preserve sanitization, redirect/proxy refusal, credentials stripping and
   response limits from the reviewed collector.
3. Implement preflight component/chain checks and a sanitized precondition file.
4. Emit separate viewer JSONL/summary sections and a collection-status field.
5. Implement owned-process cleanup for normal completion, one-player failure,
   deadline and interruption.
6. Add deterministic offline tests for all design §11 cases.
7. Write notes with the exact command, limits, hashes and known unknowns.

No live API call or playback occurs during implementation.

## 4. Review gate

Use the Paseo Reviewer profile (`deepseek-v4-flash`, `auto-review`, `xhigh`) and
write `review/findings.json`. Blocking findings return to the implementer for a
bounded repair and recheck. The reviewer must verify:

- the two-viewer collector did not modify the single-viewer harness or evidence;
- preflight/read-back semantics match the approved 0.2.1/120000/512 MiB state;
- exactly two owned players and one shared poller are possible;
- telemetry attribution cannot silently mix viewers;
- an aborted launch cannot leave an unowned player;
- summary fields cannot be read as AC5;
- offline tests cover the design's failure and cleanup paths.

## 5. Live execution

Only the parent/main session runs the live gate:

1. Set credentials in the parent process environment without writing them to a
   command, file or evidence.
2. Run a fresh timestamped two-viewer directory.
3. Preserve the preflight, launch, consumer, server, polling and summary files.
4. Do not rerun automatically on an inconclusive or failed result.
5. Do not start a third viewer.

Target command shape:

```powershell
$research = '.trellis/tasks/11-06-two-viewer-runtime-gate/research'
$run = Join-Path $research ('runtime/two-viewer-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))
python -B "$research/run-two-viewer.py" --out $run
```

The exact command may differ only for reviewed safe options such as the mpv path.

## 6. Independent evidence review

After the run, a fresh Paseo Reviewer agent checks the frozen output against the
design and reports:

- AC1-AC7 status;
- current-window server counts and per-viewer associations;
- resolver/inspect timing;
- captured TTLs and derived lower-bound peaks;
- all collection gaps and failures;
- whether the narrow gate passes or is incomplete.

The reviewer writes `review/two-viewer-evidence-findings.json`. It does not edit
the harness, production code, or prior evidence.

## 7. Rollback and preservation

No runtime mutation exists to roll back. If the collector or run fails:

- stop owned processes;
- preserve partial evidence;
- identify the failed precondition or harness invariant;
- return to design if the scope or acceptance definition is defective;
- do not delete a failed run directory.

## 8. Completion evidence

The child task can close only when:

- design review passed;
- implementation review passed;
- the live gate produced a new run directory;
- evidence review returned a bounded verdict;
- the parent still records AC5 as incomplete unless all three required
  three-viewer scenarios pass separately.
