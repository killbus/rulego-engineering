# Two-viewer same-program runtime gate

## Goal

Determine whether two simultaneous consumers of the same 1080p program can both
play continuously for 360 seconds when they start at different media positions,
using the deployed `resourceOrigin 0.2.1`, child TTL `120000 ms`, and unchanged
512 MiB retained-byte budget.

This is the next bounded runtime gate after two successful sequential
single-viewer baselines. It narrows the unknown between one viewer and the
three-viewer AC5 matrix; it does not replace AC5.

## Requirements

- **R1. Exact bounded load.** Run exactly two consumers, both against
  `3UJp1qfvL90`, starting at media positions 0 and 600 seconds.
- **R2. No quality downgrade.** Both consumers use the existing single-rendition
  1080p HLS URL and normal client read-ahead.
- **R3. No configuration change.** Do not change the graph, plugins, child TTL,
  parent TTL, `maxRetainedBytes`, cache state, service lifecycle, or player
  quality settings.
- **R4. Concurrent playback.** Both players must be started within a bounded
  synchronization window and overlap for the full 360-second media target.
- **R5. Continuous evidence.** Capture per-consumer progress, resolution,
  terminal status, HTTP/segment failures, buffering intervals, and bounded
  server-node tails. Preserve polling gaps and incomplete coverage explicitly.
- **R6. Attribution.** Keep each player's evidence separate. Server rows may be
  correlated by message/resource identity and time, but must not be described as
  a complete ledger or silently assigned to one player.
- **R7. Stop on unsafe preconditions.** Do not start load if component/chain
  read-back differs from the approved 0.2.1/120000 ms/512 MiB state, if the
  collector's initial node tails cannot be captured, or if two owned players
  cannot be launched.
- **R8. Preserve evidence.** Never overwrite prior runs or reinterpret the
  earlier single-viewer and three-viewer captures.
- **R9. Scope honesty.** A result is "two-viewer same-program different-position
  gate", never general two-user capacity, same-position reuse, three-program
  capacity, or AC5.

## Acceptance Criteria

- **AC1 -> R1/R4.** Evidence shows two distinct player processes with starts 0
  and 600, launched within the bounded synchronization window, and both active
  during the same wall-clock interval.
- **AC2 -> R2/R5.** Each player reaches at least 359 seconds of relative media
  progress within the documented endpoint tolerance, reports 1920x1080, exits
  normally, and has `finished playback, success`.
- **AC3 -> R5.** Neither player log contains a captured segment-open failure or
  HTTP 4xx/5xx error; any completed or unfinished buffering interval is reported
  separately rather than hidden.
- **AC4 -> R5/R6.** Captured server evidence contains successful child
  publications for both requested stream regions, records the observed TTL, and
  records zero `storage_limit` and zero `wait_timeout` signals in the bounded
  observation window.
- **AC5 -> R5/R6.** A machine-readable summary and independent review separate
  observed facts, derived lower bounds, and unavailable inventory. The review
  explicitly states the claim boundary and unresolved gaps.
- **AC6 -> R7.** A sanitized preflight records the deployed component/chain
  state used for the run and aborts on a mismatch.
- **AC7 -> R8/R9.** The run directory is new, prior evidence hashes remain
  unchanged, and the final verdict is limited to this two-viewer scenario.

## Out of Scope

- Same-program same-position reuse.
- Three different programs.
- Three simultaneously active viewers or parent AC5.
- Changing 1080p, the 120-second child TTL, the 512 MiB budget, disk, cache, or
  transcoder concurrency.
- Physical display/audio quality, complete resource inventory, `retainedBytes`,
  other-host consumers, or cross-run capacity guarantees.
