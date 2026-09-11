# Indexed audio passthrough chain (streamed fMP4)

## Goal

Give any audio-consuming downstream client a stable-URL, seekable,
audio-only representation for YouTube assets produced by the RuleGo
deployment, without downloading a complete representation on the RuleGo side
and without imposing a second cache layer on the consumer.

The capability is consumer-agnostic: `(provider, assetId)` → a streamed
fragmented-MP4 audio response. Songloft (self-hosted music server) is the
first known consumer, not the owner of the contract.

Contract: `GET /youtube/:videoId/audio.m4a` returns a streamed fragmented-MP4
audio response (`200`, `audio/mp4`, chunked) produced by one `ffmpeg -c copy`
container-level forward from the googlevideo itag-140 representation, with the
yt-dlp lease cached in ChainCache.

## Requirements

- Zero plugin changes: `rulego-indexed-vod` and `rulego-ffmpeg-over-ip` stay
  untouched; the chain composes existing nodes only.
- No full-track download or publication on the RuleGo side (no
  `resourceOrigin` in this chain). Byte serving is stateless per request.
- Songloft (first known consumer) ingests it through its existing remote-song
  path (`Type=remote`, `DedupKey=sourceKey`, duration from resolver) with no
  model changes; consumer-side wiring stays out of this task's contract.
- `--cookies /data/yt.txt` is mandatory on every yt-dlp invocation.

## Acceptance Criteria

- [ ] Chain deployed on `rulego.docker.pve` behind
      `GET /youtube/:videoId/audio.m4a`.
- [ ] Response is a playable fMP4 audio stream: `ftyp → moov (head) →
      sidx → moof+mdat…` verified by byte inspection.
- [ ] ffprobe reads duration from a head-only slice of the stream body.
- [ ] Songloft (first-consumer validation) plays the song end to end: first
      play streams and lands in `music_cache`, second play is served from
      cache; seek and transcode paths work on the cached fMP4 file.
- [ ] Remote ffmpeg inside the ffmpeg-over-ip container reaches googlevideo
      directly (form verified for radio transcode; this chain needs its own
      e2e evidence).
- [ ] Lease refresh: after googlevideo `expire`, the next request re-resolves
      via ytdlp without manual intervention.

## Notes

- Research and measured evidence live in [research/](research/).
- Design decision history: two rejected alternatives (per-track
  `resourceOrigin` publication; `produceAudio` extension to
  `rulego-indexed-vod`) are recorded with their refutation rationale in
  `research/indexed-audio-design-evidence.md`.
