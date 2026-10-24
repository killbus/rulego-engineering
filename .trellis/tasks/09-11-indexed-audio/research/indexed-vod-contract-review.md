# Research: Does indexed-vod require both video and audio?

- Query: Does the current `../rulego-indexed-vod` implementation require video plus audio, and is that requirement inherent to its indexing capability?
- Scope: local production-source inspection; no implementation or runtime changes.
- Date: 2026-09-11.
- Source snapshot: `D:/Repositories/rulego-indexed-vod`, clean `main` tracking `origin/main`, HEAD `ab2217bccb46b8ca854b778ef82cd805e6941cb9` when inspected.

## Findings

### Current public contract requires both representations

- `D:/Repositories/rulego-indexed-vod/node.go:47-73` defines a `mediaLease` containing `SourceKey`, `Video`, and `Audio`. Both `inspectRequest` and `produceRequest` use that lease.
- `D:/Repositories/rulego-indexed-vod/node.go:195-235`, `func decodeRequest(data string) (string, any, error)`, accepts only `inspect` and `produce`; both call `Source.validate()`. There is no audio-only operation or bypass in this dispatcher.
- `D:/Repositories/rulego-indexed-vod/node.go:241-265`, `func (source mediaLease) validate() error`, contains the decisive condition:

```go
if !source.Video.valid(true) || !source.Audio.valid(false) || source.Video.URL == source.Audio.URL {
    return errors.New("invalid indexed media lease")
}
```

- Missing either representation fails because an empty URL is invalid. URLs must differ. Declared video must be MP4 with an `avc1`/`h264` codec prefix; declared audio must be M4A/MP4 with an `mp4a.40.` prefix or `aac`. These are input validation rules, not independent verification of the actual encoded bytes.

### Dual-track assumptions extend beyond validation

- `D:/Repositories/rulego-indexed-vod/source.go:162-193`, `func (m *sourceManager) inspectSource(ctx context.Context, source mediaLease) (*sourceBundle, error)`, discovers both indexes and fails if either discovery fails.
- `D:/Repositories/rulego-indexed-vod/source.go:73-90`, `func (m *sourceManager) Inspect(parent context.Context, request inspectRequest) (inspectResult, error)`, derives segment count, segment durations, and total duration from `bundle.videoIdx`.
- `D:/Repositories/rulego-indexed-vod/producer.go:53-107`, `func (m *sourceManager) produceOnce(ctx context.Context, bundle *sourceBundle, request produceRequest, directory string) (produceResult, error)`, selects a video reference, finds overlapping audio references, creates two temporary inputs, and produces `{segment}.ts`. Its ffmpeg arguments require both tracks:

```go
"-map", "0:v:0", "-map", "1:a:0",
"-copyts", "-c", "copy", "-shortest",
"-mpegts_copyts", "1", "-mpegts_flags", "+initial_discontinuity",
"-muxdelay", "0", "-f", "mpegts", outputPath,
```

### The lower-level index/range primitives are single-representation operations

- `D:/Repositories/rulego-indexed-vod/sidx.go:41-76`, `func (m *sourceManager) discoverIndex(ctx context.Context, format mediaRepresentation, requireSAP bool) (mediaIndex, error)`, operates on one representation.
- `D:/Repositories/rulego-indexed-vod/sidx.go:109-182`, `func parseSIDX(raw []byte, absoluteOffset uint64, requireSAP bool) (mediaIndex, error)`, parses one index. Its video-specific SAP restriction is conditional on `requireSAP`.
- `D:/Repositories/rulego-indexed-vod/producer.go:178-202`, `func (m *sourceManager) writeInput(ctx context.Context, output *os.File, format mediaRepresentation, index mediaIndex, references []mediaReference, maxBytes int64) error`, copies one representation's initialization bytes and selected references. `D:/Repositories/rulego-indexed-vod/producer.go:205-250` implements those reads with HTTP Range requests. This is bounded file assembly, not an existing HTTP streaming-response API.

## Interpretation

- **Confirmed:** current public behavior requires separate video and audio inputs, including for `inspect`; a rule-chain-only change cannot enable audio-only operation. Merely relaxing validation would leave the video-primary timeline and mandatory video mapping broken.
- **Architectural inference:** the underlying index/range capability does not inherently require a pair. Supporting audio-only would require an explicit contract, timeline, revision/identity, and output-format design, plus tests. Whether that extension belongs here should follow the owned transformation, not the repository's `vod` name.
- Indexed bounded segment production and transparent original-byte Range proxying are different capabilities; evidence for the former does not establish an existing streamed `audio.m4a` endpoint. No decision to change the task's zero-plugin-change constraint was made.

## Related specs

- `D:/Repositories/rulego-engineering/.trellis/spec/guides/rulego-capability-design.md`: place capabilities by transformation and lifecycle, not the first client or provider.
- `D:/Repositories/rulego-engineering/.trellis/spec/guides/rulego-runtime-verification.md`: distinguish source contracts, HTTP behavior, and consumer evidence.

## Naming discussion (2026-09-11)

- The user proposed capability-aligned renaming as the first step. This records the direction of discussion, not approval to rename repositories, change public contracts, or implement audio-only support.
- A fresh read confirmed `D:/Repositories/rulego-indexed-vod/go.mod:1` declares `github.com/killbus/rulego-indexed-vod`; `D:/Repositories/rulego-indexed-vod/node.go:22` declares `componentType = "indexedVod"`; `D:/Repositories/rulego-indexed-vod/node.go:102` uses the label `Indexed VOD`. The node type has no `x/` prefix. The source snapshot remained unchanged.
- Proposed capability statement: consume indexed media representations and produce requested playable media segments with bounded work. Provider resolution, resource publication, HTTP serving, and consumer interpretation remain separate owners.
- Proposed names, pending user confirmation: repository `rulego-indexed-media`, Go module `github.com/killbus/rulego-indexed-media`, node type `indexedMedia`, and label `Indexed Media`. Keeping `indexed` preserves the mechanism that enables bounded access; replacing `vod` with `media` avoids making the present video-plus-audio support matrix the permanent boundary.
- A rename should inventory source identifiers, module references, release/ABI artifact names, examples, registration/configuration, and downstream references before execution. Renaming a node type and renaming a particular shared-instance/reference ID are distinct changes; references must remain coherent.
- Audio-only support must remain a separate, explicitly designed behavior change. A new name alone does not remove the current dual-track validation, video-primary timeline, or mandatory video mapping.
- Compatibility policy is unresolved: coordinated migration of the old public node type versus a transitional alias. External repository rename and writes are not authorized by this research note.
- The existing audio PRD still states zero plugin changes. If this naming direction is accepted for execution, that planning premise and the owning repository/task boundary must be reconciled before implementation; the old PRD was not silently rewritten here.

## Caveats / Not Found

- No tests were executed and no deployed version was checked. The independent documentation/test review did not return results; this conclusion relies on direct production-source evidence, not claimed test coverage.
- No source, task activation, plugin release, deployment, or commit was changed.
